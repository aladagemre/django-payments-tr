"""Tests for payment provider abstraction."""

import pytest

from payments_tr.providers import (
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
    registry,
)
from payments_tr.providers.base import BuyerInfo


class TestPaymentResult:
    """Tests for PaymentResult dataclass."""

    def test_success_result(self):
        """Test successful payment result."""
        result = PaymentResult(
            success=True,
            provider_payment_id="pay_123",
            client_secret="secret_123",
            status="succeeded",
        )
        assert result.success is True
        assert result.provider_payment_id == "pay_123"
        assert result.error_message is None

    def test_failure_result(self):
        """Test failed payment result."""
        result = PaymentResult(
            success=False,
            error_message="Card declined",
            error_code="card_declined",
        )
        assert result.success is False
        assert result.error_message == "Card declined"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = PaymentResult(
            success=True,
            provider_payment_id="pay_123",
            status="succeeded",
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["provider_payment_id"] == "pay_123"
        assert "raw_response" not in data  # Should be excluded


class TestRefundResult:
    """Tests for RefundResult dataclass."""

    def test_success_result(self):
        """Test successful refund result."""
        result = RefundResult(
            success=True,
            provider_refund_id="re_123",
            amount=5000,
            status="succeeded",
        )
        assert result.success is True
        assert result.amount == 5000


class TestWebhookResult:
    """Tests for WebhookResult dataclass."""

    def test_success_result(self):
        """Test successful webhook result."""
        result = WebhookResult(
            success=True,
            event_type="payment.succeeded",
            payment_id=123,
            status="succeeded",
        )
        assert result.success is True
        assert result.event_type == "payment.succeeded"


class TestBuyerInfo:
    """Tests for BuyerInfo dataclass."""

    def test_creation(self):
        """Test BuyerInfo creation."""
        buyer = BuyerInfo(
            email="test@example.com",
            name="Test",
            surname="User",
        )
        assert buyer.email == "test@example.com"
        assert buyer.name == "Test"

    def test_to_dict(self):
        """Test conversion to dictionary for iyzico."""
        buyer = BuyerInfo(
            email="test@example.com",
            name="Test",
            surname="User",
            city="Istanbul",
        )
        data = buyer.to_dict()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test"
        assert data["city"] == "Istanbul"
        assert "gsmNumber" in data  # iyzico field name

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
        }
        buyer = BuyerInfo.from_dict(data)
        assert buyer.email == "test@example.com"
        assert buyer.name == "Test"
        assert buyer.surname == "User"


class TestProviderRegistry:
    """Tests for provider registry."""

    def setup_method(self):
        """Clear registry before each test."""
        registry.clear()

    def test_register_provider(self):
        """Test registering a provider."""

        class TestProvider(PaymentProvider):
            provider_name = "test"

            def create_payment(self, payment, **kwargs):
                return PaymentResult(success=True)

            def confirm_payment(self, provider_payment_id):
                return PaymentResult(success=True)

            def create_refund(self, payment, amount=None, reason="", **kwargs):
                return RefundResult(success=True)

            def handle_webhook(self, payload, signature=None, **kwargs):
                return WebhookResult(success=True)

            def get_payment_status(self, provider_payment_id):
                return "succeeded"

        registry.register("test", TestProvider)
        assert registry.is_registered("test")
        assert "test" in registry.list_providers()

    def test_get_unknown_provider(self):
        """Test getting unknown provider raises error."""
        with pytest.raises(ValueError) as exc_info:
            registry.get("unknown")
        assert "Unknown payment provider" in str(exc_info.value)

    def test_unregister_provider(self):
        """Test unregistering a provider."""

        class TestProvider(PaymentProvider):
            provider_name = "test"

            def create_payment(self, payment, **kwargs):
                pass

            def confirm_payment(self, provider_payment_id):
                pass

            def create_refund(self, payment, amount=None, reason="", **kwargs):
                pass

            def handle_webhook(self, payload, signature=None, **kwargs):
                pass

            def get_payment_status(self, provider_payment_id):
                pass

        registry.register("test", TestProvider)
        assert registry.is_registered("test")

        registry.unregister("test")
        assert not registry.is_registered("test")

    def test_case_insensitive(self):
        """Test provider names are case insensitive."""

        class TestProvider(PaymentProvider):
            provider_name = "test"

            def create_payment(self, payment, **kwargs):
                pass

            def confirm_payment(self, provider_payment_id):
                pass

            def create_refund(self, payment, amount=None, reason="", **kwargs):
                pass

            def handle_webhook(self, payload, signature=None, **kwargs):
                pass

            def get_payment_status(self, provider_payment_id):
                pass

        registry.register("TEST", TestProvider)
        assert registry.is_registered("test")
        assert registry.is_registered("TEST")

    def test_get_provider_instance(self, caplog):
        """Test getting provider instance."""
        import logging

        caplog.set_level(logging.INFO)

        class TestProvider(PaymentProvider):
            provider_name = "test"

            def create_payment(self, payment, **kwargs):
                return PaymentResult(success=True)

            def confirm_payment(self, provider_payment_id):
                return PaymentResult(success=True)

            def create_refund(self, payment, amount=None, reason="", **kwargs):
                return RefundResult(success=True)

            def handle_webhook(self, payload, signature=None, **kwargs):
                return WebhookResult(success=True)

            def get_payment_status(self, provider_payment_id):
                return "succeeded"

        registry.register("test", TestProvider)
        provider = registry.get("test")
        assert isinstance(provider, TestProvider)
        assert "using payment provider" in caplog.text.lower()

    def test_get_class(self):
        """Test getting provider class without instantiation."""

        class TestProvider(PaymentProvider):
            provider_name = "test"

            def create_payment(self, payment, **kwargs):
                pass

            def confirm_payment(self, provider_payment_id):
                pass

            def create_refund(self, payment, amount=None, reason="", **kwargs):
                pass

            def handle_webhook(self, payload, signature=None, **kwargs):
                pass

            def get_payment_status(self, provider_payment_id):
                pass

        registry.register("test", TestProvider)
        provider_class = registry.get_class("test")
        assert provider_class is TestProvider
        assert not isinstance(provider_class, PaymentProvider)  # Not instantiated

    def test_get_class_unknown(self):
        """Test getting unknown provider class raises error."""
        with pytest.raises(ValueError) as exc_info:
            registry.get_class("unknown")
        assert "Unknown payment provider" in str(exc_info.value)

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent provider doesn't raise error."""
        # Should not raise
        registry.unregister("nonexistent")
