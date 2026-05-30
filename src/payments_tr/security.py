"""
Security utilities for payment processing.

This module provides security features including:
- Webhook signature verification for iyzico
- Rate limiting for webhook endpoints
- Audit logging for sensitive operations
- Idempotency key management
"""

from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, cast

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)


@dataclass
class SecurityConfig:
    """Configuration for security features."""

    # Webhook verification
    iyzico_webhook_secret: str = ""
    verify_webhooks: bool = True

    # Rate limiting
    enable_rate_limiting: bool = True
    rate_limit_requests: int = 100  # requests per window
    rate_limit_window: int = 60  # seconds

    # Audit logging
    enable_audit_log: bool = True
    audit_log_sensitive_data: bool = False

    @classmethod
    def from_settings(cls) -> SecurityConfig:
        """Load configuration from Django settings."""
        payments_settings = getattr(settings, "PAYMENTS_TR", {})
        security = payments_settings.get("SECURITY", {})

        return cls(
            iyzico_webhook_secret=security.get("IYZICO_WEBHOOK_SECRET", ""),
            verify_webhooks=security.get("VERIFY_WEBHOOKS", True),
            enable_rate_limiting=security.get("ENABLE_RATE_LIMITING", True),
            rate_limit_requests=security.get("RATE_LIMIT_REQUESTS", 100),
            rate_limit_window=security.get("RATE_LIMIT_WINDOW", 60),
            enable_audit_log=security.get("ENABLE_AUDIT_LOG", True),
            audit_log_sensitive_data=security.get("AUDIT_LOG_SENSITIVE_DATA", False),
        )


