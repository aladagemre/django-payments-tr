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
def stripe_adapter(mock_stripe):
    """Create Stripe adapter with mocked module."""
    with patch.dict("sys.modules", {"stripe": mock_stripe}):
        with patch(
            "payments_tr.providers.stripe.StripeAdapter.__init__",
            lambda self: None,
        ):
            from payments_tr.providers.stripe import StripeAdapter

            adapter = StripeAdapter()
            adapter._stripe = mock_stripe
            adapter._webhook_secret = "whsec_test"
            return adapter


class TestStripeAdapter:
    """Tests for StripeAdapter."""

    def test_provider_name(self, stripe_adapter):
        """Test provider name."""
        assert stripe_adapter.provider_name == "stripe"

    def test_create_payment_success(self, stripe_adapter, mock_payment, mock_stripe):
        """Test successful payment creation."""
        mock_stripe.PaymentIntent.create.return_value = MockPaymentIntent()

        result = stripe_adapter.create_payment(mock_payment, currency="TRY")

        assert result.success is True
        assert result.provider_payment_id == "pi_123"
        assert result.client_secret == "secret_123"

    def test_create_payment_with_buyer_info_dict(self, stripe_adapter, mock_payment, mock_stripe):
        """Test payment creation with dict buyer info."""
        mock_stripe.PaymentIntent.create.return_value = MockPaymentIntent()

        result = stripe_adapter.create_payment(
            mock_payment,
            buyer_info={"email": "test@example.com"},
        )

        assert result.success is True
        mock_stripe.PaymentIntent.create.assert_called_once()
        call_kwargs = mock_stripe.PaymentIntent.create.call_args[1]
        assert call_kwargs["receipt_email"] == "test@example.com"

    def test_create_payment_with_buyer_info_object(self, stripe_adapter, mock_payment, mock_stripe):
        """Test payment creation with BuyerInfo object."""
        from payments_tr.providers.base import BuyerInfo

        mock_stripe.PaymentIntent.create.return_value = MockPaymentIntent()
        buyer_info = BuyerInfo(email="buyer@example.com")

        result = stripe_adapter.create_payment(
            mock_payment,
            buyer_info=buyer_info,
        )

        assert result.success is True
        call_kwargs = mock_stripe.PaymentIntent.create.call_args[1]
        assert call_kwargs["receipt_email"] == "buyer@example.com"

    def test_create_payment_stripe_error(self, stripe_adapter, mock_payment, mock_stripe):
        """Test payment creation handles Stripe errors."""
        mock_stripe.PaymentIntent.create.side_effect = MockStripeError("Card declined")

        result = stripe_adapter.create_payment(mock_payment)

        assert result.success is False
        assert "Card declined" in result.error_message

    def test_create_payment_generic_error(self, stripe_adapter, mock_payment, mock_stripe):
        """Test payment creation handles generic errors."""
        mock_stripe.PaymentIntent.create.side_effect = Exception("Unknown error")

        result = stripe_adapter.create_payment(mock_payment)

        assert result.success is False
        assert "Unknown error" in result.error_message

    def test_confirm_payment_success(self, stripe_adapter, mock_stripe):
        """Test successful payment confirmation."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(status="succeeded")

        result = stripe_adapter.confirm_payment("pi_123")

        assert result.success is True
        assert result.status == "succeeded"

    def test_confirm_payment_processing(self, stripe_adapter, mock_stripe):
        """Test payment confirmation with processing status."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(status="processing")

        result = stripe_adapter.confirm_payment("pi_123")

        assert result.success is True

    def test_confirm_payment_not_succeeded(self, stripe_adapter, mock_stripe):
        """Test payment confirmation with non-success status."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(
            status="requires_payment_method"
        )

        result = stripe_adapter.confirm_payment("pi_123")

        assert result.success is False

    def test_confirm_payment_stripe_error(self, stripe_adapter, mock_stripe):
        """Test payment confirmation handles Stripe errors."""
        mock_stripe.PaymentIntent.retrieve.side_effect = MockStripeError("Not found")

        result = stripe_adapter.confirm_payment("pi_123")

        assert result.success is False

    def test_confirm_payment_generic_error(self, stripe_adapter, mock_stripe):
        """Test payment confirmation handles generic errors."""
        mock_stripe.PaymentIntent.retrieve.side_effect = Exception("Error")

        result = stripe_adapter.confirm_payment("pi_123")

        assert result.success is False

    def test_create_refund_success(self, stripe_adapter, mock_payment, mock_stripe):
        """Test successful refund creation."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_adapter.create_refund(mock_payment, amount=5000)

        assert result.success is True
        assert result.provider_refund_id == "re_123"

    def test_create_refund_full(self, stripe_adapter, mock_payment, mock_stripe):
        """Test full refund (no amount specified)."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_adapter.create_refund(mock_payment)

        assert result.success is True
        call_kwargs = mock_stripe.Refund.create.call_args[1]
        assert "amount" not in call_kwargs

    def test_create_refund_with_reason(self, stripe_adapter, mock_payment, mock_stripe):
        """Test refund with reason mapping."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_adapter.create_refund(mock_payment, reason="customer_requested")

        assert result.success is True
        call_kwargs = mock_stripe.Refund.create.call_args[1]
        assert call_kwargs["reason"] == "requested_by_customer"

    def test_create_refund_missing_payment_id(self, stripe_adapter, mock_payment):
        """Test refund fails without payment ID."""
        result = stripe_adapter.create_refund(mock_payment)

        assert result.success is False
        assert "No Stripe payment intent ID" in result.error_message

    def test_create_refund_with_provider_payment_id(
        self, stripe_adapter, mock_payment, mock_stripe
    ):
        """Test refund with provider_payment_id in kwargs."""
        mock_stripe.Refund.create.return_value = MockRefund()

        result = stripe_adapter.create_refund(mock_payment, provider_payment_id="pi_456")

        assert result.success is True

    def test_create_refund_stripe_error(self, stripe_adapter, mock_payment, mock_stripe):
        """Test refund handles Stripe errors."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.side_effect = MockStripeError("Refund failed")

        result = stripe_adapter.create_refund(mock_payment)

        assert result.success is False

    def test_create_refund_generic_error(self, stripe_adapter, mock_payment, mock_stripe):
        """Test refund handles generic errors."""
        mock_payment.stripe_payment_intent_id = "pi_123"
        mock_stripe.Refund.create.side_effect = Exception("Error")

        result = stripe_adapter.create_refund(mock_payment)

        assert result.success is False

    def test_handle_webhook_success(self, stripe_adapter, mock_stripe):
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

        result = stripe_adapter.handle_webhook(b"payload", signature="sig_123")

        assert result.success is True
        assert result.event_type == "payment_intent.succeeded"
        assert result.payment_id == 456

    def test_handle_webhook_missing_signature(self, stripe_adapter):
        """Test webhook fails without signature."""
        result = stripe_adapter.handle_webhook(b"payload")

        assert result.success is False
        assert "Missing Stripe signature" in result.error_message

    def test_handle_webhook_invalid_signature(self, stripe_adapter, mock_stripe):
        """Test webhook handles signature verification error."""
        mock_stripe.Webhook.construct_event.side_effect = (
            mock_stripe.error.SignatureVerificationError("Invalid")
        )

        result = stripe_adapter.handle_webhook(b"payload", signature="bad_sig")

        assert result.success is False
        assert "Invalid signature" in result.error_message

    def test_handle_webhook_generic_error(self, stripe_adapter, mock_stripe):
        """Test webhook handles generic errors."""
        mock_stripe.Webhook.construct_event.side_effect = Exception("Error")

        result = stripe_adapter.handle_webhook(b"payload", signature="sig_123")

        assert result.success is False
        assert result.should_retry is True

    def test_get_payment_status(self, stripe_adapter, mock_stripe):
        """Test getting payment status."""
        mock_stripe.PaymentIntent.retrieve.return_value = MockPaymentIntent(status="succeeded")

        status = stripe_adapter.get_payment_status("pi_123")

        assert status == "succeeded"

    def test_supports_checkout_form(self, stripe_adapter):
        """Test supports_checkout_form returns True."""
        assert stripe_adapter.supports_checkout_form() is True

    def test_supports_redirect(self, stripe_adapter):
        """Test supports_redirect returns True."""
        assert stripe_adapter.supports_redirect() is True

    def test_supports_subscriptions(self, stripe_adapter):
        """Test supports_subscriptions returns True."""
        assert stripe_adapter.supports_subscriptions() is True


class TestStripeAdapterInit:
    """Tests for StripeAdapter initialization."""

    def test_init_missing_api_key(self, caplog, mock_stripe):
        """Test warning when Stripe API key not configured."""
        import logging

        caplog.set_level(logging.WARNING)

        with patch.dict("sys.modules", {"stripe": mock_stripe}):
            with patch("payments_tr.providers.stripe.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = ""  # Empty API key
                mock_settings.STRIPE_WEBHOOK_SECRET = ""

                from payments_tr.providers.stripe import StripeAdapter

                adapter = StripeAdapter()

                # Check warning was logged
                assert "STRIPE_SECRET_KEY not configured" in caplog.text
                assert adapter._stripe.api_key == ""

    def test_init_with_api_key(self, mock_stripe):
        """Test successful initialization with API key."""
        with patch.dict("sys.modules", {"stripe": mock_stripe}):
            with patch("payments_tr.providers.stripe.settings") as mock_settings:
                mock_settings.STRIPE_SECRET_KEY = "sk_test_123"
                mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_123"

                from payments_tr.providers.stripe import StripeAdapter

                adapter = StripeAdapter()

                assert adapter._stripe.api_key == "sk_test_123"
                assert adapter._webhook_secret == "whsec_123"


class TestStripeWebhookEdgeCases:
    """Tests for Stripe webhook edge cases."""

    def test_webhook_payment_id_non_integer_string(self, stripe_adapter, mock_stripe):
        """Test webhook with non-integer payment_id in metadata."""
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_123",
                    "status": "succeeded",
                    "metadata": {"payment_id": "abc123"},  # Non-integer string
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        result = stripe_adapter.handle_webhook(b"payload", signature="sig_123")

        assert result.success is True
        # Should keep as string when ValueError occurs
        assert result.payment_id == "abc123"

    def test_webhook_payment_id_none(self, stripe_adapter, mock_stripe):
        """Test webhook with None payment_id in metadata."""
        mock_event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_123",
                    "status": "succeeded",
                    "metadata": {"payment_id": None},  # None value
                }
            },
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        result = stripe_adapter.handle_webhook(b"payload", signature="sig_123")

        assert result.success is True
        # Should keep as None when TypeError occurs
        assert result.payment_id is None
