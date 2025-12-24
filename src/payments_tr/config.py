"""
Settings validation and configuration management.

This module provides utilities to validate Django settings for payments_tr
and provide helpful error messages for misconfiguration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Configuration validation error."""

    field: str
    message: str
    severity: str = "error"  # error, warning, info

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.field}: {self.message}"


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def add_error(self, field: str, message: str) -> None:
        """Add validation error."""
        self.valid = False
        self.errors.append(ValidationError(field, message, "error"))

    def add_warning(self, field: str, message: str) -> None:
        """Add validation warning."""
        self.warnings.append(ValidationError(field, message, "warning"))

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0


class SettingsValidator:
    """
    Validator for PAYMENTS_TR settings.

    Example:
        >>> from payments_tr.config import SettingsValidator
        >>> validator = SettingsValidator()
        >>> result = validator.validate()
        >>> if not result.valid:
        ...     for error in result.errors:
        ...         print(error)
    """

    REQUIRED_SETTINGS = []  # No required settings, all optional
    OPTIONAL_SETTINGS = [
        "DEFAULT_PROVIDER",
        "SECURITY",
        "LOGGING",
        "STRIPE_API_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "IYZICO_API_KEY",
        "IYZICO_SECRET_KEY",
        "WEBHOOK_MODEL",
    ]

    def __init__(self):
        """Initialize validator."""
        self.settings = getattr(settings, "PAYMENTS_TR", {})

    def validate(self, raise_on_error: bool = False) -> ValidationResult:
        """
        Validate all settings.

        Args:
            raise_on_error: Raise ImproperlyConfigured on validation errors

        Returns:
            ValidationResult with errors and warnings

        Raises:
            ImproperlyConfigured: If raise_on_error=True and validation fails
        """
        result = ValidationResult(valid=True)

        # Validate provider settings
        self._validate_provider_settings(result)

        # Validate security settings
        self._validate_security_settings(result)

        # Validate logging settings
        self._validate_logging_settings(result)

        # Validate webhook settings
        self._validate_webhook_settings(result)

        if raise_on_error and result.has_errors():
            error_messages = "\n".join(str(e) for e in result.errors)
            raise ImproperlyConfigured(
                f"PAYMENTS_TR settings validation failed:\n{error_messages}"
            )

        return result

    def _validate_provider_settings(self, result: ValidationResult) -> None:
        """Validate provider configuration."""
        default_provider = self.settings.get("DEFAULT_PROVIDER", "stripe")

        # Check if default provider is valid
        valid_providers = ["stripe", "iyzico"]
        if default_provider not in valid_providers:
            result.add_warning(
                "DEFAULT_PROVIDER",
                f"Unknown provider '{default_provider}'. "
                f"Valid providers: {', '.join(valid_providers)}",
            )

        # Validate Stripe settings
        if "STRIPE_API_KEY" in self.settings:
            api_key = self.settings["STRIPE_API_KEY"]
            if not api_key:
                result.add_error("STRIPE_API_KEY", "Stripe API key is empty")
            elif not (api_key.startswith("sk_test_") or api_key.startswith("sk_live_")):
                result.add_warning(
                    "STRIPE_API_KEY",
                    "Stripe API key should start with 'sk_test_' or 'sk_live_'",
                )

        if "STRIPE_WEBHOOK_SECRET" in self.settings:
            secret = self.settings["STRIPE_WEBHOOK_SECRET"]
            if not secret:
                result.add_error("STRIPE_WEBHOOK_SECRET", "Stripe webhook secret is empty")
            elif not secret.startswith("whsec_"):
                result.add_warning(
                    "STRIPE_WEBHOOK_SECRET",
                    "Stripe webhook secret should start with 'whsec_'",
                )

        # Validate iyzico settings
        if "IYZICO_API_KEY" in self.settings and not self.settings["IYZICO_API_KEY"]:
            result.add_error("IYZICO_API_KEY", "iyzico API key is empty")

        if "IYZICO_SECRET_KEY" in self.settings and not self.settings["IYZICO_SECRET_KEY"]:
            result.add_error("IYZICO_SECRET_KEY", "iyzico secret key is empty")

    def _validate_security_settings(self, result: ValidationResult) -> None:
        """Validate security configuration."""
        security = self.settings.get("SECURITY", {})

        if not isinstance(security, dict):
            result.add_error("SECURITY", "SECURITY must be a dictionary")
            return

        # Validate rate limiting settings
        if "RATE_LIMIT_REQUESTS" in security:
            rate_limit = security["RATE_LIMIT_REQUESTS"]
            if not isinstance(rate_limit, int) or rate_limit <= 0:
                result.add_error(
                    "SECURITY.RATE_LIMIT_REQUESTS",
                    "Must be a positive integer",
                )

        if "RATE_LIMIT_WINDOW" in security:
            window = security["RATE_LIMIT_WINDOW"]
            if not isinstance(window, int) or window <= 0:
                result.add_error(
                    "SECURITY.RATE_LIMIT_WINDOW",
                    "Must be a positive integer (seconds)",
                )

        # Check webhook verification
        verify_webhooks = security.get("VERIFY_WEBHOOKS", True)
        if not verify_webhooks:
            result.add_warning(
                "SECURITY.VERIFY_WEBHOOKS",
                "Webhook verification is disabled - this is insecure!",
            )

        # Check if webhook secret is configured when verification is enabled
        if verify_webhooks:
            iyzico_secret = security.get("IYZICO_WEBHOOK_SECRET")
            if not iyzico_secret and "IYZICO_API_KEY" in self.settings:
                result.add_warning(
                    "SECURITY.IYZICO_WEBHOOK_SECRET",
                    "iyzico webhook secret not configured - webhook verification will fail",
                )

    def _validate_logging_settings(self, result: ValidationResult) -> None:
        """Validate logging configuration."""
        logging_config = self.settings.get("LOGGING", {})

        if not isinstance(logging_config, dict):
            result.add_error("LOGGING", "LOGGING must be a dictionary")
            return

        # Validate log level
        if "LEVEL" in logging_config:
            level = logging_config["LEVEL"]
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if not isinstance(level, str):
                result.add_error(
                    "LOGGING.LEVEL",
                    f"Log level must be a string, got {type(level).__name__}",
                )
            elif level.upper() not in valid_levels:
                result.add_error(
                    "LOGGING.LEVEL",
                    f"Invalid log level '{level}'. Valid levels: {', '.join(valid_levels)}",
                )

        # Check log file path
        if "FILE" in logging_config:
            log_file = logging_config["FILE"]
            if log_file:
                import os

                log_dir = os.path.dirname(log_file)
                if log_dir and not os.path.exists(log_dir):
                    result.add_warning(
                        "LOGGING.FILE",
                        f"Log directory does not exist: {log_dir}",
                    )

    def _validate_webhook_settings(self, result: ValidationResult) -> None:
        """Validate webhook configuration."""
        webhook_model = self.settings.get("WEBHOOK_MODEL")

        if webhook_model:
            # Validate model path format
            if "." not in webhook_model:
                result.add_error(
                    "WEBHOOK_MODEL",
                    "Must be in format 'app_label.ModelName'",
                )
            else:
                # Try to load the model
                try:
                    from django.apps import apps

                    app_label, model_name = webhook_model.rsplit(".", 1)
                    apps.get_model(app_label, model_name)
                except Exception as e:
                    result.add_error(
                        "WEBHOOK_MODEL",
                        f"Failed to load model: {e}",
                    )


