"""Tests for configuration validation."""

import os
import tempfile
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from payments_tr.config import (
    ValidationError,
    ValidationResult,
    SettingsValidator,
    validate_settings,
    get_setting,
    check_configuration,
)


class TestValidationError:
    """Test ValidationError class."""

    def test_validation_error_str(self):
        """Test string representation of ValidationError."""
        error = ValidationError("field_name", "Error message", "error")
        assert str(error) == "[ERROR] field_name: Error message"

    def test_validation_error_default_severity(self):
        """Test default severity is error."""
        error = ValidationError("field_name", "Error message")
        assert error.severity == "error"
        assert str(error) == "[ERROR] field_name: Error message"


class TestValidationResult:
    """Test ValidationResult class."""

    def test_validation_result_add_error(self):
        """Test adding errors to validation result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert not result.has_errors()

        result.add_error("field1", "Error 1")
        assert result.valid is False
        assert result.has_errors()
        assert len(result.errors) == 1
        assert result.errors[0].field == "field1"
        assert result.errors[0].message == "Error 1"

    def test_validation_result_add_warning(self):
        """Test adding warnings to validation result."""
        result = ValidationResult(valid=True)
        assert not result.has_warnings()

        result.add_warning("field1", "Warning 1")
        assert result.valid is True  # Warnings don't change valid status
        assert result.has_warnings()
        assert len(result.warnings) == 1
        assert result.warnings[0].field == "field1"
        assert result.warnings[0].message == "Warning 1"

    def test_validation_result_multiple_errors(self):
        """Test multiple errors."""
        result = ValidationResult(valid=True)
        result.add_error("field1", "Error 1")
        result.add_error("field2", "Error 2")
        assert len(result.errors) == 2
        assert result.has_errors()


class TestSettingsValidator:
    """Test SettingsValidator class."""

    def test_validator_init_no_settings(self):
        """Test validator initialization without PAYMENTS_TR settings."""
        with patch("payments_tr.config.settings") as mock_settings:
            del mock_settings.PAYMENTS_TR
            validator = SettingsValidator()
            assert validator.settings == {}

    def test_validator_init_with_settings(self):
        """Test validator initialization with PAYMENTS_TR settings."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"DEFAULT_PROVIDER": "stripe"}
            validator = SettingsValidator()
            assert validator.settings == {"DEFAULT_PROVIDER": "stripe"}

    def test_validate_default_settings(self):
        """Test validation with default settings."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert not result.has_errors()

    def test_validate_unknown_provider_warning(self):
        """Test warning for unknown default provider."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"DEFAULT_PROVIDER": "unknown"}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert result.has_warnings()
            assert any("Unknown provider" in str(w) for w in result.warnings)

    def test_validate_stripe_api_key_empty(self):
        """Test error for empty Stripe API key."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": ""}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("empty" in str(e).lower() for e in result.errors)

    def test_validate_stripe_api_key_not_string(self):
        """Test error for non-string Stripe API key."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": 12345}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("must be a string" in str(e) for e in result.errors)

    def test_validate_stripe_api_key_invalid_format(self):
        """Test warning for invalid Stripe API key format."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": "invalid_key_format"}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert result.has_warnings()
            assert any("should start with" in str(w) for w in result.warnings)

    def test_validate_stripe_api_key_test_valid(self):
        """Test valid Stripe test API key."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": "sk_test_123456"}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert not result.has_warnings()

    def test_validate_stripe_api_key_live_valid(self):
        """Test valid Stripe live API key."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": "sk_live_123456"}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert not result.has_warnings()

    def test_validate_stripe_webhook_secret_empty(self):
        """Test error for empty Stripe webhook secret."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_WEBHOOK_SECRET": ""}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("empty" in str(e).lower() for e in result.errors)

    def test_validate_stripe_webhook_secret_not_string(self):
        """Test error for non-string Stripe webhook secret."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_WEBHOOK_SECRET": 12345}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("must be a string" in str(e) for e in result.errors)

    def test_validate_stripe_webhook_secret_invalid_format(self):
        """Test warning for invalid Stripe webhook secret format."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_WEBHOOK_SECRET": "invalid_secret"}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert result.has_warnings()
            assert any("should start with 'whsec_'" in str(w) for w in result.warnings)

    def test_validate_stripe_webhook_secret_valid(self):
        """Test valid Stripe webhook secret."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_WEBHOOK_SECRET": "whsec_123456"}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert not result.has_warnings()

    def test_validate_iyzico_api_key_empty(self):
        """Test error for empty iyzico API key."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"IYZICO_API_KEY": ""}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()

    def test_validate_iyzico_secret_key_empty(self):
        """Test error for empty iyzico secret key."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"IYZICO_SECRET_KEY": ""}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()

    def test_validate_security_not_dict(self):
        """Test error when SECURITY is not a dictionary."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": "not_a_dict"}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("must be a dictionary" in str(e) for e in result.errors)

    def test_validate_security_rate_limit_requests_invalid(self):
        """Test error for invalid rate limit requests."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"RATE_LIMIT_REQUESTS": -1}}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("positive integer" in str(e) for e in result.errors)

    def test_validate_security_rate_limit_requests_not_int(self):
        """Test error for non-integer rate limit requests."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"RATE_LIMIT_REQUESTS": "100"}}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()

    def test_validate_security_rate_limit_window_invalid(self):
        """Test error for invalid rate limit window."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"RATE_LIMIT_WINDOW": 0}}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()

    def test_validate_security_verify_webhooks_disabled_warning(self):
        """Test warning when webhook verification is disabled."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"VERIFY_WEBHOOKS": False}}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert result.has_warnings()
            assert any("insecure" in str(w).lower() for w in result.warnings)

    def test_validate_security_iyzico_webhook_secret_missing_warning(self):
        """Test warning when iyzico webhook secret is missing."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {
                "IYZICO_API_KEY": "test_key",
                "SECURITY": {"VERIFY_WEBHOOKS": True},
            }
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert result.has_warnings()
            assert any("webhook secret not configured" in str(w) for w in result.warnings)

    def test_validate_logging_not_dict(self):
        """Test error when LOGGING is not a dictionary."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"LOGGING": "not_a_dict"}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("must be a dictionary" in str(e) for e in result.errors)

    def test_validate_logging_level_not_string(self):
        """Test error when log level is not a string."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"LOGGING": {"LEVEL": 123}}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("must be a string" in str(e) for e in result.errors)

    def test_validate_logging_level_invalid(self):
        """Test error for invalid log level."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"LOGGING": {"LEVEL": "INVALID"}}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("Invalid log level" in str(e) for e in result.errors)

    def test_validate_logging_level_valid(self):
        """Test valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            with patch("payments_tr.config.settings") as mock_settings:
                mock_settings.PAYMENTS_TR = {"LOGGING": {"LEVEL": level}}
                validator = SettingsValidator()
                result = validator.validate()
                assert result.valid is True
                assert not result.has_errors()

    def test_validate_logging_file_missing_directory(self):
        """Test warning for non-existent log directory."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"LOGGING": {"FILE": "/nonexistent/dir/file.log"}}
            validator = SettingsValidator()
            result = validator.validate()
            assert result.valid is True
            assert result.has_warnings()
            assert any("does not exist" in str(w) for w in result.warnings)

    def test_validate_logging_file_existing_directory(self):
        """Test no warning for existing log directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            with patch("payments_tr.config.settings") as mock_settings:
                mock_settings.PAYMENTS_TR = {"LOGGING": {"FILE": log_file}}
                validator = SettingsValidator()
                result = validator.validate()
                assert result.valid is True
                assert not result.has_warnings()

    def test_validate_webhook_model_invalid_format(self):
        """Test error for invalid webhook model format."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"WEBHOOK_MODEL": "InvalidFormat"}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("app_label.ModelName" in str(e) for e in result.errors)

    def test_validate_webhook_model_not_found(self):
        """Test error when webhook model cannot be loaded."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"WEBHOOK_MODEL": "nonexistent.Model"}
            validator = SettingsValidator()
            result = validator.validate()
            assert not result.valid
            assert result.has_errors()
            assert any("Failed to load model" in str(e) for e in result.errors)

    def test_validate_raise_on_error(self):
        """Test raise_on_error parameter."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": ""}
            validator = SettingsValidator()

            # Should raise when raise_on_error=True
            with pytest.raises(ImproperlyConfigured) as exc_info:
                validator.validate(raise_on_error=True)
            assert "validation failed" in str(exc_info.value).lower()

            # Should not raise when raise_on_error=False
            result = validator.validate(raise_on_error=False)
            assert not result.valid


