"""Tests for security utilities."""

import hashlib
import hmac
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.utils import timezone as django_timezone

from payments_tr.security import (
    AuditLogEntry,
    AuditLogger,
    IdempotencyManager,
    IyzicoWebhookVerifier,
    RateLimiter,
    SecurityConfig,
    idempotent,
)


class TestSecurityConfig:
    """Test SecurityConfig class."""

    def test_security_config_defaults(self):
        """Test default security configuration values."""
        config = SecurityConfig()
        assert config.iyzico_webhook_secret == ""
        assert config.verify_webhooks is True
        assert config.enable_rate_limiting is True
        assert config.rate_limit_requests == 100
        assert config.rate_limit_window == 60
        assert config.enable_audit_log is True
        assert config.audit_log_sensitive_data is False

    def test_security_config_from_settings_empty(self):
        """Test loading config from empty settings."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            config = SecurityConfig.from_settings()
            assert config.iyzico_webhook_secret == ""
            assert config.verify_webhooks is True

    def test_security_config_from_settings_custom(self):
        """Test loading config from custom settings."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {
                "SECURITY": {
                    "IYZICO_WEBHOOK_SECRET": "test_secret",
                    "VERIFY_WEBHOOKS": False,
                    "ENABLE_RATE_LIMITING": False,
                    "RATE_LIMIT_REQUESTS": 200,
                    "RATE_LIMIT_WINDOW": 120,
                    "ENABLE_AUDIT_LOG": False,
                    "AUDIT_LOG_SENSITIVE_DATA": True,
                }
            }
            config = SecurityConfig.from_settings()
            assert config.iyzico_webhook_secret == "test_secret"
            assert config.verify_webhooks is False
            assert config.enable_rate_limiting is False
            assert config.rate_limit_requests == 200
            assert config.rate_limit_window == 120
            assert config.enable_audit_log is False
            assert config.audit_log_sensitive_data is True


class TestIyzicoWebhookVerifier:
    """Test IyzicoWebhookVerifier class."""

    def test_verifier_init_with_secret(self):
        """Test initializing verifier with explicit secret."""
        verifier = IyzicoWebhookVerifier(secret="test_secret")
        assert verifier.secret == "test_secret"

    def test_verifier_init_from_settings(self):
        """Test initializing verifier from settings."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {
                "SECURITY": {"IYZICO_WEBHOOK_SECRET": "settings_secret"}
            }
            verifier = IyzicoWebhookVerifier()
            assert verifier.secret == "settings_secret"

    def test_verifier_init_no_secret_warning(self, caplog):
        """Test warning when no secret is configured."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            verifier = IyzicoWebhookVerifier()
            assert verifier.secret == ""
            assert "webhook secret not configured" in caplog.text.lower()

    def test_compute_signature(self):
        """Test computing HMAC signature."""
        verifier = IyzicoWebhookVerifier(secret="test_secret")
        payload = b"test payload"
        signature = verifier.compute_signature(payload)

        # Verify signature format
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest

        # Verify signature is correct
        expected = hmac.new(
            b"test_secret", payload, hashlib.sha256
        ).hexdigest()
        assert signature == expected

    def test_compute_signature_no_secret(self):
        """Test computing signature without secret raises error."""
        verifier = IyzicoWebhookVerifier(secret="")
        with pytest.raises(ValueError, match="secret not configured"):
            verifier.compute_signature(b"test")

    def test_verify_valid_signature(self):
        """Test verifying valid signature."""
        secret = "test_secret"
        verifier = IyzicoWebhookVerifier(secret=secret)
        payload = b"test payload"

        # Generate valid signature
        signature = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

        assert verifier.verify(payload, signature) is True

    def test_verify_invalid_signature(self):
        """Test verifying invalid signature."""
        verifier = IyzicoWebhookVerifier(secret="test_secret")
        payload = b"test payload"
        invalid_signature = "invalid_signature_hex"

        assert verifier.verify(payload, invalid_signature) is False

    def test_verify_no_secret(self, caplog):
        """Test verifying without secret returns False."""
        verifier = IyzicoWebhookVerifier(secret="")
        assert verifier.verify(b"test", "signature") is False
        assert "cannot verify webhook" in caplog.text.lower()

    def test_verify_exception_handling(self, caplog):
        """Test that verification errors are caught and logged."""
        verifier = IyzicoWebhookVerifier(secret="test_secret")

        # Mock compute_signature to raise an exception
        with patch.object(verifier, "compute_signature", side_effect=Exception("Test error")):
            result = verifier.verify(b"test", "signature")
            assert result is False
            assert "error verifying webhook signature" in caplog.text.lower()


