"""
EFT payment model mixins and abstract models.

These provide the database fields and methods needed for EFT payment
workflows, including approval tracking.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class EFTStatus(models.TextChoices):
    """Status choices for EFT payments."""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class EFTPaymentFieldsMixin(models.Model):
    """
    Mixin that adds EFT-specific fields to a Payment model.

    This mixin provides fields for tracking EFT transfer details
    and approval workflow without requiring a specific model structure.

    Usage:
        class Payment(EFTPaymentFieldsMixin, models.Model):
            amount = models.IntegerField()
            # ... other fields

    Fields added:
        - eft_bank_name: Bank used for transfer
        - eft_reference_number: Bank reference/transaction number
        - eft_transfer_date: Date of the transfer
        - eft_sender_name: Name of person who made the transfer
        - approved_by: Admin user who approved the payment
        - approved_at: When the payment was approved
        - rejected_by: Admin user who rejected the payment
        - rejected_at: When the payment was rejected
        - rejection_reason: Reason for rejection
    """

    # EFT transfer details
    eft_bank_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Bank Name",
        help_text="Name of the bank used for EFT transfer",
    )
    eft_reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Reference Number",
        help_text="EFT reference or transaction number from bank",
    )
    eft_transfer_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Transfer Date",
        help_text="Date when the EFT transfer was made",
    )
    eft_sender_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Sender Name",
        help_text="Name of the person who made the EFT transfer",
    )

    # Approval workflow
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_approved",
        verbose_name="Approved By",
        help_text="Admin user who approved this EFT payment",
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Approved At",
        help_text="When the EFT payment was approved",
    )
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_rejected",
        verbose_name="Rejected By",
        help_text="Admin user who rejected this EFT payment",
    )
    rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Rejected At",
        help_text="When the EFT payment was rejected",
    )
    rejection_reason = models.TextField(
        blank=True,
        verbose_name="Rejection Reason",
        help_text="Reason for EFT payment rejection",
    )

    class Meta:
        abstract = True

    @property
    def is_eft_pending(self) -> bool:
        """Check if this EFT payment is pending approval."""
        return (
            self.approved_at is None
            and self.rejected_at is None
            and self.eft_reference_number is not None
        )

    @property
    def is_eft_approved(self) -> bool:
        """Check if this EFT payment has been approved."""
        return self.approved_at is not None

    @property
    def is_eft_rejected(self) -> bool:
        """Check if this EFT payment has been rejected."""
        return self.rejected_at is not None

    @property
    def eft_status(self) -> EFTStatus:
        """Get the current EFT approval status."""
        if self.is_eft_approved:
            return EFTStatus.APPROVED
        elif self.is_eft_rejected:
            return EFTStatus.REJECTED
        return EFTStatus.PENDING


class AbstractEFTPayment(EFTPaymentFieldsMixin):
    """
    Abstract base model for EFT payments.

    This provides a complete abstract model with EFT fields and
    common payment fields. Extend this if you want a standalone
    EFT payment model.

    Usage:
        class EFTPayment(AbstractEFTPayment):
            order = models.ForeignKey(Order, on_delete=models.CASCADE)

            class Meta(AbstractEFTPayment.Meta):
                pass
    """

    # Receipt/proof of payment
    receipt = models.FileField(
        upload_to="eft_receipts/",
        null=True,
        blank=True,
        verbose_name="Receipt",
        help_text="Upload proof of EFT transfer (screenshot, PDF, etc.)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["eft_reference_number"]),
            models.Index(fields=["created_at"]),
        ]

    def approve(self, user, save: bool = True) -> None:
        """
        Approve this EFT payment.

        Args:
            user: The admin user approving the payment
            save: Whether to save the model after approval
        """
        self.approved_by = user
        self.approved_at = timezone.now()
        self.rejected_by = None
        self.rejected_at = None
        self.rejection_reason = ""
        if save:
            self.save(
                update_fields=[
                    "approved_by",
                    "approved_at",
                    "rejected_by",
                    "rejected_at",
                    "rejection_reason",
                    "updated_at",
                ]
            )

    def reject(self, user, reason: str = "", save: bool = True) -> None:
        """
        Reject this EFT payment.

        Args:
            user: The admin user rejecting the payment
            reason: Reason for rejection
            save: Whether to save the model after rejection
        """
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.approved_by = None
        self.approved_at = None
        if save:
            self.save(
                update_fields=[
                    "rejected_by",
                    "rejected_at",
                    "rejection_reason",
                    "approved_by",
                    "approved_at",
                    "updated_at",
                ]
            )
