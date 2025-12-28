"""
Iyzico payment provider for django-payments-tr.

Turkey's leading payment gateway with full support for:
- 3D Secure payments
- Installments (taksit)
- Subscriptions and recurring billing
- Card storage (PCI DSS compliant)
- Webhooks

Installation:
    pip install django-payments-tr[iyzico]

Usage:
    # settings.py
    INSTALLED_APPS = [
        ...
        "payments_tr",
        "payments_tr.providers.iyzico",
    ]

    IYZICO_API_KEY = "your-api-key"
    IYZICO_SECRET_KEY = "your-secret-key"
    IYZICO_BASE_URL = "https://api.iyzipay.com"  # or sandbox

    # models.py
    from payments_tr.providers.iyzico.models import AbstractIyzicoPayment

    class Payment(AbstractIyzicoPayment):
        user = models.ForeignKey(User, on_delete=models.CASCADE)
        # your fields...
"""

import importlib.util
from typing import TYPE_CHECKING

from .exceptions import (
    CardError,
    ConfigurationError,
    IyzicoAPIException,
    IyzicoError,
    IyzicoValidationException,
    PaymentError,
    ThreeDSecureError,
    ValidationError,
    WebhookError,
)

# Check if iyzipay is available (don't raise on import - check lazily)
_IYZIPAY_AVAILABLE = importlib.util.find_spec("iyzipay") is not None

# Type hints for lazy imports
if TYPE_CHECKING:
    from .client import IyzicoClient
    from .models import AbstractIyzicoPayment, IyzicoPaymentManager, IyzicoPaymentQuerySet
    from .provider import IyzicoProvider

__all__ = [
    # Exceptions (available immediately)
    "IyzicoError",
    "IyzicoAPIException",
    "IyzicoValidationException",
    "PaymentError",
    "CardError",
    "ConfigurationError",
    "ValidationError",
    "WebhookError",
    "ThreeDSecureError",
    # Provider
    "IyzicoProvider",
    # Client
    "IyzicoClient",
    # Models (lazy loaded)
    "AbstractIyzicoPayment",
    "IyzicoPaymentManager",
    "IyzicoPaymentQuerySet",
    # Functions
    "get_client",
    "get_provider",
]


def _check_iyzipay_available():
    """Check if iyzipay is installed and raise helpful error if not."""
    if not _IYZIPAY_AVAILABLE:
        raise ImportError(
            "Iyzico provider requires 'iyzipay' package.\n"
            "Install with: pip install django-payments-tr[iyzico]"
        )


def get_client(**kwargs) -> "IyzicoClient":
    """
    Get configured IyzicoClient instance.

    Uses settings from Django settings if not provided.

    Args:
        **kwargs: Override settings (api_key, secret_key, base_url)

    Returns:
        Configured IyzicoClient
    """
    from .client import IyzicoClient

    return IyzicoClient(**kwargs)


def get_provider() -> "IyzicoProvider":
    """
    Get IyzicoProvider instance.

    Returns:
        IyzicoProvider for payments-tr integration
    """
    from .provider import IyzicoProvider

    return IyzicoProvider()


def __getattr__(name: str):
    """Lazy import for heavy modules to avoid circular imports."""
    if name == "IyzicoProvider":
        from .provider import IyzicoProvider

        return IyzicoProvider
    if name == "IyzicoClient":
        from .client import IyzicoClient

        return IyzicoClient
    if name == "AbstractIyzicoPayment":
        from .models import AbstractIyzicoPayment

        return AbstractIyzicoPayment
    if name == "IyzicoPaymentManager":
        from .models import IyzicoPaymentManager

        return IyzicoPaymentManager
    if name == "IyzicoPaymentQuerySet":
        from .models import IyzicoPaymentQuerySet

        return IyzicoPaymentQuerySet
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