class TestRateLimiter:
    """Test RateLimiter class."""

    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()

    def test_rate_limiter_init_defaults(self):
        """Test rate limiter initialization with defaults."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            limiter = RateLimiter()
            assert limiter.max_requests == 100
            assert limiter.window == 60
            assert limiter.enabled is True

    def test_rate_limiter_init_custom(self):
        """Test rate limiter initialization with custom values."""
        limiter = RateLimiter(max_requests=50, window=30)
        assert limiter.max_requests == 50
        assert limiter.window == 30

    def test_rate_limiter_disabled(self):
        """Test that disabled rate limiter always allows requests."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"ENABLE_RATE_LIMITING": False}}
            limiter = RateLimiter()
            assert limiter.enabled is False

            # Should allow unlimited requests when disabled
            for _ in range(200):
                assert limiter.allow("test-id") is True

    def test_rate_limiter_allow_within_limit(self):
        """Test allowing requests within rate limit."""
        limiter = RateLimiter(max_requests=5, window=60)

        # First 5 requests should be allowed
        for i in range(5):
            assert limiter.allow("test-id") is True

    def test_rate_limiter_block_over_limit(self, caplog):
        """Test blocking requests over rate limit."""
        limiter = RateLimiter(max_requests=3, window=60)

        # First 3 requests allowed
        for i in range(3):
            assert limiter.allow("test-id") is True

        # 4th request should be blocked
        assert limiter.allow("test-id") is False
        assert "rate limit exceeded" in caplog.text.lower()

    def test_rate_limiter_separate_identifiers(self):
        """Test that different identifiers have separate rate limits."""
        limiter = RateLimiter(max_requests=2, window=60)

        # Two requests for each identifier should be allowed
        assert limiter.allow("id1") is True
        assert limiter.allow("id1") is True
        assert limiter.allow("id2") is True
        assert limiter.allow("id2") is True

        # Third request for each should be blocked
        assert limiter.allow("id1") is False
        assert limiter.allow("id2") is False

    def test_rate_limiter_window_expiry(self):
        """Test that rate limit window expires."""
        limiter = RateLimiter(max_requests=2, window=1)  # 1 second window

        # Use up the limit
        assert limiter.allow("test-id") is True
        assert limiter.allow("test-id") is True
        assert limiter.allow("test-id") is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        assert limiter.allow("test-id") is True

    def test_rate_limiter_reset(self):
        """Test resetting rate limit for identifier."""
        limiter = RateLimiter(max_requests=2, window=60)

        # Use up the limit
        assert limiter.allow("test-id") is True
        assert limiter.allow("test-id") is True
        assert limiter.allow("test-id") is False

        # Reset and try again
        limiter.reset("test-id")
        assert limiter.allow("test-id") is True

    def test_rate_limiter_cache_fallback(self, caplog):
        """Test fallback to in-memory storage on cache error."""
        limiter = RateLimiter(max_requests=2, window=60)

        # Mock cache to raise exception
        with patch("payments_tr.security.cache.get", side_effect=Exception("Cache error")):
            assert limiter.allow("test-id") is True
            assert "cache error" in caplog.text.lower()

            # Should still work with in-memory storage
            assert limiter.allow("test-id") is True
            assert limiter.allow("test-id") is False

    def test_rate_limiter_get_cache_key(self):
        """Test cache key generation."""
        limiter = RateLimiter(cache_prefix="test:prefix")
        key = limiter._get_cache_key("identifier")
        assert key == "test:prefix:identifier"

    def test_rate_limiter_clean_old_requests(self):
        """Test cleaning old requests outside window."""
        limiter = RateLimiter(max_requests=10, window=60)
        current_time = time.time()

        requests = [
            current_time - 120,  # 2 minutes ago (outside window)
            current_time - 90,   # 1.5 minutes ago (outside window)
            current_time - 30,   # 30 seconds ago (inside window)
            current_time - 10,   # 10 seconds ago (inside window)
        ]

        cleaned = limiter._clean_old_requests(requests, current_time)
        assert len(cleaned) == 2  # Only the last 2 requests


