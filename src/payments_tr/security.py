"""
Security utilities for payment processing.

This module provides security features including:
- Webhook signature verification for iyzico
- Rate limiting for webhook endpoints
- Audit logging for sensitive operations
- Idempotency key management
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any

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
    Webhook signature verification for iyzico.

    iyzico uses HMAC-SHA256 for webhook signatures. This verifier
    ensures that incoming webhooks are authentic.

    Example:
        >>> verifier = IyzicoWebhookVerifier(secret="your-webhook-secret")
        >>> is_valid = verifier.verify(payload, signature)
    """

    def __init__(self, secret: str | None = None):
        """
        Initialize the verifier.

        Args:
            secret: Webhook secret key, or None to load from settings
        """
        if secret is None:
            config = SecurityConfig.from_settings()
            secret = config.iyzico_webhook_secret

        if not secret:
            logger.warning(
                "iyzico webhook secret not configured. "
                "Webhook verification will fail. "
                "Set PAYMENTS_TR['SECURITY']['IYZICO_WEBHOOK_SECRET'] in settings."
            )
        self.secret = secret

    def compute_signature(self, payload: bytes) -> str:
        """
        Compute HMAC-SHA256 signature for payload.

        Args:
            payload: Raw webhook payload bytes

        Returns:
            Hex-encoded signature string
        """
        if not self.secret:
            raise ValueError("Webhook secret not configured")

        return hmac.new(self.secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from webhook headers

        Returns:
            True if signature is valid, False otherwise
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
            # Try to use Django cache
            requests = cache.get(cache_key, [])
            requests = self._clean_old_requests(requests, current_time)

            if len(requests) >= self.max_requests:
                logger.warning(
                    f"Rate limit exceeded for {identifier}: "
                    f"{len(requests)}/{self.max_requests} requests"
                )
                return False

            requests.append(current_time)
            cache.set(cache_key, requests, self.window + 10)
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
        payment_id: str | int,
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
