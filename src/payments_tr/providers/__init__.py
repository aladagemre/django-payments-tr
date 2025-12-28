"""
Payment provider abstraction layer.

This module provides a unified interface for multiple payment providers,
allowing seamless switching between iyzico, Stripe, and other gateways.

Supports per-country provider selection for multi-country deployments:

    # settings.py
    PAYMENT_PROVIDERS_BY_COUNTRY = {
        "TR": "iyzico",
        "US": "stripe",
    }

    # Usage
    from payments_tr.providers import get_payment_provider
    provider = get_payment_provider(country_code="TR")  # Gets iyzico
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
    get_available_providers,
    get_default_provider,
    get_payment_provider,
    get_provider_for_country,
    get_provider_for_country_cached,
    get_provider_name,
    get_supported_countries,
    is_iyzico_enabled,
    is_provider_available,
    is_stripe_enabled,
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
    "get_default_provider",
    "get_provider_name",
    "register_provider",
    "is_provider_available",
    # Per-country selection
    "get_provider_for_country",
    "get_provider_for_country_cached",
    "get_supported_countries",
    "get_available_providers",
    "is_iyzico_enabled",
    "is_stripe_enabled",
]