class IyzicoWebhookVerifier:
    """
    Webhook signature verification for iyzico (``X-IYZ-SIGNATURE-V3``).

    .. warning::

        **Behaviour change (security fix).** iyzico does **not** sign the
        raw JSON body. It signs an ordered concatenation of specific event
        fields keyed by the merchant **secret key** (``IYZICO_SECRET_KEY``).
        Previous versions HMAC'd the raw payload keyed by a separate
        ``IYZICO_WEBHOOK_SECRET``; that scheme could never match a genuine
        iyzico signature. This verifier now implements iyzico's real
        algorithm — see
        :func:`payments_tr.providers.iyzico.utils.build_iyzico_signature_string`.

        Pass the merchant secret key as ``secret``. ``compute_signature``
        and ``verify`` now take the *parsed* webhook ``dict`` (a raw
        ``bytes`` body is still accepted and parsed for compatibility).

    Example:
        >>> verifier = IyzicoWebhookVerifier(secret="your-secret-key")
        >>> is_valid = verifier.verify(webhook_dict, signature)
    """

    def __init__(self, secret: str | None = None):
        """
        Initialize the verifier.

        Args:
            secret: Merchant secret key (``IYZICO_SECRET_KEY``), or None to
                load it from ``IYZICO_SECRET_KEY`` / the legacy
                ``PAYMENTS_TR['SECURITY']['IYZICO_WEBHOOK_SECRET']`` setting.
        """
        if secret is None:
            secret = getattr(settings, "IYZICO_SECRET_KEY", "") or ""
            if not secret:
                # Backwards-compatible fallback to the legacy setting.
                config = SecurityConfig.from_settings()
                secret = config.iyzico_webhook_secret

        if not secret:
            logger.warning(
                "iyzico secret key not configured. "
                "Webhook verification will fail. "
                "Set IYZICO_SECRET_KEY in settings."
            )
        self.secret = secret

    @staticmethod
    def _as_dict(payload: bytes | dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        import json

        raw = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        return cast("dict[str, Any]", json.loads(raw))

    def compute_signature(self, payload: bytes | dict[str, Any]) -> str:
        """
        Compute the iyzico ``X-IYZ-SIGNATURE-V3`` signature for a payload.

        Args:
            payload: Parsed webhook dict, or raw JSON body bytes.

        Returns:
            Hex-encoded signature string.
        """
        if not self.secret:
            raise ValueError("Webhook secret not configured")

        from payments_tr.providers.iyzico.utils import compute_iyzico_webhook_signature

        return compute_iyzico_webhook_signature(self._as_dict(payload), self.secret)

    def verify(self, payload: bytes | dict[str, Any], signature: str) -> bool:
        """
        Verify an iyzico webhook signature.

        Args:
            payload: Parsed webhook dict, or raw JSON body bytes.
            signature: Value of the ``X-IYZ-SIGNATURE-V3`` header.

        Returns:
            True if signature is valid, False otherwise.
        """
        if not self.secret:
            logger.error("Cannot verify webhook: secret not configured")
            return False

        try:
            expected_signature = self.compute_signature(payload)
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False


class RateLimiter:
    """
    Rate limiter for webhook endpoints.

    Uses token bucket algorithm with Django cache backend.
    Falls back to in-memory storage if cache is not available.

    Example:
        >>> limiter = RateLimiter(max_requests=100, window=60)
        >>> if limiter.allow("client-ip"):
        ...     process_webhook()
        ... else:
        ...     return 429
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window: int | None = None,
        cache_prefix: str = "payments_tr:ratelimit",
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window
            window: Time window in seconds
            cache_prefix: Prefix for cache keys
        """
        config = SecurityConfig.from_settings()

        self.max_requests = max_requests or config.rate_limit_requests
        self.window = window or config.rate_limit_window
        self.cache_prefix = cache_prefix
        self.enabled = config.enable_rate_limiting

        # Fallback in-memory storage
        self._memory_store: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _get_cache_key(self, identifier: str) -> str:
        """Generate cache key for identifier."""
        return f"{self.cache_prefix}:{identifier}"

    def _clean_old_requests(self, requests: list[float], current_time: float) -> list[float]:
        """Remove requests outside the time window."""
        cutoff = current_time - self.window
        return [req_time for req_time in requests if req_time > cutoff]

    def allow(self, identifier: str) -> bool:
        """
        Check if request is allowed for identifier.

        Args:
            identifier: Unique identifier (e.g., IP address, user ID)

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        if not self.enabled:
            return True

        current_time = time.time()
        cache_key = self._get_cache_key(identifier)

        try:
            # Atomic fixed-window counter.
            #
            # A read-modify-write (get -> compare -> set) races under
            # concurrency: N simultaneous requests all read the same
            # pre-increment value and all pass, so the effective limit is
            # much higher than configured. ``cache.add`` (only sets if absent)
            # plus ``cache.incr`` (atomic on real backends like Redis/
            # Memcached) closes that window.
            #
            # ``cache.add`` returns False if the key already exists, so the
            # window TTL is established exactly once per window and the
            # counter naturally resets when the key expires.
            cache.add(cache_key, 0, self.window)
            try:
                count = cache.incr(cache_key)
            except ValueError:
                # Key expired between add and incr; re-establish it.
                cache.add(cache_key, 0, self.window)
                count = cache.incr(cache_key)

            if count > self.max_requests:
                logger.warning(
                    f"Rate limit exceeded for {identifier}: "
                    f"{count}/{self.max_requests} requests"
                )
                return False

            return True

        except Exception as e:
            # Fallback to in-memory storage
            logger.warning(f"Cache error, using in-memory rate limiting: {e}")

            with self._lock:
                requests = self._memory_store[identifier]
                requests = self._clean_old_requests(requests, current_time)
                self._memory_store[identifier] = requests

                if len(requests) >= self.max_requests:
                    logger.warning(
                        f"Rate limit exceeded for {identifier}: "
                        f"{len(requests)}/{self.max_requests} requests"
                    )
                    return False

                requests.append(current_time)
                return True

    def reset(self, identifier: str) -> None:
        """Reset rate limit for identifier."""
        cache_key = self._get_cache_key(identifier)
        try:
            cache.delete(cache_key)
        except Exception:
            pass

        with self._lock:
            if identifier in self._memory_store:
                del self._memory_store[identifier]


@dataclass
class AuditLogEntry:
    """Audit log entry for sensitive operations."""

    timestamp: datetime
    operation: str
    user: str
    payment_id: str | int | None
    provider: str
    success: bool
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "user": self.user,
            "payment_id": self.payment_id,
            "provider": self.provider,
            "success": self.success,
            "details": self.details,
            "ip_address": self.ip_address,
        }


class AuditLogger:
    """
    Audit logger for sensitive payment operations.

    Logs operations like refunds, EFT approvals, and webhook processing.

    Example:
        >>> audit = AuditLogger()
        >>> audit.log_refund(user, payment, success=True, amount=5000)
    """

    def __init__(self, logger_name: str = "payments_tr.audit"):
        """
        Initialize audit logger.

        Args:
            logger_name: Name for the audit logger
        """
        self.logger = logging.getLogger(logger_name)
        config = SecurityConfig.from_settings()
        self.enabled = config.enable_audit_log
        self.log_sensitive = config.audit_log_sensitive_data

    def log(self, entry: AuditLogEntry) -> None:
        """Log an audit entry."""
        if not self.enabled:
            return

        # Filter sensitive data if needed
        details = entry.details.copy()
        if not self.log_sensitive:
            # Remove sensitive fields
            for key in ["card_number", "cvv", "password", "secret", "token"]:
                if key in details:
                    details[key] = "***REDACTED***"

        log_data = {**entry.to_dict(), "details": details}

        if entry.success:
            self.logger.info(f"Audit: {entry.operation}", extra=log_data)
        else:
            self.logger.warning(f"Audit: {entry.operation} FAILED", extra=log_data)

    def log_refund(
        self,
        user: str,
        payment_id: str | int | None,
        provider: str,
        success: bool,
        amount: int | None = None,
        reason: str = "",
        ip_address: str = "",
    ) -> None:
        """Log a refund operation."""
        entry = AuditLogEntry(
            timestamp=django_timezone.now(),
            operation="refund",
            user=user,
            payment_id=payment_id,
            provider=provider,
            success=success,
            details={"amount": amount, "reason": reason},
            ip_address=ip_address,
        )
        self.log(entry)

    def log_eft_approval(
        self,
        user: str,
        payment_id: str | int,
        approved: bool,
        success: bool,
        reason: str = "",
        ip_address: str = "",
    ) -> None:
        """Log an EFT approval/rejection."""
        operation = "eft_approve" if approved else "eft_reject"
        entry = AuditLogEntry(
            timestamp=django_timezone.now(),
            operation=operation,
            user=user,
            payment_id=payment_id,
            provider="eft",
            success=success,
            details={"approved": approved, "reason": reason},
            ip_address=ip_address,
        )
        self.log(entry)

    def log_webhook(
        self,
        provider: str,
        event_type: str,
        payment_id: str | int | None,
        success: bool,
        ip_address: str = "",
    ) -> None:
        """Log webhook processing."""
        entry = AuditLogEntry(
            timestamp=django_timezone.now(),
            operation="webhook",
            user="system",
            payment_id=payment_id,
            provider=provider,
            success=success,
            details={"event_type": event_type},
            ip_address=ip_address,
        )
        self.log(entry)


class IdempotencyManager:
    """
    Idempotency key manager for webhook processing.

    Ensures webhooks are processed exactly once, even if they are
    delivered multiple times by the provider.

    Example:
        >>> manager = IdempotencyManager()
        >>> if manager.check("webhook-123"):
        ...     process_webhook()
        ...     manager.mark_processed("webhook-123")
    """

    def __init__(
        self,
        ttl: int = 86400,  # 24 hours
        cache_prefix: str = "payments_tr:idempotency",
    ):
        """
        Initialize idempotency manager.

        Args:
            ttl: Time-to-live for idempotency keys in seconds
            cache_prefix: Prefix for cache keys
        """
        self.ttl = ttl
        self.cache_prefix = cache_prefix
        self._memory_store: dict[str, datetime] = {}
        self._lock = Lock()

    def _get_cache_key(self, idempotency_key: str) -> str:
        """Generate cache key."""
        return f"{self.cache_prefix}:{idempotency_key}"

    def check(self, idempotency_key: str) -> bool:
        """
        Check if operation has already been processed.

        Args:
            idempotency_key: Unique identifier for the operation

        Returns:
            True if this is a new operation, False if already processed
        """
        cache_key = self._get_cache_key(idempotency_key)

        try:
            # Try Django cache first
            if cache.get(cache_key):
                logger.info(f"Idempotent operation detected: {idempotency_key}")
                return False
            return True

        except Exception as e:
            logger.warning(f"Cache error, using in-memory idempotency check: {e}")

            # Fallback to in-memory storage
            with self._lock:
                # Clean old entries
                cutoff = django_timezone.now() - timedelta(seconds=self.ttl)
                self._memory_store = {k: v for k, v in self._memory_store.items() if v > cutoff}

                if idempotency_key in self._memory_store:
                    logger.info(f"Idempotent operation detected: {idempotency_key}")
                    return False
                return True

    def mark_processed(self, idempotency_key: str) -> None:
        """
        Mark operation as processed.

        Args:
            idempotency_key: Unique identifier for the operation
        """
        cache_key = self._get_cache_key(idempotency_key)

        try:
            cache.set(cache_key, True, self.ttl)
        except Exception:
            pass

        with self._lock:
            self._memory_store[idempotency_key] = django_timezone.now()


# Decorator for idempotent operations
def idempotent(key_func: Callable[[Any], str]):
    """
    Decorator to make functions idempotent.

    Args:
        key_func: Function that extracts idempotency key from arguments

    Example:
        >>> @idempotent(lambda webhook_id: f"webhook:{webhook_id}")
        ... def process_webhook(webhook_id, data):
        ...     # Process webhook
        ...     pass
    """
    from functools import wraps

    def decorator(func: Callable) -> Callable:
        manager = IdempotencyManager()

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            if not manager.check(key):
                logger.info(f"Skipping idempotent operation: {func.__name__}")
                return None

            result = func(*args, **kwargs)
            manager.mark_processed(key)
            return result

        return wrapper

    return decorator
