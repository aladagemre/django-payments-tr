"""Tests for Stripe payment provider."""

from unittest.mock import MagicMock, patch

import pytest


class MockPaymentIntent:
    """Mock Stripe PaymentIntent."""

    def __init__(self, id="pi_123", status="requires_payment_method"):
        self.id = id
        self.status = status
        self.client_secret = "secret_123"

    def __iter__(self):
        return iter(
            {
                "id": self.id,
                "status": self.status,
                "client_secret": self.client_secret,
            }.items()
        )


class MockRefund:
    """Mock Stripe Refund."""

    def __init__(self, id="re_123", status="succeeded", amount=5000):
        self.id = id
        self.status = status
        self.amount = amount

    def __iter__(self):
        return iter(
            {
                "id": self.id,
                "status": self.status,
                "amount": self.amount,
            }.items()
        )


class MockStripeError(Exception):
    """Mock Stripe error."""

    def __init__(self, message="Stripe error", code="stripe_error"):
        super().__init__(message)
        self.code = code


class MockStripeModule:
    """Mock Stripe module."""

    def __init__(self):
        self.api_key = None
        self.PaymentIntent = MagicMock()
        self.Refund = MagicMock()
        self.Webhook = MagicMock()
        self.error = MagicMock()
        self.error.StripeError = MockStripeError
        self.error.SignatureVerificationError = type("SignatureVerificationError", (Exception,), {})


@pytest.fixture
def mock_stripe():
    """Create mock Stripe module."""
    return MockStripeModule()


@pytest.fixture
def stripe_provider(mock_stripe):
    """Create Stripe provider with mocked module."""
    with patch.dict("sys.modules", {"stripe": mock_stripe}):
        with patch(
            "payments_tr.providers.stripe.StripeProvider.__init__",
            lambda self: None,
        ):
            from payments_tr.providers.stripe import StripeProvider

            provider = StripeProvider()
            provider._stripe = mock_stripe
            provider._webhook_secret = "whsec_test"
            return provider