def validate_settings(raise_on_error: bool = False) -> ValidationResult:
    """
    Validate PAYMENTS_TR settings.

    Args:
        raise_on_error: Raise ImproperlyConfigured on validation errors

    Returns:
        ValidationResult with errors and warnings

    Example:
        >>> from payments_tr.config import validate_settings
        >>> result = validate_settings()
        >>> if result.has_errors():
        ...     print("Configuration errors:")
        ...     for error in result.errors:
        ...         print(f"  - {error}")
    """
    validator = SettingsValidator()
    return validator.validate(raise_on_error=raise_on_error)


def get_setting(key: str, default: Any = None) -> Any:
    """
    Get a PAYMENTS_TR setting value.

    Args:
        key: Setting key (can use dot notation for nested keys)
        default: Default value if key not found

    Returns:
        Setting value or default

    Example:
        >>> from payments_tr.config import get_setting
        >>> provider = get_setting('DEFAULT_PROVIDER', 'stripe')
        >>> rate_limit = get_setting('SECURITY.RATE_LIMIT_REQUESTS', 100)
    """
    payments_settings = getattr(settings, "PAYMENTS_TR", {})

    # Handle dot notation
    if "." in key:
        keys = key.split(".")
        value = payments_settings
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    return payments_settings.get(key, default)


def check_configuration() -> None:
    """
    Check configuration and print warnings/errors.

    This function is useful to call in AppConfig.ready() to ensure
    configuration is correct at startup.

    Example:
        >>> from django.apps import AppConfig
        >>>
        >>> class MyAppConfig(AppConfig):
        ...     def ready(self):
        ...         from payments_tr.config import check_configuration
        ...         check_configuration()
    """
    result = validate_settings(raise_on_error=False)

    if result.has_errors():
        logger.error("PAYMENTS_TR configuration errors:")
        for error in result.errors:
            logger.error(f"  - {error}")

    if result.has_warnings():
        logger.warning("PAYMENTS_TR configuration warnings:")
        for warning in result.warnings:
            logger.warning(f"  - {warning}")

    if result.valid and not result.has_warnings():
        logger.info("PAYMENTS_TR configuration is valid")
