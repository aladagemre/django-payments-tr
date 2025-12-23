"""
EFT payment approval service.

This module provides a service class for managing EFT payment approvals
with proper validation and notifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from django.db import transaction

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


@runtime_checkable
class EFTPaymentProtocol(Protocol):
    """Protocol for EFT payment objects."""

    eft_reference_number: str | None
    approved_at: Any
    rejected_at: Any

    def approve(self, user: Any, save: bool = True) -> None: ...
    def reject(self, user: Any, reason: str = "", save: bool = True) -> None: ...


@dataclass
class ApprovalResult:
    """Result of an approval/rejection operation."""

    success: bool
    payment_id: int | str
    action: str  # 'approved' or 'rejected'
    error: str | None = None


class EFTApprovalService:
    """
    Service for managing EFT payment approvals.

    This service provides methods for approving and rejecting EFT payments
    with validation, transaction handling, and optional notifications.

    Example:
        >>> service = EFTApprovalService()
        >>> result = service.approve_payment(payment, admin_user)
        >>> if result.success:
        ...     print(f"Payment {result.payment_id} approved")

    Customization:
        Subclass and override notification methods for custom behavior:

        >>> class MyEFTService(EFTApprovalService):
        ...     def on_approved(self, payment, user):
        ...         send_confirmation_email(payment)
    """

    def approve_payment(
        self,
        payment: EFTPaymentProtocol,
        user: AbstractUser,
        *,
        notify: bool = True,
    ) -> ApprovalResult:
        """
        Approve an EFT payment.

        Args:
            payment: The payment to approve
            user: The admin user approving the payment
            notify: Whether to trigger notifications

        Returns:
            ApprovalResult with success status
        """
        payment_id = getattr(payment, "id", "unknown")

        # Validate
        if not payment.eft_reference_number:
            return ApprovalResult(
                success=False,
                payment_id=payment_id,
                action="approved",
                error="Payment has no EFT reference number",
            )

        if payment.approved_at is not None:
            return ApprovalResult(
                success=False,
                payment_id=payment_id,
                action="approved",
                error="Payment is already approved",
            )

        try:
            with transaction.atomic():
                payment.approve(user)
                logger.info(
                    f"EFT payment {payment_id} approved by {user}",
                    extra={"payment_id": payment_id, "user_id": user.id},
                )

            if notify:
                self.on_approved(payment, user)

            return ApprovalResult(
                success=True,
                payment_id=payment_id,
                action="approved",
            )

        except Exception as e:
            logger.exception(f"Error approving EFT payment {payment_id}: {e}")
            return ApprovalResult(
                success=False,
                payment_id=payment_id,
                action="approved",
                error=str(e),
            )

    def reject_payment(
        self,
        payment: EFTPaymentProtocol,
        user: AbstractUser,
        reason: str = "",
        *,
        notify: bool = True,
    ) -> ApprovalResult:
        """
        Reject an EFT payment.

        Args:
            payment: The payment to reject
            user: The admin user rejecting the payment
            reason: Reason for rejection
            notify: Whether to trigger notifications

        Returns:
            ApprovalResult with success status
        """
        payment_id = getattr(payment, "id", "unknown")

        # Validate
        if payment.rejected_at is not None:
            return ApprovalResult(
                success=False,
                payment_id=payment_id,
                action="rejected",
                error="Payment is already rejected",
            )

        try:
            with transaction.atomic():
                payment.reject(user, reason=reason)
                logger.info(
                    f"EFT payment {payment_id} rejected by {user}: {reason}",
                    extra={
                        "payment_id": payment_id,
                        "user_id": user.id,
                        "reason": reason,
                    },
                )

            if notify:
                self.on_rejected(payment, user, reason)

            return ApprovalResult(
                success=True,
                payment_id=payment_id,
                action="rejected",
            )

        except Exception as e:
            logger.exception(f"Error rejecting EFT payment {payment_id}: {e}")
            return ApprovalResult(
                success=False,
                payment_id=payment_id,
                action="rejected",
                error=str(e),
            )

    def bulk_approve(
        self,
        payments: QuerySet | list,
        user: AbstractUser,
        *,
        notify: bool = True,
    ) -> list[ApprovalResult]:
        """
        Approve multiple EFT payments.

        Args:
            payments: QuerySet or list of payments to approve
            user: The admin user approving the payments
            notify: Whether to trigger notifications

        Returns:
            List of ApprovalResult for each payment
        """
        results = []
        for payment in payments:
            result = self.approve_payment(payment, user, notify=notify)
            results.append(result)
        return results

    def bulk_reject(
        self,
        payments: QuerySet | list,
        user: AbstractUser,
        reason: str = "",
        *,
        notify: bool = True,
    ) -> list[ApprovalResult]:
        """
        Reject multiple EFT payments.

        Args:
            payments: QuerySet or list of payments to reject
            user: The admin user rejecting the payments
            reason: Reason for rejection
            notify: Whether to trigger notifications

        Returns:
            List of ApprovalResult for each payment
        """
        results = []
        for payment in payments:
            result = self.reject_payment(payment, user, reason=reason, notify=notify)
            results.append(result)
        return results

    def get_pending_payments(self, queryset: QuerySet) -> QuerySet:
        """
        Filter queryset to only pending EFT payments.

        Args:
            queryset: Base queryset to filter

        Returns:
            Filtered queryset with only pending EFT payments
        """
        return queryset.filter(
            eft_reference_number__isnull=False,
            approved_at__isnull=True,
            rejected_at__isnull=True,
        )

    def on_approved(self, payment: EFTPaymentProtocol, user: AbstractUser) -> None:
        """
        Hook called after payment approval.

        Override this method to add custom logic such as:
        - Sending confirmation emails
        - Updating order status
        - Triggering fulfillment

        Args:
            payment: The approved payment
            user: The admin user who approved
        """
        pass

    def on_rejected(
        self,
        payment: EFTPaymentProtocol,
        user: AbstractUser,
        reason: str,
    ) -> None:
        """
        Hook called after payment rejection.

        Override this method to add custom logic such as:
        - Sending rejection notification
        - Logging for audit

        Args:
            payment: The rejected payment
            user: The admin user who rejected
            reason: Rejection reason
        """
        pass