class TestAuditLogEntry:
    """Test AuditLogEntry dataclass."""

    def test_audit_log_entry_creation(self):
        """Test creating audit log entry."""
        timestamp = django_timezone.now()
        entry = AuditLogEntry(
            timestamp=timestamp,
            operation="refund",
            user="admin",
            payment_id="pay_123",
            provider="stripe",
            success=True,
            details={"amount": 5000},
            ip_address="192.168.1.1",
        )

        assert entry.timestamp == timestamp
        assert entry.operation == "refund"
        assert entry.user == "admin"
        assert entry.payment_id == "pay_123"
        assert entry.provider == "stripe"
        assert entry.success is True
        assert entry.details == {"amount": 5000}
        assert entry.ip_address == "192.168.1.1"

    def test_audit_log_entry_to_dict(self):
        """Test converting audit log entry to dictionary."""
        timestamp = django_timezone.now()
        entry = AuditLogEntry(
            timestamp=timestamp,
            operation="refund",
            user="admin",
            payment_id="pay_123",
            provider="stripe",
            success=True,
            details={"amount": 5000},
        )

        entry_dict = entry.to_dict()
        assert entry_dict["timestamp"] == timestamp.isoformat()
        assert entry_dict["operation"] == "refund"
        assert entry_dict["user"] == "admin"
        assert entry_dict["payment_id"] == "pay_123"
        assert entry_dict["provider"] == "stripe"
        assert entry_dict["success"] is True
        assert entry_dict["details"] == {"amount": 5000}


