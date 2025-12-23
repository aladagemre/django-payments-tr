"""
Django REST Framework serializers for payments.

These serializers provide ready-to-use DRF serializers for payment
operations. Requires djangorestframework to be installed.
"""

from __future__ import annotations

from typing import Any

try:
    from rest_framework import serializers
except ImportError as e:
    raise ImportError(
        "djangorestframework is required for payments_tr.contrib.serializers. "
        "Install it with: pip install djangorestframework"
    ) from e

from payments_tr.providers.base import BuyerInfo, PaymentResult, RefundResult


class BuyerInfoSerializer(serializers.Serializer):
    """Serializer for buyer information."""

    id = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=True)
    name = serializers.CharField(required=False, allow_blank=True)
    surname = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    identity_number = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    country = serializers.CharField(required=False, default="Turkey")
    zip_code = serializers.CharField(required=False, allow_blank=True)
    ip = serializers.IPAddressField(required=False)

    def create(self, validated_data: dict[str, Any]) -> BuyerInfo:
        """Create BuyerInfo from validated data."""
        return BuyerInfo(**validated_data)


class PaymentIntentCreateSerializer(serializers.Serializer):
    """Serializer for creating a payment intent."""

    currency = serializers.CharField(default="TRY", max_length=3)
    callback_url = serializers.URLField(required=False, allow_null=True)
    buyer_info = BuyerInfoSerializer(required=False, allow_null=True)

    # Additional buyer fields for convenience
    buyer_name = serializers.CharField(required=False, allow_blank=True)
    buyer_surname = serializers.CharField(required=False, allow_blank=True)
    buyer_phone = serializers.CharField(required=False, allow_blank=True)
    buyer_address = serializers.CharField(required=False, allow_blank=True)
    buyer_city = serializers.CharField(required=False, allow_blank=True)
    buyer_country = serializers.CharField(required=False, default="Turkey")


class PaymentResultSerializer(serializers.Serializer):
    """Serializer for payment result response."""

    success = serializers.BooleanField()
    provider_payment_id = serializers.CharField(allow_null=True)
    client_secret = serializers.CharField(allow_null=True)
    checkout_url = serializers.URLField(allow_null=True)
    token = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    error_message = serializers.CharField(allow_null=True)
    error_code = serializers.CharField(allow_null=True)

    @classmethod
    def from_result(cls, result: PaymentResult) -> PaymentResultSerializer:
        """Create serializer from PaymentResult."""
        return cls(data=result.to_dict())


class RefundCreateSerializer(serializers.Serializer):
    """Serializer for creating a refund."""

    amount = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Amount to refund in smallest currency unit. Omit for full refund.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text="Reason for the refund.",
    )


class RefundResultSerializer(serializers.Serializer):
    """Serializer for refund result response."""

    success = serializers.BooleanField()
    provider_refund_id = serializers.CharField(allow_null=True)
    amount = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()
    error_message = serializers.CharField(allow_null=True)
    error_code = serializers.CharField(allow_null=True)

    @classmethod
    def from_result(cls, result: RefundResult) -> RefundResultSerializer:
        """Create serializer from RefundResult."""
        return cls(data=result.to_dict())


class EFTPaymentCreateSerializer(serializers.Serializer):
    """Serializer for creating an EFT payment."""

    bank_name = serializers.CharField(max_length=100)
    reference_number = serializers.CharField(max_length=100)
    transfer_date = serializers.DateField()
    sender_name = serializers.CharField(max_length=200)
    receipt = serializers.FileField(required=False, allow_null=True)


class IyzicoCallbackSerializer(serializers.Serializer):
    """Serializer for iyzico callback data."""

    token = serializers.CharField(required=True)