class TestValidateSettings:
    """Test validate_settings function."""

    def test_validate_settings_function(self):
        """Test validate_settings convenience function."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            result = validate_settings()
            assert isinstance(result, ValidationResult)
            assert result.valid is True

    def test_validate_settings_raise_on_error(self):
        """Test validate_settings with raise_on_error."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": ""}

            with pytest.raises(ImproperlyConfigured):
                validate_settings(raise_on_error=True)


class TestGetSetting:
    """Test get_setting function."""

    def test_get_setting_simple_key(self):
        """Test getting a simple setting."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"DEFAULT_PROVIDER": "stripe"}
            assert get_setting("DEFAULT_PROVIDER") == "stripe"

    def test_get_setting_default(self):
        """Test getting setting with default value."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            assert get_setting("NONEXISTENT", "default_value") == "default_value"

    def test_get_setting_nested_key(self):
        """Test getting a nested setting with dot notation."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"RATE_LIMIT_REQUESTS": 100}}
            assert get_setting("SECURITY.RATE_LIMIT_REQUESTS") == 100

    def test_get_setting_nested_default(self):
        """Test getting nested setting with default."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {}}
            assert get_setting("SECURITY.NONEXISTENT", 50) == 50

    def test_get_setting_nested_not_dict(self):
        """Test getting nested setting when parent is not a dict."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": "not_a_dict"}
            assert get_setting("SECURITY.RATE_LIMIT_REQUESTS", 50) == 50

    def test_get_setting_no_payments_tr(self):
        """Test getting setting when PAYMENTS_TR doesn't exist."""
        with patch("payments_tr.config.settings") as mock_settings:
            del mock_settings.PAYMENTS_TR
            assert get_setting("DEFAULT_PROVIDER", "stripe") == "stripe"

    def test_get_setting_none_value(self):
        """Test that None values are returned (not replaced with default for simple keys)."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"DEFAULT_PROVIDER": None}
            # For simple keys, None is returned as-is
            assert get_setting("DEFAULT_PROVIDER", "stripe") is None

    def test_get_setting_none_value_nested(self):
        """Test that None values return default for nested keys."""
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"RATE_LIMIT": None}}
            # For nested keys, None is replaced with default
            assert get_setting("SECURITY.RATE_LIMIT", 100) == 100


class TestCheckConfiguration:
    """Test check_configuration function."""

    def test_check_configuration_valid(self, caplog):
        """Test check_configuration with valid settings."""
        import logging

        caplog.set_level(logging.INFO)
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            check_configuration()
            assert "configuration is valid" in caplog.text.lower()

    def test_check_configuration_errors(self, caplog):
        """Test check_configuration with errors."""
        import logging

        caplog.set_level(logging.ERROR)
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"STRIPE_API_KEY": ""}
            check_configuration()
            assert "error" in caplog.text.lower()

    def test_check_configuration_warnings(self, caplog):
        """Test check_configuration with warnings."""
        import logging

        caplog.set_level(logging.WARNING)
        with patch("payments_tr.config.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"DEFAULT_PROVIDER": "unknown"}
            check_configuration()
            assert "warning" in caplog.text.lower()