class TestAuditLogger:
    """Test AuditLogger class."""

    def test_audit_logger_init(self):
        """Test audit logger initialization."""
        logger = AuditLogger()
        assert logger.logger.name == "payments_tr.audit"

    def test_audit_logger_init_custom_name(self):
        """Test audit logger with custom name."""
        logger = AuditLogger(logger_name="custom.audit")
        assert logger.logger.name == "custom.audit"

    def test_audit_logger_disabled(self, caplog):
        """Test that disabled audit logger doesn't log."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"ENABLE_AUDIT_LOG": False}}
            logger = AuditLogger()
            assert logger.enabled is False

            entry = AuditLogEntry(
                timestamp=django_timezone.now(),
                operation="test",
                user="admin",
                payment_id="123",
                provider="stripe",
                success=True,
            )
            logger.log(entry)

            # Nothing should be logged
            assert "Audit:" not in caplog.text

    def test_audit_logger_log_success(self, caplog):
        """Test logging successful operation."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"ENABLE_AUDIT_LOG": True}}
            logger = AuditLogger()

            entry = AuditLogEntry(
                timestamp=django_timezone.now(),
                operation="refund",
                user="admin",
                payment_id="pay_123",
                provider="stripe",
                success=True,
            )
            logger.log(entry)

            assert "Audit: refund" in caplog.text

    def test_audit_logger_log_failure(self, caplog):
        """Test logging failed operation."""
        import logging

        caplog.set_level(logging.WARNING)

        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {"SECURITY": {"ENABLE_AUDIT_LOG": True}}
            logger = AuditLogger()

            entry = AuditLogEntry(
                timestamp=django_timezone.now(),
                operation="refund",
                user="admin",
                payment_id="pay_123",
                provider="stripe",
                success=False,
            )
            logger.log(entry)

            assert "Audit: refund FAILED" in caplog.text

    def test_audit_logger_redact_sensitive_data(self):
        """Test redacting sensitive data."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {
                "SECURITY": {
                    "ENABLE_AUDIT_LOG": True,
                    "AUDIT_LOG_SENSITIVE_DATA": False,
                }
            }
            logger = AuditLogger()

            entry = AuditLogEntry(
                timestamp=django_timezone.now(),
                operation="payment",
                user="user",
                payment_id="123",
                provider="stripe",
                success=True,
                details={
                    "amount": 5000,
                    "card_number": "4242424242424242",
                    "cvv": "123",
                },
            )

            # Mock the logger to capture log calls
            with patch.object(logger.logger, "info") as mock_log:
                logger.log(entry)

                # Verify log was called
                assert mock_log.called

                # Check that details were redacted
                call_args = mock_log.call_args
                log_data = call_args[1]["extra"]
                assert log_data["details"]["card_number"] == "***REDACTED***"
                assert log_data["details"]["cvv"] == "***REDACTED***"
                assert log_data["details"]["amount"] == 5000  # Not redacted

    def test_audit_logger_log_sensitive_data_enabled(self):
        """Test logging sensitive data when enabled."""
        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {
                "SECURITY": {
                    "ENABLE_AUDIT_LOG": True,
                    "AUDIT_LOG_SENSITIVE_DATA": True,
                }
            }
            logger = AuditLogger()
            assert logger.log_sensitive is True

    def test_audit_logger_log_refund(self, caplog):
        """Test logging refund operation."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            logger = AuditLogger()

            logger.log_refund(
                user="admin",
                payment_id="pay_123",
                provider="stripe",
                success=True,
                amount=5000,
                reason="Customer request",
                ip_address="192.168.1.1",
            )

            assert "refund" in caplog.text.lower()

    def test_audit_logger_log_eft_approval(self, caplog):
        """Test logging EFT approval."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            logger = AuditLogger()

            logger.log_eft_approval(
                user="admin",
                payment_id="eft_123",
                approved=True,
                success=True,
                reason="Verified",
                ip_address="192.168.1.1",
            )

            assert "eft_approve" in caplog.text.lower()

    def test_audit_logger_log_eft_rejection(self, caplog):
        """Test logging EFT rejection."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            logger = AuditLogger()

            logger.log_eft_approval(
                user="admin",
                payment_id="eft_123",
                approved=False,
                success=True,
                reason="Invalid receipt",
                ip_address="192.168.1.1",
            )

            assert "eft_reject" in caplog.text.lower()

    def test_audit_logger_log_webhook(self, caplog):
        """Test logging webhook processing."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("payments_tr.security.settings") as mock_settings:
            mock_settings.PAYMENTS_TR = {}
            logger = AuditLogger()

            logger.log_webhook(
                provider="stripe",
                event_type="payment.succeeded",
                payment_id="pay_123",
                success=True,
                ip_address="54.187.174.169",
            )

            assert "webhook" in caplog.text.lower()


class TestIdempotencyManager:
    """Test IdempotencyManager class."""

    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()

    def test_idempotency_manager_init(self):
        """Test idempotency manager initialization."""
        manager = IdempotencyManager()
        assert manager.ttl == 86400  # 24 hours
        assert manager.cache_prefix == "payments_tr:idempotency"

    def test_idempotency_manager_init_custom(self):
        """Test idempotency manager with custom values."""
        manager = IdempotencyManager(ttl=3600, cache_prefix="custom:prefix")
        assert manager.ttl == 3600
        assert manager.cache_prefix == "custom:prefix"

    def test_idempotency_manager_check_new_key(self):
        """Test checking new idempotency key returns True."""
        manager = IdempotencyManager()
        assert manager.check("new-key-123") is True

    def test_idempotency_manager_check_existing_key(self, caplog):
        """Test checking existing idempotency key returns False."""
        import logging

        caplog.set_level(logging.INFO)
        manager = IdempotencyManager()

        # First check should return True
        assert manager.check("existing-key") is True

        # Mark as processed
        manager.mark_processed("existing-key")

        # Second check should return False
        assert manager.check("existing-key") is False
        assert "idempotent operation detected" in caplog.text.lower()

    def test_idempotency_manager_mark_processed(self):
        """Test marking operation as processed."""
        manager = IdempotencyManager()

        # Initially should be new
        assert manager.check("test-key") is True

        # Mark as processed
        manager.mark_processed("test-key")

        # Should now be detected as duplicate
        assert manager.check("test-key") is False

    def test_idempotency_manager_cache_fallback(self, caplog):
        """Test fallback to in-memory storage on cache error."""
        manager = IdempotencyManager()

        # Mock cache to raise exception
        with patch("payments_tr.security.cache.get", side_effect=Exception("Cache error")):
            assert manager.check("test-key") is True
            assert "cache error" in caplog.text.lower()

            # Mark as processed in memory
            manager.mark_processed("test-key")

        # Should still detect duplicate with in-memory storage
        with patch("payments_tr.security.cache.get", side_effect=Exception("Cache error")):
            assert manager.check("test-key") is False

    def test_idempotency_manager_ttl_expiry(self):
        """Test that old entries are cleaned from memory store."""
        manager = IdempotencyManager(ttl=1)  # 1 second TTL

        # Add entry to memory store
        with patch("payments_tr.security.cache.get", side_effect=Exception("Cache error")):
            manager.check("test-key")
            manager.mark_processed("test-key")

        # Wait for TTL to expire
        time.sleep(1.1)

        # Check again - should clean old entries and return True
        with patch("payments_tr.security.cache.get", side_effect=Exception("Cache error")):
            assert manager.check("test-key") is True

    def test_idempotency_manager_get_cache_key(self):
        """Test cache key generation."""
        manager = IdempotencyManager(cache_prefix="test:prefix")
        key = manager._get_cache_key("my-key")
        assert key == "test:prefix:my-key"


class TestIdempotentDecorator:
    """Test idempotent decorator."""

    def setup_method(self):
        """Clear cache before each test."""
        cache.clear()

    def test_idempotent_decorator_basic(self):
        """Test basic idempotent decorator functionality."""
        call_count = {"value": 0}

        @idempotent(lambda webhook_id: f"webhook:{webhook_id}")
        def process_webhook(webhook_id):
            call_count["value"] += 1
            return f"processed:{webhook_id}"

        # First call should execute
        result1 = process_webhook("123")
        assert result1 == "processed:123"
        assert call_count["value"] == 1

        # Second call with same ID should be skipped
        result2 = process_webhook("123")
        assert result2 is None
        assert call_count["value"] == 1  # Not incremented

        # Call with different ID should execute
        result3 = process_webhook("456")
        assert result3 == "processed:456"
        assert call_count["value"] == 2

    def test_idempotent_decorator_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""

        @idempotent(lambda x: f"key:{x}")
        def my_function(x):
            """My function docstring."""
            return x

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My function docstring."

    def test_idempotent_decorator_with_multiple_args(self):
        """Test idempotent decorator with multiple arguments."""
        call_count = {"value": 0}

        @idempotent(lambda a, b: f"op:{a}:{b}")
        def operation(a, b):
            call_count["value"] += 1
            return a + b

        # First call
        assert operation(1, 2) == 3
        assert call_count["value"] == 1

        # Duplicate call
        assert operation(1, 2) is None
        assert call_count["value"] == 1

        # Different args
        assert operation(2, 3) == 5
        assert call_count["value"] == 2

    def test_idempotent_decorator_with_kwargs(self):
        """Test idempotent decorator with keyword arguments."""
        call_count = {"value": 0}

        @idempotent(lambda **kwargs: f"key:{kwargs.get('id')}")
        def process(id=None, data=None):
            call_count["value"] += 1
            return data

        # First call
        assert process(id="123", data="value") == "value"
        assert call_count["value"] == 1

        # Duplicate
        assert process(id="123", data="value") is None
        assert call_count["value"] == 1
