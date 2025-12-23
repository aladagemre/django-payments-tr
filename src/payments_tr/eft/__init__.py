"""
EFT (Electronic Funds Transfer) payment workflow.

This module provides:
- Abstract models for EFT payment fields
- Admin mixins for EFT approval workflow
- Services for EFT payment processing
"""

from payments_tr.eft.admin import EFTPaymentAdminMixin, EFTPaymentListFilter
from payments_tr.eft.models import (
    AbstractEFTPayment,
    EFTPaymentFieldsMixin,
    EFTStatus,
)
from payments_tr.eft.services import EFTApprovalService

__all__ = [
    # Models
    "AbstractEFTPayment",
    "EFTPaymentFieldsMixin",
    "EFTStatus",
    # Admin
    "EFTPaymentAdminMixin",
    "EFTPaymentListFilter",
    # Services
    "EFTApprovalService",
]
