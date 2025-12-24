"""
Django signals for payment lifecycle events.

This module provides signals that are dispatched during payment operations,
allowing applications to hook into the payment lifecycle.

Signals:
    - payment_created: Sent when a payment is created with a provider
    - payment_confirmed: Sent when a payment is confirmed/succeeded
    - payment_failed: Sent when a payment fails
    - payment_refunded: Sent when a refund is processed
    - webhook_received: Sent when a webhook is received from a provider
    - eft_approved: Sent when an EFT payment is approved
    - eft_rejected: Sent when an EFT payment is rejected

Example:
    >>> from payments_tr.signals import payment_confirmed
    >>> from django.dispatch import receiver
    >>>
    >>> @receiver(payment_confirmed)
    >>> def on_payment_success(sender, payment, result, **kwargs):
    ...     # Send confirmation email
    ...     send_confirmation_email(payment.user)
"""

from __future__ import annotations

from django.dispatch import Signal

# Payment lifecycle signals
payment_created = Signal()
"""
Sent when a payment is created with a provider.

Args:
    sender: Payment model class
    payment: Payment instance
    provider: Provider name (str)
    result: PaymentResult instance
"""

payment_confirmed = Signal()
"""
Sent when a payment is confirmed/succeeded.

Args:
    sender: Payment model class
    payment: Payment instance
    provider: Provider name (str)
    result: PaymentResult instance
"""

payment_failed = Signal()
"""
Sent when a payment fails.

Args:
    sender: Payment model class
    payment: Payment instance
    provider: Provider name (str)
    result: PaymentResult instance
    error_message: Error message (str)
"""

payment_refunded = Signal()
"""
Sent when a refund is processed.

Args:
    sender: Payment model class
    payment: Payment instance
    provider: Provider name (str)
    result: RefundResult instance
    amount: Refunded amount (int)
    reason: Refund reason (str)
"""

webhook_received = Signal()
"""
Sent when a webhook is received from a provider.

Args:
    sender: Provider class
    provider: Provider name (str)
    event_type: Event type (str)
    result: WebhookResult instance
    payload: Raw webhook payload
"""

# EFT signals
eft_approved = Signal()
"""
Sent when an EFT payment is approved.

Args:
    sender: EFT payment model class
    payment: Payment instance
    approved_by: User who approved
    approval_service: EFTApprovalService instance
"""

eft_rejected = Signal()
"""
Sent when an EFT payment is rejected.

Args:
    sender: EFT payment model class
    payment: Payment instance
    rejected_by: User who rejected
    reason: Rejection reason (str)
    approval_service: EFTApprovalService instance
"""
