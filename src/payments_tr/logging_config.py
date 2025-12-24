"""
Comprehensive logging configuration for payment operations.

This module provides structured logging with different levels and formats
for payment-related operations, making debugging and monitoring easier.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from django.conf import settings


class PaymentLogFilter(logging.Filter):
    """Filter to add payment context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add payment-specific attributes to record."""
        # Add default values if not present
        if not hasattr(record, "payment_id"):
            record.payment_id = None
        if not hasattr(record, "provider"):
            record.provider = None
        if not hasattr(record, "operation"):
            record.operation = None
        return True


class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive data from logs."""

    SENSITIVE_FIELDS = {
        "card_number",
        "cvv",
        "cvc",
        "password",
        "secret",
        "api_key",
        "token",
        "client_secret",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact sensitive data from log message."""
        if hasattr(record, "args") and isinstance(record.args, dict):
            record.args = self._redact_dict(record.args)
        return True

    def _redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact sensitive fields from dictionary."""
        redacted = {}
        for key, value in data.items():
            if key.lower() in self.SENSITIVE_FIELDS:
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self._redact_dict(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                redacted[key] = value
        return redacted


class PaymentLogger:
    """
    Structured logger for payment operations.

    Example:
        >>> logger = PaymentLogger("payments_tr.providers")
        >>> logger.payment_created(payment_id="123", provider="stripe", amount=5000)
        >>> logger.payment_failed(payment_id="123", provider="stripe", error="Card declined")
    """

    def __init__(self, name: str = "payments_tr"):
        """
        Initialize payment logger.

        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)

    def _log_with_context(
        self,
        level: int,
        message: str,
        payment_id: str | int | None = None,
        provider: str | None = None,
        operation: str | None = None,
        **extra: Any,
    ) -> None:
        """Log with payment context."""
        extra_data = {
            "payment_id": payment_id,
            "provider": provider,
            "operation": operation,
            **extra,
        }
        self.logger.log(level, message, extra=extra_data)

    def payment_created(
        self,
        payment_id: str | int,
        provider: str,
        amount: int,
        currency: str = "TRY",
        **extra: Any,
    ) -> None:
        """Log payment creation."""
        self._log_with_context(
            logging.INFO,
            f"Payment created: {payment_id} - {amount/100:.2f} {currency}",
            payment_id=payment_id,
            provider=provider,
            operation="create",
            amount=amount,
            currency=currency,
            **extra,
        )

    def payment_confirmed(
        self,
        payment_id: str | int,
        provider: str,
        provider_payment_id: str | None = None,
        **extra: Any,
    ) -> None:
        """Log payment confirmation."""
        self._log_with_context(
            logging.INFO,
            f"Payment confirmed: {payment_id}",
            payment_id=payment_id,
            provider=provider,
            operation="confirm",
            provider_payment_id=provider_payment_id,
            **extra,
        )

    def payment_failed(
        self,
        payment_id: str | int,
        provider: str,
        error: str,
        error_code: str | None = None,
        **extra: Any,
    ) -> None:
        """Log payment failure."""
        self._log_with_context(
            logging.ERROR,
            f"Payment failed: {payment_id} - {error}",
            payment_id=payment_id,
            provider=provider,
            operation="confirm",
            error=error,
            error_code=error_code,
            **extra,
        )

    def refund_created(
        self,
        payment_id: str | int,
        provider: str,
        amount: int | None,
        reason: str = "",
        **extra: Any,
    ) -> None:
        """Log refund creation."""
        amount_str = f"{amount/100:.2f}" if amount is not None else "full"
        self._log_with_context(
            logging.INFO,
            f"Refund created: {payment_id} - {amount_str}",
            payment_id=payment_id,
            provider=provider,
            operation="refund",
            amount=amount,
            reason=reason,
            **extra,
        )

    def webhook_received(
        self,
        provider: str,
        event_type: str,
        event_id: str | None = None,
        **extra: Any,
    ) -> None:
        """Log webhook received."""
        self._log_with_context(
            logging.INFO,
            f"Webhook received: {provider} - {event_type}",
            provider=provider,
            operation="webhook",
            event_type=event_type,
            event_id=event_id,
            **extra,
        )

    def webhook_processed(
        self,
        provider: str,
        event_type: str,
        success: bool,
        **extra: Any,
    ) -> None:
        """Log webhook processing result."""
        level = logging.INFO if success else logging.ERROR
        status = "successfully" if success else "with errors"
        self._log_with_context(
            level,
            f"Webhook processed {status}: {provider} - {event_type}",
            provider=provider,
            operation="webhook",
            event_type=event_type,
            success=success,
            **extra,
        )

    def api_call(
        self,
        provider: str,
        endpoint: str,
        method: str = "POST",
        **extra: Any,
    ) -> None:
        """Log API call to provider."""
        self._log_with_context(
            logging.DEBUG,
            f"API call: {method} {provider}/{endpoint}",
            provider=provider,
            operation="api_call",
            endpoint=endpoint,
            method=method,
            **extra,
        )

    def api_response(
        self,
        provider: str,
        endpoint: str,
        status_code: int,
        duration_ms: float | None = None,
        **extra: Any,
    ) -> None:
        """Log API response from provider."""
        level = logging.INFO if status_code < 400 else logging.ERROR
        duration_str = f" ({duration_ms:.0f}ms)" if duration_ms else ""
        self._log_with_context(
            level,
            f"API response: {provider}/{endpoint} - {status_code}{duration_str}",
            provider=provider,
            operation="api_response",
            endpoint=endpoint,
            status_code=status_code,
            duration_ms=duration_ms,
            **extra,
        )


def configure_logging(
    debug: bool = False,
    log_level: str | None = None,
    log_file: str | None = None,
    enable_sensitive_filter: bool = True,
) -> None:
    """
    Configure logging for payments_tr package.

    Args:
        debug: Enable debug mode with verbose logging
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
        enable_sensitive_filter: Enable sensitive data filtering

    Example:
        >>> # In Django settings.py or apps.py
        >>> from payments_tr.logging_config import configure_logging
        >>> configure_logging(debug=DEBUG, log_level='INFO')
    """
    # Determine log level
    if log_level is None:
        log_level = "DEBUG" if debug else "INFO"

    # Get or create logger
    logger = logging.getLogger("payments_tr")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Create formatters
    if debug:
        # Detailed format for debugging
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s [%(name)s.%(funcName)s:%(lineno)d] "
            "[payment=%(payment_id)s provider=%(provider)s op=%(operation)s] "
            "%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        # Production format
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(provider)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(PaymentLogFilter())
    if enable_sensitive_filter:
        console_handler.addFilter(SensitiveDataFilter())
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(PaymentLogFilter())
        if enable_sensitive_filter:
            file_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(file_handler)

    logger.info(f"Logging configured: level={log_level}, debug={debug}")


def get_logger(name: str = "payments_tr") -> PaymentLogger:
    """
    Get a configured payment logger.

    Args:
        name: Logger name

    Returns:
        PaymentLogger instance

    Example:
        >>> from payments_tr.logging_config import get_logger
        >>> logger = get_logger()
        >>> logger.payment_created(payment_id=123, provider="stripe", amount=5000)
    """
    return PaymentLogger(name)


# Django integration
def setup_django_logging() -> None:
    """
    Set up logging configuration from Django settings.

    Add this to your Django app's AppConfig.ready() method:

    Example:
        >>> from django.apps import AppConfig
        >>>
        >>> class MyAppConfig(AppConfig):
        ...     def ready(self):
        ...         from payments_tr.logging_config import setup_django_logging
        ...         setup_django_logging()
    """
    try:
        payments_settings = getattr(settings, "PAYMENTS_TR", {})
        logging_config = payments_settings.get("LOGGING", {})

        configure_logging(
            debug=logging_config.get("DEBUG", settings.DEBUG),
            log_level=logging_config.get("LEVEL"),
            log_file=logging_config.get("FILE"),
            enable_sensitive_filter=logging_config.get("FILTER_SENSITIVE_DATA", True),
        )
    except Exception as e:
        # Fallback to basic configuration
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("payments_tr").warning(f"Failed to configure logging from settings: {e}")
