"""
Decorator utilities for payment operations.

This module provides decorators for common payment-related tasks like
transaction management, signal dispatching, audit logging, and error handling.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import Any, Callable, TypeVar

from django.db import transaction

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_payment_signals(
    created_signal: Any | None = None,
    confirmed_signal: Any | None = None,
    failed_signal: Any | None = None,
):
    """
    Decorator to automatically dispatch payment signals.

    Args:
        created_signal: Signal to dispatch on payment creation
        confirmed_signal: Signal to dispatch on successful payment
        failed_signal: Signal to dispatch on payment failure

    Example:
        >>> from payments_tr.signals import payment_created, payment_confirmed
        >>>
        >>> @with_payment_signals(
        ...     created_signal=payment_created,
        ...     confirmed_signal=payment_confirmed
        ... )
        ... def process_payment(payment, provider):
        ...     result = provider.create_payment(payment)
        ...     return result
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Execute function
            result = func(*args, **kwargs)

            # Dispatch signals based on result
            if hasattr(result, "success"):
                payment = args[0] if args else None
                provider_name = getattr(args[1], "provider_name", None) if len(args) > 1 else None

                if result.success and confirmed_signal:
                    confirmed_signal.send(
                        sender=payment.__class__ if payment else None,
                        payment=payment,
                        provider=provider_name,
                        result=result,
                    )
                elif not result.success and failed_signal:
                    failed_signal.send(
                        sender=payment.__class__ if payment else None,
                        payment=payment,
                        provider=provider_name,
                        result=result,
                        error_message=getattr(result, "error_message", None),
                    )

            return result

        return wrapper

    return decorator


def with_audit_log(operation: str):
    """
    Decorator to automatically log operations to audit log.

    Args:
        operation: Operation name (e.g., 'refund', 'payment_creation')

    Example:
        >>> @with_audit_log('refund')
        ... def process_refund(payment, amount, user):
        ...     # Process refund
        ...     return result
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from payments_tr.security import AuditLogger

            audit = AuditLogger()

            # Execute function
            try:
                result = func(*args, **kwargs)

                # Log success
                user = kwargs.get("user", "system")
                payment = args[0] if args else None
                payment_id = getattr(payment, "id", None)

                if operation == "refund":
                    audit.log_refund(
                        user=str(user),
                        payment_id=payment_id,
                        provider=kwargs.get("provider", "unknown"),
                        success=getattr(result, "success", True),
                        amount=kwargs.get("amount"),
                        reason=kwargs.get("reason", ""),
                    )

                return result

            except Exception as e:
                # Log failure
                user = kwargs.get("user", "system")
                payment = args[0] if args else None
                payment_id = getattr(payment, "id", None)

                if operation == "refund":
                    audit.log_refund(
                        user=str(user),
                        payment_id=payment_id,
                        provider=kwargs.get("provider", "unknown"),
                        success=False,
                    )

                raise

        return wrapper

    return decorator


def atomic_payment_operation(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to wrap payment operations in database transaction.

    Example:
        >>> @atomic_payment_operation
        ... def process_payment_and_update_order(payment, order):
        ...     result = provider.create_payment(payment)
        ...     if result.success:
        ...         order.status = 'paid'
        ...         order.save()
        ...     return result
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with transaction.atomic():
            return func(*args, **kwargs)

    return wrapper


def log_payment_operation(
    log_start: bool = True,
    log_end: bool = True,
    log_errors: bool = True,
):
    """
    Decorator to log payment operations.

    Args:
        log_start: Log when operation starts
        log_end: Log when operation completes
        log_errors: Log errors

    Example:
        >>> @log_payment_operation(log_start=True, log_end=True)
        ... def create_payment(payment, provider):
        ...     return provider.create_payment(payment)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract payment info if available
            payment = args[0] if args else None
            payment_id = getattr(payment, "id", None)
            provider = getattr(args[1], "provider_name", None) if len(args) > 1 else None

            operation_name = func.__name__

            if log_start:
                logger.info(
                    f"Starting {operation_name}",
                    extra={"payment_id": payment_id, "provider": provider},
                )

            try:
                result = func(*args, **kwargs)

                if log_end:
                    success = getattr(result, "success", True)
                    logger.info(
                        f"Completed {operation_name}: {'success' if success else 'failed'}",
                        extra={"payment_id": payment_id, "provider": provider},
                    )

                return result

            except Exception as e:
                if log_errors:
                    logger.error(
                        f"Error in {operation_name}: {str(e)}",
                        extra={"payment_id": payment_id, "provider": provider},
                        exc_info=True,
                    )
                raise

        return wrapper

    return decorator


def cache_provider_result(ttl: int = 300):
    """
    Decorator to cache provider API results.

    Args:
        ttl: Time-to-live in seconds

    Example:
        >>> @cache_provider_result(ttl=60)
        ... def get_payment_status(provider_payment_id):
        ...     return provider.get_payment_status(provider_payment_id)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from django.core.cache import cache

            # Generate deterministic cache key
            # Convert args and kwargs to a JSON string, then hash it
            try:
                # Create a deterministic representation of arguments
                cache_data = {
                    "args": [str(arg) for arg in args],
                    "kwargs": {k: str(v) for k, v in sorted(kwargs.items())},
                }
                cache_json = json.dumps(cache_data, sort_keys=True)
                cache_hash = hashlib.md5(cache_json.encode()).hexdigest()
                cache_key = f"payments_tr:{func.__name__}:{cache_hash}"
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to generate cache key for {func.__name__}: {e}")
                # Fall back to executing without cache
                return func(*args, **kwargs)

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {func.__name__}")
                return result

            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            logger.debug(f"Cached result for {func.__name__} (ttl={ttl}s)")

            return result

        return wrapper

    return decorator


def require_payment_provider(provider_name: str | None = None):
    """
    Decorator to ensure payment provider is available.

    Args:
        provider_name: Required provider name, or None to allow any

    Example:
        >>> @require_payment_provider('stripe')
        ... def process_stripe_payment(payment):
        ...     provider = get_payment_provider('stripe')
        ...     return provider.create_payment(payment)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from payments_tr.providers.registry import get_payment_provider

            try:
                provider = get_payment_provider(provider_name)
                if provider is None:
                    raise ValueError(
                        f"Payment provider not available: {provider_name or 'default'}"
                    )
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Provider requirement failed: {e}")
                raise

        return wrapper

    return decorator


def measure_payment_time(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to measure and log payment operation time.

    Example:
        >>> @measure_payment_time
        ... def create_payment(payment, provider):
        ...     return provider.create_payment(payment)
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import time

        start_time = time.time()

        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                f"{func.__name__} completed in {duration_ms:.0f}ms",
                extra={"duration_ms": duration_ms, "operation": func.__name__},
            )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"{func.__name__} failed after {duration_ms:.0f}ms: {e}",
                extra={"duration_ms": duration_ms, "operation": func.__name__},
            )
            raise

    return wrapper


def handle_payment_errors(
    default_return: Any = None,
    log_errors: bool = True,
):
    """
    Decorator to handle payment errors gracefully.

    Args:
        default_return: Default value to return on error
        log_errors: Whether to log errors

    Example:
        >>> @handle_payment_errors(default_return=None)
        ... def get_payment_status(payment_id):
        ...     return provider.get_payment_status(payment_id)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    logger.error(
                        f"Error in {func.__name__}: {str(e)}",
                        exc_info=True,
                    )
                return default_return

        return wrapper

    return decorator
