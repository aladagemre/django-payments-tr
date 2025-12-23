"""
Django Payments TR - Payment processing for Django with Turkey-specific features.

This package provides:
- Provider abstraction layer for multiple payment gateways (iyzico, Stripe)
- Turkey-specific utilities (KDV/VAT, TCKN validation, IBAN validation)
- EFT payment workflow with admin approval
- Commission calculation utilities
"""

from payments_tr.providers import (
    BuyerInfo,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
    get_payment_provider,
    get_provider_name,
    register_provider,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Provider abstraction
    "PaymentProvider",
    "PaymentResult",
    "RefundResult",
    "WebhookResult",
    "BuyerInfo",
    "get_payment_provider",
    "get_provider_name",
    "register_provider",
]
