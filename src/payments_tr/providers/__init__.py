"""
Payment provider abstraction layer.

This module provides a unified interface for multiple payment providers,
allowing seamless switching between iyzico, Stripe, and other gateways.
"""

from payments_tr.providers.base import (
    BuyerInfo,
    PaymentLike,
    PaymentProvider,
    PaymentResult,
    PaymentWithClient,
    RefundResult,
    WebhookResult,
)
from payments_tr.providers.registry import (
    ProviderRegistry,
    get_payment_provider,
    get_provider_name,
    register_provider,
    registry,
)

__all__ = [
    # Base classes and protocols
    "PaymentProvider",
    "PaymentResult",
    "RefundResult",
    "WebhookResult",
    "BuyerInfo",
    "PaymentLike",
    "PaymentWithClient",
    # Registry
    "ProviderRegistry",
    "registry",
    "get_payment_provider",
    "get_provider_name",
    "register_provider",
]
