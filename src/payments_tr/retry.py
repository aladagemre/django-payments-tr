"""
Retry utilities with exponential backoff for payment operations.

This module provides decorators and utilities for retrying failed
payment operations with configurable backoff strategies.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay between retries
            exponential_base: Base for exponential backoff
            jitter: Add random jitter to delay
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        delay = min(self.initial_delay * (self.exponential_base**attempt), self.max_delay)

        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to delay
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback called on each retry attempt

    Example:
        >>> @retry_with_backoff(max_attempts=3, initial_delay=1.0)
        ... def create_payment(payment):
        ...     provider = get_payment_provider()
        ...     return provider.create_payment(payment)
        >>>
        >>> result = create_payment(payment)  # Will retry up to 3 times
    """
    config = RetryConfig(max_attempts, initial_delay, max_delay, exponential_base, jitter)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts - 1:
                        # Last attempt failed
                        logger.error(
                            f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                        )
                        raise

                    delay = config.get_delay(attempt)
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt + 1}/{config.max_attempts}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


class RetryableOperation:
    """
    Context manager for retryable operations.

    Example:
        >>> retry = RetryableOperation(max_attempts=3)
        >>> for attempt in retry:
        ...     with attempt:
        ...         result = provider.create_payment(payment)
        ...         break  # Success
    """

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        """Initialize retryable operation context."""
        self.config = RetryConfig(max_attempts, initial_delay, max_delay, exponential_base, jitter)
        self.current_attempt = 0
        self.last_exception: Exception | None = None

    def __iter__(self):
        """Iterate over retry attempts."""
        self.current_attempt = 0
        return self

    def __next__(self):
        """Get next retry attempt."""
        if self.current_attempt >= self.config.max_attempts:
            if self.last_exception:
                raise self.last_exception
            raise StopIteration

        attempt = RetryAttempt(self, self.current_attempt)
        self.current_attempt += 1
        return attempt


class RetryAttempt:
    """Single retry attempt context manager."""

    def __init__(self, operation: RetryableOperation, attempt_number: int):
        """Initialize retry attempt."""
        self.operation = operation
        self.attempt_number = attempt_number

    def __enter__(self):
        """Enter retry attempt context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit retry attempt context."""
        if exc_type is None:
            # Success
            return True

        # Store exception
        self.operation.last_exception = exc_val

        # Check if this was the last attempt
        if self.attempt_number >= self.operation.config.max_attempts - 1:
            logger.error(
                f"Operation failed after {self.operation.config.max_attempts} attempts: {exc_val}"
            )
            return False  # Re-raise exception

        # Calculate delay and sleep
        delay = self.operation.config.get_delay(self.attempt_number)
        logger.warning(
            f"Attempt {self.attempt_number + 1}/{self.operation.config.max_attempts} failed: "
            f"{exc_val}. Retrying in {delay:.2f}s..."
        )
        time.sleep(delay)

        return True  # Suppress exception, will retry


# Async versions
try:
    import asyncio

    def async_retry_with_backoff(
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        exceptions: tuple[type[Exception], ...] = (Exception,),
        on_retry: Callable[[Exception, int], None] | None = None,
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """
        Async decorator to retry function with exponential backoff.

        Args:
            max_attempts: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay between retries
            exponential_base: Base for exponential backoff
            jitter: Add random jitter to delay
            exceptions: Tuple of exceptions to catch and retry
            on_retry: Optional callback called on each retry attempt

        Example:
            >>> @async_retry_with_backoff(max_attempts=3)
            ... async def create_payment(payment):
            ...     provider = get_payment_provider()
            ...     return await provider.create_payment_async(payment)
        """
        config = RetryConfig(max_attempts, initial_delay, max_delay, exponential_base, jitter)

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                last_exception = None

                for attempt in range(config.max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e

                        if attempt == config.max_attempts - 1:
                            # Last attempt failed
                            logger.error(
                                f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                            )
                            raise

                        delay = config.get_delay(attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{config.max_attempts}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )

                        if on_retry:
                            on_retry(e, attempt)

                        await asyncio.sleep(delay)

                # This should never be reached, but just in case
                if last_exception:
                    raise last_exception
                raise RuntimeError("Unexpected retry loop exit")

            return wrapper

        return decorator

except ImportError:
    # asyncio not available
    pass
