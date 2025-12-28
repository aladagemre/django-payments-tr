"""
Django models for payments-tr.

Provides abstract base models that can be inherited by your Django models
to add payment functionality. These models are provider-agnostic.

Architecture:
    AbstractPayment (provider-agnostic base)
        └── Provider-specific extensions (e.g., AbstractIyzicoPayment in django-iyzico)
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentStatus(models.TextChoices):
    """
    Payment status choices.

    These are provider-agnostic status values that work across
    different payment providers (Stripe, iyzico, PayPal, etc.).
    """

    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    SUCCESS = "success", _("Success")
    FAILED = "failed", _("Failed")
    REFUND_PENDING = "refund_pending", _("Refund Pending")
    REFUNDED = "refunded", _("Refunded")
    CANCELLED = "cancelled", _("Cancelled")


class PaymentProviderChoices(models.TextChoices):
    """Payment provider choices."""

    IYZICO = "iyzico", _("iyzico")
    STRIPE = "stripe", _("Stripe")
    PAYPAL = "paypal", _("PayPal")
    PAYTR = "paytr", _("PayTR")
    OTHER = "other", _("Other")


class PaymentQuerySet(models.QuerySet):
    """Custom QuerySet for payments (provider-agnostic)."""

    def successful(self):
        """Filter successful payments."""
        return self.filter(status=PaymentStatus.SUCCESS)

    def failed(self):
        """Filter failed payments."""
        return self.filter(status=PaymentStatus.FAILED)

    def pending(self):
        """Filter pending payments."""
        return self.filter(status=PaymentStatus.PENDING)

    def by_provider(self, provider: str):
        """Filter by payment provider."""
        return self.filter(provider=provider)

    def by_provider_payment_id(self, provider_payment_id: str):
        """Get payment by provider payment ID."""
        return self.filter(provider_payment_id=provider_payment_id)


class PaymentManager(models.Manager):
    """Custom manager for payments (provider-agnostic)."""

    def get_queryset(self):
        """Return custom QuerySet."""
        return PaymentQuerySet(self.model, using=self._db)

    def get_by_provider_payment_id(self, provider_payment_id: str):
        """
        Get payment by provider payment ID.

        Args:
            provider_payment_id: Payment ID from the provider

        Returns:
            Payment instance

        Raises:
            DoesNotExist: If payment not found
        """
        return self.get(provider_payment_id=provider_payment_id)

    def successful(self):
        """Get all successful payments."""
        return self.get_queryset().successful()

    def failed(self):
        """Get all failed payments."""
        return self.get_queryset().failed()

    def pending(self):
        """Get all pending payments."""
        return self.get_queryset().pending()

    def by_provider(self, provider: str):
        """Get payments by provider."""
        return self.get_queryset().by_provider(provider)


class AbstractPayment(models.Model):
    """
    Abstract base model for payments (provider-agnostic).

    This is the foundation for multi-provider payment support.
    Inherit from this for generic payment functionality, or use
    provider-specific extensions like AbstractIyzicoPayment from django-iyzico.

    Example:
        class Payment(AbstractPayment):
            user = models.ForeignKey(User, on_delete=models.CASCADE)
            order = models.ForeignKey(Order, on_delete=models.CASCADE)

            # Add provider-specific fields as needed
            stripe_payment_intent_id = models.CharField(max_length=255, null=True)

            class Meta:
                db_table = 'payments'

    This provides common payment fields while letting you add
    provider-specific fields in your model.
    """

    # Provider identification
    provider = models.CharField(
        max_length=20,
        choices=PaymentProviderChoices.choices,
        default=PaymentProviderChoices.OTHER,
        db_index=True,
        verbose_name=_("Provider"),
        help_text=_("Payment provider (e.g., iyzico, stripe)"),
    )
    provider_payment_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("Provider Payment ID"),
        help_text=_("Payment ID from the provider"),
    )

    # Payment details
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
        verbose_name=_("Status"),
        help_text=_("Current payment status"),
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("Amount"),
        help_text=_("Payment amount"),
    )
    paid_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Paid Amount"),
        help_text=_("Actual amount paid (may differ with fees/installments)"),
    )
    currency = models.CharField(
        max_length=3,
        default="TRY",
        verbose_name=_("Currency"),
        help_text=_("Currency code (e.g., TRY, USD, EUR)"),
    )

    # Buyer information (common across providers)
    buyer_email = models.EmailField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Buyer Email"),
        help_text=_("Buyer's email address"),
    )
    buyer_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Buyer Name"),
        help_text=_("Buyer's first name"),
    )
    buyer_surname = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name=_("Buyer Surname"),
        help_text=_("Buyer's last name"),
    )

    # Error handling
    error_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Error Code"),
        help_text=_("Error code (if payment failed)"),
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Error Message"),
        help_text=_("Error message (if payment failed)"),
    )

    # Audit trail
    raw_response = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("Raw Response"),
        help_text=_("Complete response from provider API (for debugging and audit)"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
        help_text=_("When this payment record was created"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At"),
        help_text=_("When this payment record was last updated"),
    )

    # Custom manager
    objects = PaymentManager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        indexes = [
            # Primary identifiers
            models.Index(fields=["provider_payment_id"]),
            models.Index(fields=["provider"]),
            # Status queries
            models.Index(fields=["status"]),
            # Date queries
            models.Index(fields=["created_at"]),
            models.Index(fields=["-created_at"]),
            # Buyer queries
            models.Index(fields=["buyer_email"]),
            # Composite indexes for common query patterns
            models.Index(fields=["provider", "status"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider_payment_id", "status"]),
            models.Index(fields=["buyer_email", "status"]),
            models.Index(fields=["currency", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        """String representation."""
        return f"{self.provider} Payment {self.provider_payment_id or 'pending'} - {self.get_status_display()}"

    def is_successful(self) -> bool:
        """Check if payment is successful."""
        return self.status == PaymentStatus.SUCCESS

    def is_failed(self) -> bool:
        """Check if payment failed."""
        return self.status == PaymentStatus.FAILED

    def is_pending(self) -> bool:
        """Check if payment is pending."""
        return self.status in [PaymentStatus.PENDING, PaymentStatus.PROCESSING]

    def can_be_refunded(self) -> bool:
        """Check if payment can be refunded."""
        return self.status == PaymentStatus.SUCCESS

    def get_buyer_full_name(self) -> str:
        """Get buyer's full name."""
        if self.buyer_name and self.buyer_surname:
            return f"{self.buyer_name} {self.buyer_surname}"
        return self.buyer_name or self.buyer_surname or ""

    def get_amount_display(self) -> str:
        """Get formatted amount for display."""
        return f"{self.amount} {self.currency}"

    def get_paid_amount_display(self) -> str:
        """Get formatted paid amount for display."""
        amount = self.paid_amount if self.paid_amount else self.amount
        return f"{amount} {self.currency}"
