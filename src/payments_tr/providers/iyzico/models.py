"""
Django models for django-iyzico.

Provides iyzico-specific abstract models that extend the base payment models
from payments-tr.

Architecture:
    payments_tr.AbstractPayment (provider-agnostic base)
        └── AbstractIyzicoPayment (iyzico-specific extensions)
"""

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

# Import base classes from payments-tr
from payments_tr.models import (
    AbstractPayment,
    PaymentManager,
    PaymentProviderChoices,
    PaymentQuerySet,
    PaymentStatus,
)

from .utils import extract_card_info, mask_card_data, sanitize_log_data

# Re-export for backward compatibility
# Users can import from payments_tr.providers.iyzico.models or payments_tr.models
__all__ = [
    # From payments_tr (re-exported)
    "PaymentStatus",
    "PaymentProviderChoices",
    "PaymentQuerySet",
    "PaymentManager",
    "AbstractPayment",
    # iyzico-specific
    "IyzicoPaymentQuerySet",
    "IyzicoPaymentManager",
    "AbstractIyzicoPayment",
]

# Backward compatibility alias
PaymentProvider = PaymentProviderChoices


class IyzicoPaymentQuerySet(PaymentQuerySet):
    """Custom QuerySet for Iyzico payments."""

    def by_payment_id(self, payment_id: str):
        """Get payment by Iyzico payment ID (alias for provider_payment_id)."""
        return self.filter(provider_payment_id=payment_id)

    def by_conversation_id(self, conversation_id: str):
        """Get payments by conversation ID."""
        return self.filter(conversation_id=conversation_id)

    def by_token(self, token: str):
        """Get payment by checkout form token."""
        return self.filter(token=token)


class IyzicoPaymentManager(PaymentManager):
    """Custom manager for Iyzico payments."""

    def get_queryset(self):
        """Return custom QuerySet."""
        return IyzicoPaymentQuerySet(self.model, using=self._db)

    def get_by_payment_id(self, payment_id: str):
        """
        Get payment by Iyzico payment ID.

        Args:
            payment_id: Iyzico payment ID

        Returns:
            Payment instance

        Raises:
            DoesNotExist: If payment not found
        """
        return self.get(provider_payment_id=payment_id)

    def get_by_conversation_id(self, conversation_id: str):
        """
        Get payment by conversation ID.

        Args:
            conversation_id: Conversation ID

        Returns:
            Payment instance (first match) or None if not found
        """
        return self.filter(conversation_id=conversation_id).first()

    def get_by_token(self, token: str):
        """
        Get payment by checkout form token.

        Args:
            token: Checkout form token

        Returns:
            Payment instance or None if not found
        """
        return self.filter(token=token).first()


