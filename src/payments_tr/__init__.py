"""
Django Payments TR - Payment processing for Django with Turkey-specific features.

This package provides:
- Provider abstraction layer for multiple payment gateways (iyzico, Stripe)
- Per-country provider selection for multi-country deployments
- Abstract payment models for multi-provider support
- Turkey-specific utilities (KDV/VAT, TCKN validation, IBAN validation)
- EFT payment workflow with admin approval
- Commission calculation utilities

Per-country provider selection:

    # settings.py
    PAYMENT_PROVIDERS_BY_COUNTRY = {
        "TR": "iyzico",
        "US": "stripe",
    }

    # Usage
    from payments_tr import get_payment_provider
    provider = get_payment_provider(country_code="TR")  # Gets iyzico
"""

from payments_tr.providers import (
    BuyerInfo,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
    get_available_providers,
    get_default_provider,
    get_payment_provider,
    get_provider_for_country,
    get_provider_name,
    get_supported_countries,
    is_iyzico_enabled,
    is_stripe_enabled,
    register_provider,
)


# Lazy import for models to avoid Django app registry issues
def _get_models():
    """Lazy import of models."""
    from payments_tr.models import (
        AbstractPayment,
        PaymentManager,
        PaymentProviderChoices,
        PaymentQuerySet,
        PaymentStatus,
    )

    return {
        "AbstractPayment": AbstractPayment,
        "PaymentStatus": PaymentStatus,
        "PaymentProviderChoices": PaymentProviderChoices,
        "PaymentQuerySet": PaymentQuerySet,
        "PaymentManager": PaymentManager,
    }


__version__ = "0.2.0"

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
    "get_default_provider",
    "get_provider_name",
    "register_provider",
    # Per-country selection
    "get_provider_for_country",
    "get_supported_countries",
    "get_available_providers",
    "is_iyzico_enabled",
    "is_stripe_enabled",
    # Lazy model imports
    "_get_models",
]
