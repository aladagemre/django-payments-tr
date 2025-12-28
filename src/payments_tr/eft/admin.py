"""
Django admin mixins for EFT payment approval workflow.

These mixins add approval/rejection actions and display customization
to Django admin for EFT payments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.utils.safestring import mark_safe

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class EFTPaymentAdminMixin:
    """
    Admin mixin that adds EFT payment approval workflow.

    This mixin provides:
    - Approve/reject admin actions
    - Color-coded status display
    - EFT-specific fieldsets
    - List filters for approval status

    Usage:
        @admin.register(Payment)
        class PaymentAdmin(EFTPaymentAdminMixin, admin.ModelAdmin):
            list_display = ['id', 'amount', 'eft_status_display', ...]
            # ... other admin options

    Note: Your model should use EFTPaymentFieldsMixin or AbstractEFTPayment.
    """

    # Admin actions
    actions = ["approve_eft_payments", "reject_eft_payments"]

    # Additional fields to show in list display
    eft_list_display_fields = [
        "eft_status_display",
        "eft_bank_name",
        "eft_reference_number",
        "approved_by",
    ]

    # List filters for EFT status
    eft_list_filter_fields = [
        "approved_at",
        "rejected_at",
        "eft_bank_name",
    ]

    # Fieldset for EFT details in admin form
    eft_fieldset = (
        "EFT Details",
        {
            "fields": (
                "eft_bank_name",
                "eft_reference_number",
                "eft_transfer_date",
                "eft_sender_name",
                "receipt",
            ),
            "classes": ("collapse",),
        },
    )

    # Fieldset for approval workflow
    approval_fieldset = (
        "Approval Status",
        {
            "fields": (
                ("approved_by", "approved_at"),
                ("rejected_by", "rejected_at"),
                "rejection_reason",
            ),
            "classes": ("collapse",),
        },
    )

    @admin.display(description="EFT Status")
    def eft_status_display(self, obj: Any) -> str:
        """Display EFT status with color coding."""
        if hasattr(obj, "is_eft_approved") and obj.is_eft_approved:
            return mark_safe(
                '<span style="color: #28a745; font-weight: bold;">&#x2713; Approved</span>'
            )
        elif hasattr(obj, "is_eft_rejected") and obj.is_eft_rejected:
            return mark_safe(
                '<span style="color: #dc3545; font-weight: bold;">&#x2717; Rejected</span>'
            )
        elif hasattr(obj, "eft_reference_number") and obj.eft_reference_number:
            return mark_safe(
                '<span style="color: #ffc107; font-weight: bold;">&#x23F3; Pending</span>'
            )
        return mark_safe('<span style="color: #6c757d;">N/A</span>')

    @admin.action(description="Approve selected EFT payments")
    def approve_eft_payments(
        self,
        request: HttpRequest,
        queryset: QuerySet[Any],
    ) -> None:
        """Admin action to approve selected EFT payments."""
        approved_count = 0
        for payment in queryset:
            if hasattr(payment, "approve"):
                payment.approve(request.user)
                approved_count += 1
                # Trigger any post-approval logic
                self._on_eft_approved(request, payment)

        self.message_user(  # type: ignore[attr-defined]
            request,
            f"Successfully approved {approved_count} EFT payment(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Reject selected EFT payments")
    def reject_eft_payments(
        self,
        request: HttpRequest,
        queryset: QuerySet[Any],
    ) -> None:
        """Admin action to reject selected EFT payments."""
        rejected_count = 0
        for payment in queryset:
            if hasattr(payment, "reject"):
                payment.reject(request.user, reason="Rejected via admin action")
                rejected_count += 1
                # Trigger any post-rejection logic
                self._on_eft_rejected(request, payment)

        self.message_user(  # type: ignore[attr-defined]
            request,
            f"Rejected {rejected_count} EFT payment(s).",
            messages.WARNING,
        )

    def _on_eft_approved(self, request: HttpRequest, payment: Any) -> None:
        """
        Hook called after EFT payment approval.

        Override this method to add custom logic after approval,
        such as sending confirmation emails or updating order status.

        Args:
            request: The admin request
            payment: The approved payment object
        """
        pass

    def _on_eft_rejected(self, request: HttpRequest, payment: Any) -> None:
        """
        Hook called after EFT payment rejection.

        Override this method to add custom logic after rejection,
        such as sending notification emails.

        Args:
            request: The admin request
            payment: The rejected payment object
        """
        pass

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Any = None,
    ) -> tuple[str, ...]:
        """Make approval fields read-only."""
        readonly = list(super().get_readonly_fields(request, obj))  # type: ignore
        readonly.extend(
            [
                "approved_by",
                "approved_at",
                "rejected_by",
                "rejected_at",
            ]
        )
        return tuple(readonly)


class EFTPaymentListFilter(admin.SimpleListFilter):
    """
    Admin list filter for EFT payment approval status.

    Usage:
        class PaymentAdmin(admin.ModelAdmin):
            list_filter = [EFTPaymentListFilter, ...]
    """

    title = "EFT Status"
    parameter_name = "eft_status"

    def lookups(
        self,
        request: HttpRequest,
        model_admin: admin.ModelAdmin[Any],
    ) -> list[tuple[str, str]]:
        """Return filter options."""
        return [
            ("pending", "Pending Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("no_eft", "Not EFT"),
        ]

    def queryset(
        self,
        request: HttpRequest,
        queryset: QuerySet[Any],
    ) -> QuerySet[Any]:
        """Filter queryset based on selected option."""
        value = self.value()

        if value == "pending":
            return queryset.filter(
                eft_reference_number__isnull=False,
                approved_at__isnull=True,
                rejected_at__isnull=True,
            )
        elif value == "approved":
            return queryset.filter(approved_at__isnull=False)
        elif value == "rejected":
            return queryset.filter(rejected_at__isnull=False)
        elif value == "no_eft":
            return queryset.filter(eft_reference_number__isnull=True)

        return queryset