class AbstractIyzicoPayment(AbstractPayment):
    """
    Abstract base model for Iyzico payments.

    Extends AbstractPayment with iyzico-specific fields for:
    - Checkout form tokens
    - Conversation IDs
    - Card information (non-sensitive, PCI DSS compliant)
    - Installment details (Turkish market)
    - Locale settings

    Example:
        class Order(AbstractIyzicoPayment):
            user = models.ForeignKey(User, on_delete=models.CASCADE)
            product = models.ForeignKey(Product, on_delete=models.CASCADE)
            quantity = models.IntegerField()

            class Meta:
                db_table = 'orders'

    This provides all Iyzico payment fields and functionality while letting you
    add your own business-specific fields.
    """

    # iyzico-specific IDs
    conversation_id = models.CharField(
        max_length=255,
        db_index=True,
        null=True,
        blank=True,
        verbose_name=_("Conversation ID"),
        help_text=_("Unique conversation ID for tracking this payment"),
    )
    token = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Checkout Token"),
        help_text=_("Checkout form token"),
    )
    locale = models.CharField(
        max_length=5,
        default="tr",
        verbose_name=_("Locale"),
        help_text=_("Locale for the payment (e.g., tr, en)"),
    )

    # Card information (non-sensitive only - PCI DSS compliant)
    card_last_four_digits = models.CharField(
        max_length=4,
        null=True,
        blank=True,
        verbose_name=_("Card Last 4 Digits"),
        help_text=_("Last 4 digits of card number"),
    )
    card_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Card Type"),
        help_text=_("Card type (e.g., CREDIT_CARD, DEBIT_CARD)"),
    )
    card_association = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Card Association"),
        help_text=_("Card association (e.g., VISA, MASTER_CARD, AMEX)"),
    )
    card_family = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Card Family"),
        help_text=_("Card family/program (e.g., Bonus, Axess, Maximum)"),
    )
    card_bank_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("Card Bank Name"),
        help_text=_("Issuing bank name"),
    )
    card_bank_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Card Bank Code"),
        help_text=_("Issuing bank code"),
    )
    bin_number = models.CharField(
        max_length=6,
        null=True,
        blank=True,
        verbose_name=_("BIN Number"),
        help_text=_("First 6 digits of card (Bank Identification Number)"),
    )

    # Installment details (Turkish market feature)
    installment = models.IntegerField(
        default=1,
        verbose_name=_("Installment"),
        help_text=_("Number of installments (1 for single payment)"),
    )
    installment_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Installment Rate"),
        help_text=_("Installment fee rate as percentage"),
    )
    monthly_installment_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Monthly Installment Amount"),
        help_text=_("Amount per month for installment payments"),
    )
    total_with_installment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Total with Installment"),
        help_text=_("Total amount including installment fees"),
    )

    # iyzico-specific error field
    error_group = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Error Group"),
        help_text=_("Iyzico error group (if payment failed)"),
    )

    # Custom manager
    objects = IyzicoPaymentManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        verbose_name = _("Iyzico Payment")
        verbose_name_plural = _("Iyzico Payments")
        indexes = [
            # iyzico-specific indexes
            models.Index(fields=["conversation_id"]),
            models.Index(fields=["token"]),
            # Card association filtering (analytics)
            models.Index(fields=["card_association", "status"]),
        ]

    def __str__(self) -> str:
        """String representation."""
        return (
            f"iyzico Payment {self.provider_payment_id or 'pending'} - {self.get_status_display()}"
        )

    def save(self, *args, **kwargs):
        """Ensure provider is set to iyzico."""
        self.provider = PaymentProviderChoices.IYZICO
        super().save(*args, **kwargs)

    # === Backward compatibility aliases ===

    @property
    def payment_id(self) -> str | None:
        """Alias for provider_payment_id (backward compatibility)."""
        return self.provider_payment_id

    @payment_id.setter
    def payment_id(self, value: str):
        """Set provider_payment_id via alias."""
        self.provider_payment_id = value

    # === iyzico-specific methods ===

    def process_refund(
        self,
        ip_address: str,
        amount: Decimal | None = None,
        reason: str | None = None,
    ):
        """
        Process refund for this payment.

        Args:
            ip_address: IP address initiating the refund (required by iyzico)
            amount: Amount to refund (None for full refund)
            reason: Optional refund reason

        Returns:
            RefundResponse object

        Raises:
            ValidationError: If payment cannot be refunded
            PaymentError: If refund fails
        """
        from django.db import transaction

        from .client import IyzicoClient
        from .signals import payment_refunded

        if not self.can_be_refunded():
            raise ValidationError("Payment cannot be refunded")

        if not self.provider_payment_id:
            raise ValidationError("Payment ID is missing")

        if not ip_address:
            raise ValidationError("IP address is required for refund")

        with transaction.atomic():
            # Lock this payment row to prevent concurrent refunds
            payment = type(self).objects.select_for_update().get(pk=self.pk)

            # Double-check status after locking
            if payment.status in [PaymentStatus.REFUNDED, PaymentStatus.REFUND_PENDING]:
                raise ValidationError(f"Payment already refunded (status: {payment.status})")

            client = IyzicoClient()
            response = client.refund_payment(
                payment_id=payment.provider_payment_id,
                ip_address=ip_address,
                amount=amount,
                reason=reason,
            )

            if response.is_successful():
                if amount is None or amount >= payment.amount:
                    payment.status = PaymentStatus.REFUNDED
                else:
                    payment.status = PaymentStatus.REFUND_PENDING

                payment.save()
                self.status = payment.status

        if response.is_successful():
            payment_refunded.send(
                sender=self.__class__,
                instance=self,
                response=response.to_dict(),
                amount=amount,
                reason=reason,
            )

        return response

    def update_from_response(self, response, save: bool = True) -> None:
        """
        Update payment fields from Iyzico API response.

        Args:
            response: PaymentResponse or dict from Iyzico
            save: Whether to save the model after updating
        """
        # Handle both PaymentResponse objects and dicts
        if hasattr(response, "to_dict"):
            response_dict = response.to_dict()
        else:
            response_dict = response

        # Update provider payment ID
        if response_dict.get("paymentId"):
            self.provider_payment_id = response_dict["paymentId"]

        if response_dict.get("conversationId"):
            self.conversation_id = response_dict["conversationId"]

        # Update status
        # Note: Iyzico API returns "success" or "failure" as status strings
        if response_dict.get("status") == "success":
            self.status = PaymentStatus.SUCCESS
        elif response_dict.get("status") in ("failure", "failed"):
            self.status = PaymentStatus.FAILED
        else:
            if self.status == PaymentStatus.PENDING:
                self.status = PaymentStatus.PROCESSING

        # Update amounts
        if response_dict.get("price"):
            self.amount = Decimal(str(response_dict["price"]))

        if response_dict.get("paidPrice"):
            self.paid_amount = Decimal(str(response_dict["paidPrice"]))

        if response_dict.get("currency"):
            self.currency = response_dict["currency"]

        if response_dict.get("installment"):
            self.installment = int(response_dict["installment"])

        # Update card info
        card_info = extract_card_info(response_dict)
        if card_info.get("cardType"):
            self.card_type = card_info["cardType"]
        if card_info.get("cardAssociation"):
            self.card_association = card_info["cardAssociation"]
        if card_info.get("cardFamily"):
            self.card_family = card_info["cardFamily"]
        if card_info.get("cardBankName"):
            self.card_bank_name = card_info["cardBankName"]
        if card_info.get("cardBankCode"):
            self.card_bank_code = card_info["cardBankCode"]

        # Update buyer info
        if response_dict.get("buyerEmail"):
            self.buyer_email = response_dict["buyerEmail"]
        if response_dict.get("buyerName"):
            self.buyer_name = response_dict["buyerName"]
        if response_dict.get("buyerSurname"):
            self.buyer_surname = response_dict["buyerSurname"]

        # Update error info
        if response_dict.get("errorCode"):
            self.error_code = response_dict["errorCode"]
        if response_dict.get("errorMessage"):
            self.error_message = response_dict["errorMessage"]
        if response_dict.get("errorGroup"):
            self.error_group = response_dict["errorGroup"]

        # Store sanitized raw response
        self.raw_response = sanitize_log_data(response_dict)

        if save:
            self.save()

    def mask_and_store_card_data(self, payment_details: dict[str, Any], save: bool = True) -> None:
        """
        Mask and store card data (last 4 digits only).

        Args:
            payment_details: Original payment details with card info
            save: Whether to save the model after updating
        """
        masked = mask_card_data(payment_details)

        if "card" in masked and isinstance(masked["card"], dict):
            last_four = masked["card"].get("lastFourDigits", "")
            if last_four:
                self.card_last_four_digits = last_four

        if save:
            self.save()

    # === Card display methods ===

    def get_masked_card_number(self) -> str:
        """Get masked card number for display."""
        if self.card_last_four_digits:
            return f"**** **** **** {self.card_last_four_digits}"
        return "****"

    def get_card_display(self) -> str:
        """Get card display string (e.g., 'VISA **** 1234')."""
        parts = []
        if self.card_association:
            parts.append(self.card_association)
        if self.card_last_four_digits:
            parts.append(f"**** {self.card_last_four_digits}")
        return " ".join(parts) if parts else "****"

    # === Installment methods ===

    def has_installment(self) -> bool:
        """Check if payment uses installments."""
        return self.installment > 1

    def get_installment_display(self) -> str:
        """Get formatted installment display string."""
        if not self.has_installment():
            return "Single payment"

        if self.monthly_installment_amount:
            return f"{self.installment}x {self.monthly_installment_amount} {self.currency}"

        return f"{self.installment}x installments"

    def get_installment_fee(self) -> Decimal:
        """Calculate total installment fee."""
        if not self.has_installment() or not self.total_with_installment:
            return Decimal("0.00")

        return self.total_with_installment - self.amount

    def get_installment_details(self) -> dict[str, Any]:
        """Get comprehensive installment details."""
        return {
            "installment_count": self.installment,
            "has_installment": self.has_installment(),
            "installment_rate": self.installment_rate,
            "monthly_amount": self.monthly_installment_amount,
            "total_with_fees": self.total_with_installment,
            "total_fee": self.get_installment_fee(),
            "base_amount": self.amount,
            "display": self.get_installment_display(),
        }

    # === Currency methods ===

    def get_formatted_amount(self, show_symbol: bool = True, show_code: bool = False) -> str:
        """Get formatted amount with currency symbol/code."""
        from .currency import format_amount

        return format_amount(self.amount, self.currency, show_symbol, show_code)

    def get_formatted_paid_amount(self, show_symbol: bool = True, show_code: bool = False) -> str:
        """Get formatted paid amount with currency symbol/code."""
        from .currency import format_amount

        amount = self.paid_amount if self.paid_amount else self.amount
        return format_amount(amount, self.currency, show_symbol, show_code)

    def get_currency_symbol(self) -> str:
        """Get currency symbol for this payment."""
        from .currency import get_currency_symbol

        return get_currency_symbol(self.currency)

    def get_currency_name(self) -> str:
        """Get full currency name."""
        from .currency import get_currency_name

        return get_currency_name(self.currency)

    def convert_to_currency(self, target_currency: str, converter=None) -> Decimal:
        """Convert payment amount to another currency."""
        from .currency import CurrencyConverter

        if not converter:
            converter = CurrencyConverter()

        return converter.convert(
            self.amount,
            self.currency,
            target_currency,
        )

    def is_currency(self, currency_code: str) -> bool:
        """Check if payment is in specific currency."""
        return self.currency.upper() == currency_code.upper()

    def get_amount_in_try(self, converter=None) -> Decimal:
        """Get payment amount in Turkish Lira (TRY)."""
        if self.is_currency("TRY"):
            return self.amount

        return self.convert_to_currency("TRY", converter)

    def get_currency_info(self) -> dict[str, Any]:
        """Get complete currency information."""
        from .currency import get_currency_info

        return get_currency_info(self.currency)
