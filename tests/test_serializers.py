"""Tests for DRF serializers."""

import pytest

# Skip all tests if DRF is not installed
pytest.importorskip("rest_framework")

from payments_tr.contrib.serializers import (
    BuyerInfoSerializer,
    EFTPaymentCreateSerializer,
    IyzicoCallbackSerializer,
    PaymentIntentCreateSerializer,
    PaymentResultSerializer,
    RefundCreateSerializer,
    RefundResultSerializer,
)
from payments_tr.providers.base import BuyerInfo, PaymentResult, RefundResult


class TestBuyerInfoSerializer:
    """Tests for BuyerInfoSerializer."""

    def test_valid_buyer_info(self):
        """Test valid buyer info serialization."""
        data = {
            "email": "test@example.com",
            "name": "John",
            "surname": "Doe",
            "phone": "+905551234567",
            "city": "Istanbul",
            "country": "Turkey",
        }
        serializer = BuyerInfoSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_minimal_buyer_info(self):
        """Test minimal buyer info (email only)."""
        data = {"email": "test@example.com"}
        serializer = BuyerInfoSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_invalid_email(self):
        """Test invalid email is rejected."""
        data = {"email": "not-an-email"}
        serializer = BuyerInfoSerializer(data=data)
        assert not serializer.is_valid()
        assert "email" in serializer.errors

    def test_missing_email(self):
        """Test missing email is rejected."""
        data = {"name": "John"}
        serializer = BuyerInfoSerializer(data=data)
        assert not serializer.is_valid()
        assert "email" in serializer.errors

    def test_create_buyer_info(self):
        """Test creating BuyerInfo from serializer."""
        data = {
            "email": "test@example.com",
            "name": "John",
            "surname": "Doe",
        }
        serializer = BuyerInfoSerializer(data=data)
        assert serializer.is_valid()
        buyer_info = serializer.save()
        assert isinstance(buyer_info, BuyerInfo)
        assert buyer_info.email == "test@example.com"
        assert buyer_info.name == "John"


class TestPaymentIntentCreateSerializer:
    """Tests for PaymentIntentCreateSerializer."""

    def test_default_values(self):
        """Test default values are applied."""
        serializer = PaymentIntentCreateSerializer(data={})
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["currency"] == "TRY"

    def test_custom_currency(self):
        """Test custom currency."""
        data = {"currency": "USD"}
        serializer = PaymentIntentCreateSerializer(data=data)
        assert serializer.is_valid()
        assert serializer.validated_data["currency"] == "USD"

    def test_with_callback_url(self):
        """Test with callback URL."""
        data = {"callback_url": "https://example.com/callback"}
        serializer = PaymentIntentCreateSerializer(data=data)
        assert serializer.is_valid()

    def test_with_buyer_info(self):
        """Test with nested buyer info."""
        data = {
            "buyer_info": {
                "email": "test@example.com",
                "name": "John",
            }
        }
        serializer = PaymentIntentCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_with_convenience_fields(self):
        """Test with convenience buyer fields."""
        data = {
            "buyer_name": "John",
            "buyer_surname": "Doe",
            "buyer_phone": "+905551234567",
        }
        serializer = PaymentIntentCreateSerializer(data=data)
        assert serializer.is_valid()


class TestPaymentResultSerializer:
    """Tests for PaymentResultSerializer."""

    def test_success_result(self):
        """Test serializing success result."""
        data = {
            "success": True,
            "provider_payment_id": "pi_123",
            "client_secret": "secret_123",
            "checkout_url": None,
            "token": None,
            "status": "succeeded",
            "error_message": None,
            "error_code": None,
        }
        serializer = PaymentResultSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_failure_result(self):
        """Test serializing failure result."""
        data = {
            "success": False,
            "provider_payment_id": None,
            "client_secret": None,
            "checkout_url": None,
            "token": None,
            "status": "failed",
            "error_message": "Card declined",
            "error_code": "CARD_DECLINED",
        }
        serializer = PaymentResultSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_from_result_classmethod(self):
        """Test creating serializer from PaymentResult."""
        result = PaymentResult(
            success=True,
            provider_payment_id="pi_123",
            status="succeeded",
        )
        serializer = PaymentResultSerializer.from_result(result)
        assert serializer.initial_data["success"] is True


class TestRefundCreateSerializer:
    """Tests for RefundCreateSerializer."""

    def test_full_refund(self):
        """Test full refund (no amount)."""
        data = {}
        serializer = RefundCreateSerializer(data=data)
        assert serializer.is_valid()

    def test_partial_refund(self):
        """Test partial refund with amount."""
        data = {"amount": 5000, "reason": "Customer request"}
        serializer = RefundCreateSerializer(data=data)
        assert serializer.is_valid()

    def test_invalid_amount(self):
        """Test invalid amount (zero or negative)."""
        data = {"amount": 0}
        serializer = RefundCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "amount" in serializer.errors


class TestRefundResultSerializer:
    """Tests for RefundResultSerializer."""

    def test_success_result(self):
        """Test serializing success result."""
        data = {
            "success": True,
            "provider_refund_id": "re_123",
            "amount": 5000,
            "status": "succeeded",
            "error_message": None,
            "error_code": None,
        }
        serializer = RefundResultSerializer(data=data)
        assert serializer.is_valid()

    def test_from_result_classmethod(self):
        """Test creating serializer from RefundResult."""
        result = RefundResult(
            success=True,
            provider_refund_id="re_123",
            amount=5000,
            status="succeeded",
        )
        serializer = RefundResultSerializer.from_result(result)
        assert serializer.initial_data["success"] is True


class TestEFTPaymentCreateSerializer:
    """Tests for EFTPaymentCreateSerializer."""

    def test_valid_eft_payment(self):
        """Test valid EFT payment data."""
        data = {
            "bank_name": "Test Bank",
            "reference_number": "REF123456",
            "transfer_date": "2025-01-15",
            "sender_name": "John Doe",
        }
        serializer = EFTPaymentCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_required_fields(self):
        """Test missing required fields."""
        data = {"bank_name": "Test Bank"}
        serializer = EFTPaymentCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "reference_number" in serializer.errors


class TestIyzicoCallbackSerializer:
    """Tests for IyzicoCallbackSerializer."""

    def test_valid_callback(self):
        """Test valid callback data."""
        data = {"token": "checkout_token_123"}
        serializer = IyzicoCallbackSerializer(data=data)
        assert serializer.is_valid()

    def test_missing_token(self):
        """Test missing token."""
        data = {}
        serializer = IyzicoCallbackSerializer(data=data)
        assert not serializer.is_valid()
        assert "token" in serializer.errors