class TestStripeProvider:
    """Tests for StripeProvider."""

    def test_provider_name(self, stripe_provider):
        """Test provider name."""
        assert stripe_provider.provider_name == "stripe"

    def test_create_payment_success(self, stripe_provider, mock_payment, mock_stripe):
        """Test successful payment creation."""
        mock_stripe.PaymentIntent.create.return_value = MockPaymentIntent()

        result = stripe_provider.create_payment(mock_payment, currency="TRY")

        assert result.success is True
        assert result.provider_payment_id == "pi_123"
        assert result.client_secret == "secret_123"

    def test_create_payment_with_buyer_info_dict(self, stripe_provider, mock_payment, mock_stripe):
        """Test payment creation with dict buyer info."""
        mock_stripe.PaymentIntent.create.return_value = MockPaymentIntent()

        result = stripe_provider.create_payment(
            mock_payment,
            buyer_info={"email": "test@example.com"},
        )

        assert result.success is True
        mock_stripe.PaymentIntent.create.assert_called_once()
        call_kwargs = mock_stripe.PaymentIntent.create.call_args[1]
        assert call_kwargs["receipt_email"] == "test@example.com"

    def test_create_payment_with_buyer_info_object(
        self, stripe_provider, mock_payment, mock_stripe
    ):
        """Test payment creation with BuyerInfo object."""
        from payments_tr.providers.base import BuyerInfo

        mock_stripe.PaymentIntent.create.return_value = MockPaymentIntent()
        buyer_info = BuyerInfo(email="buyer@example.com")

        result = stripe_provider.create_payment(
            mock_payment,
            buyer_info=buyer_info,
        )

        assert result.success is True
        call_kwargs = mock_stripe.PaymentIntent.create.call_args[1]
        assert call_kwargs["receipt_email"] == "buyer@example.com"

    def test_create_payment_stripe_error(self, stripe_provider, mock_payment, mock_stripe):
        """Test payment creation handles Stripe errors."""
        mock_stripe.PaymentIntent.create.side_effect = MockStripeError("Card declined")

        result = stripe_provider.create_payment(mock_payment)

        assert result.success is False
        assert "Card declined" in result.error_message

    def test_create_payment_generic_error(self, stripe_provider, mock_payment, mock_stripe):
        """Test payment creation handles generic errors."""
        mock_stripe.PaymentIntent.create.side_effect = Exception("Unknown error")

        result = stripe_provider.create_payment(mock_payment)

        assert result.success is False
        assert "Unknown error" in result.error_message

    def test_confirm_payment_success(self, stripe_provider, mock_stripe):
        """Test successful payment confirmation."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(status="succeeded")

        result = stripe_provider.confirm_payment("pi_123")

        assert result.success is True
        assert result.status == "succeeded"

    def test_confirm_payment_processing(self, stripe_provider, mock_stripe):
        """Test payment confirmation with processing status."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(status="processing")

        result = stripe_provider.confirm_payment("pi_123")

        assert result.success is True

    def test_confirm_payment_not_succeeded(self, stripe_provider, mock_stripe):
        """Test payment confirmation with non-success status."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(
            status="requires_payment_method"
        )

        result = stripe_provider.confirm_payment("pi_123")

        assert result.success is False

    def test_confirm_payment_stripe_error(self, stripe_provider, mock_stripe):
        """Test payment confirmation handles Stripe errors."""
        mock_stripe.PaymentIntent.retrieve.side_effect = MockStripeError("Not found")

        result = stripe_provider.confirm_payment("pi_123")

        assert result.success is False

    def test_confirm_payment_generic_error(self, stripe_provider, mock_stripe):
        """Test payment confirmation handles generic errors."""
        mock_stripe.PaymentIntent.retrieve.side_effect = Exception("Error")

        result = stripe_provider.confirm_payment("pi_123")

        assert result.success is False

    def test_create_refund_success(self, stripe_provider, mock_payment, mock_stripe):
        """Test successful refund creation."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_provider.create_refund(mock_payment, amount=5000)

        assert result.success is True
        assert result.provider_refund_id == "re_123"

    def test_create_refund_full(self, stripe_provider, mock_payment, mock_stripe):
        """Test full refund (no amount specified)."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_provider.create_refund(mock_payment)

        assert result.success is True
        call_kwargs = mock_stripe.Refund.create.call_args[1]
        assert "amount" not in call_kwargs

    def test_create_refund_with_reason(self, stripe_provider, mock_payment, mock_stripe):
        """Test refund with reason mapping."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_provider.create_refund(mock_payment, reason="customer_requested")

        assert result.success is True
        call_kwargs = mock_stripe.Refund.create.call_args[1]
        assert call_kwargs["reason"] == "requested_by_customer"

    def test_create_refund_missing_payment_id(self, stripe_provider, mock_payment):
        """Test refund fails without payment ID."""
        result = stripe_provider.create_refund(mock_payment)

        assert result.success is False
        assert "No Stripe payment intent ID" in result.error_message

    def test_create_refund_with_provider_payment_id(
        self, stripe_provider, mock_payment, mock_stripe
    ):
        """Test refund with provider_payment_id in kwargs."""
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_provider.create_refund(mock_payment, provider_payment_id="pi_456")

        assert result.success is True

    def test_create_refund_stripe_error(self, stripe_provider, mock_payment, mock_stripe):
        """Test refund handles Stripe errors."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.side_effect = MockStripeError("Refund failed")

        result = stripe_provider.create_refund(mock_payment)

        assert result.success is False

    def test_create_refund_generic_error(self, stripe_provider, mock_payment, mock_stripe):
        """Test refund handles generic errors."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.side_effect = Exception("Error")

        result = stripe_provider.create_refund(mock_payment)

        assert result.success is False

    def test_handle_webhook_success(self, stripe_provider, mock_stripe):
        """Test successful webhook handling."""
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_123",
                    "status": "succeeded",
                    "metadata": {"payment_id": "456"},
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        result = stripe_provider.handle_webhook(b"payload", signature="sig_123")

        assert result.success is True
        assert result.event_type == "payment_intent.succeeded"
        assert result.payment_id == 456

    def test_handle_webhook_missing_signature(self, stripe_provider):
        """Test webhook fails without signature."""
        result = stripe_provider.handle_webhook(b"payload")

        assert result.success is False
        assert "Missing Stripe signature" in result.error_message

    def test_handle_webhook_invalid_signature(self, stripe_provider, mock_stripe):
        """Test webhook handles signature verification error."""
        mock_stripe.Webhook.construct_event.side_effect = (
            mock_stripe.error.SignatureVerificationError("Invalid")
        )

        result = stripe_provider.handle_webhook(b"payload", signature="bad_sig")

        assert result.success is False
        assert "Invalid signature" in result.error_message

    def test_handle_webhook_generic_error(self, stripe_provider, mock_stripe):
        """Test webhook handles generic errors."""
        mock_stripe.Webhook.construct_event.side_effect = Exception("Error")

        result = stripe_provider.handle_webhook(b"payload", signature="sig_123")

        assert result.success is False
        assert result.should_retry is True

    def test_get_payment_status(self, stripe_provider, mock_stripe):
        """Test getting payment status."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(status="succeeded")

        status = stripe_provider.get_payment_status("pi_123")

        assert status == "succeeded"

    def test_supports_checkout_form(self, stripe_provider):
        """Test supports_checkout_form returns True."""
        assert stripe_provider.supports_checkout_form() is True

    def test_supports_redirect(self, stripe_provider):
        """Test supports_redirect returns True."""
        assert stripe_provider.supports_redirect() is True

    def test_supports_subscriptions(self, stripe_provider):
        """Test supports_subscriptions returns True."""
        assert stripe_provider.supports_subscriptions() is True
