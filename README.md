# django-payments-tr

Payment processing for Django with Turkey-specific features.

[![PyPI version](https://badge.fury.io/py/django-payments-tr.svg)](https://badge.fury.io/py/django-payments-tr)
[![Python versions](https://img.shields.io/pypi/pyversions/django-payments-tr.svg)](https://pypi.org/project/django-payments-tr/)
[![Django versions](https://img.shields.io/badge/django-4.2%20%7C%205.0%20%7C%205.1-blue.svg)](https://pypi.org/project/django-payments-tr/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Provider Abstraction**: Unified interface for multiple payment gateways (iyzico, Stripe)
- **Turkey-Specific Utilities**:
  - KDV (VAT) calculation with current Turkish rates
  - TC Kimlik No validation
  - Turkish IBAN validation
  - VKN (Tax Number) validation
  - Turkish phone number validation
- **EFT Payment Workflow**: Complete EFT payment handling with admin approval
- **Django Integration**: Admin mixins, model mixins, DRF serializers

## Installation

```bash
# Basic installation
pip install django-payments-tr

# With iyzico support
pip install django-payments-tr[iyzico]

# With Stripe support
pip install django-payments-tr[stripe]

# With both providers
pip install django-payments-tr[all]
```

## Quick Start

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "payments_tr",
]
```

### 2. Configure Payment Provider

```python
# settings.py
PAYMENT_PROVIDER = "iyzico"  # or "stripe"

# For iyzico
IYZICO_API_KEY = "your-api-key"
IYZICO_SECRET_KEY = "your-secret-key"
IYZICO_BASE_URL = "api.iyzipay.com"  # or sandbox-api.iyzipay.com

# For Stripe
STRIPE_SECRET_KEY = "sk_live_..."
STRIPE_WEBHOOK_SECRET = "whsec_..."
```

### 3. Use the Provider

```python
from payments_tr import get_payment_provider

# Get configured provider
provider = get_payment_provider()

# Create a payment
result = provider.create_payment(
    payment,
    callback_url="https://example.com/callback",
    buyer_info={
        "email": "customer@example.com",
        "name": "John",
        "surname": "Doe",
    }
)

if result.success:
    # For iyzico: redirect to checkout
    redirect(result.checkout_url)
    # For Stripe: send client_secret to frontend
    return {"client_secret": result.client_secret}
```

## Turkey-Specific Utilities

### KDV (VAT) Calculation

```python
from payments_tr.tax import KDVRate, calculate_kdv, amount_with_kdv, extract_kdv

# Calculate KDV
kdv = calculate_kdv(10000)  # 2000 (20% of 100 TRY)
kdv = calculate_kdv(10000, KDVRate.REDUCED)  # 1000 (10%)

# Calculate gross amount
gross = amount_with_kdv(10000)  # 12000 (100 TRY + 20% KDV)

# Extract net and KDV from gross
net, kdv = extract_kdv(12000)  # (10000, 2000)
```

### Validation

```python
from payments_tr.validation import (
    validate_tckn,
    validate_iban_tr,
    validate_vkn,
    validate_phone_tr,
    format_phone,
)

# TC Kimlik No
if validate_tckn("10000000146"):
    print("Valid TC Kimlik No")

# Turkish IBAN
if validate_iban_tr("TR330006100519786457841326"):
    print("Valid Turkish IBAN")

# Phone formatting
formatted = format_phone("5551234567")  # "+90 555 123 45 67"
```

## EFT Payment Workflow

### Add EFT Fields to Your Model

```python
from django.db import models
from payments_tr.eft import EFTPaymentFieldsMixin

class Payment(EFTPaymentFieldsMixin, models.Model):
    amount = models.IntegerField()
    # ... your other fields

    def confirm(self):
        # Your confirmation logic
        pass
```

### Admin Integration

```python
from django.contrib import admin
from payments_tr.eft import EFTPaymentAdminMixin

@admin.register(Payment)
class PaymentAdmin(EFTPaymentAdminMixin, admin.ModelAdmin):
    list_display = ['id', 'amount', 'eft_status_display']
    # Adds approve/reject actions automatically
```

### EFT Approval Service

```python
from payments_tr.eft import EFTApprovalService

service = EFTApprovalService()

# Approve a payment
result = service.approve_payment(payment, admin_user)

# Reject with reason
result = service.reject_payment(payment, admin_user, reason="Invalid receipt")
```

## Provider Abstraction

### Using Multiple Providers

```python
from payments_tr import get_payment_provider

# Get default (from settings)
provider = get_payment_provider()

# Get specific provider by name
iyzico = get_payment_provider("iyzico")
stripe = get_payment_provider("stripe")
```

### Per-Country Provider Selection

For multi-country deployments, configure different providers per country:

```python
# settings.py
PAYMENT_PROVIDERS_BY_COUNTRY = {
    "TR": "iyzico",   # Turkey uses iyzico
    "US": "stripe",   # USA uses Stripe
    "GB": "stripe",   # UK uses Stripe
    "BR": "pagarme",  # Brazil uses local provider (when implemented)
}
PAYMENT_PROVIDER = "stripe"  # Default fallback for unconfigured countries
```

```python
from payments_tr import get_payment_provider

# Get provider based on user's country
provider = get_payment_provider(country_code="TR")  # Returns iyzico
provider = get_payment_provider(country_code="US")  # Returns Stripe
provider = get_payment_provider(country_code="XX")  # Falls back to default (Stripe)

# Explicit provider name overrides country
provider = get_payment_provider(name="stripe", country_code="TR")  # Returns Stripe
```

### Helper Functions

```python
from payments_tr import (
    get_provider_for_country,
    get_provider_name,
    get_supported_countries,
    get_available_providers,
    is_iyzico_enabled,
    is_stripe_enabled,
)

# Get provider name for a country
get_provider_for_country("TR")  # "iyzico"
get_provider_for_country("XX")  # "stripe" (default)

# Get provider name (with optional country)
get_provider_name()             # "stripe" (default)
get_provider_name("TR")         # "iyzico"

# Get all configured country mappings
get_supported_countries()       # {"TR": "iyzico", "US": "stripe", ...}

# Get all registered providers
get_available_providers()       # ["stripe", "iyzico"]

# Check which provider is active
is_iyzico_enabled()             # False (checking default)
is_iyzico_enabled("TR")         # True
is_stripe_enabled("US")         # True
```

### Creating Custom Providers

```python
from payments_tr import PaymentProvider, PaymentResult, register_provider

class PayTRProvider(PaymentProvider):
    provider_name = "paytr"

    def create_payment(self, payment, **kwargs):
        # Your implementation
        return PaymentResult(success=True, ...)

    def confirm_payment(self, provider_payment_id):
        return PaymentResult(success=True, ...)

    def create_refund(self, payment, amount=None, reason="", **kwargs):
        return RefundResult(success=True, ...)

    def handle_webhook(self, payload, signature=None, **kwargs):
        return WebhookResult(success=True, ...)

    def get_payment_status(self, provider_payment_id):
        return "succeeded"

# Register your provider
register_provider("paytr", PayTRProvider)
```

## DRF Serializers

```python
from payments_tr.contrib.serializers import (
    PaymentIntentCreateSerializer,
    PaymentResultSerializer,
    EFTPaymentCreateSerializer,
)

class PaymentViewSet(viewsets.ModelViewSet):
    @action(detail=True, methods=['post'])
    def create_intent(self, request, pk=None):
        serializer = PaymentIntentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provider = get_payment_provider()
        result = provider.create_payment(
            self.get_object(),
            **serializer.validated_data
        )

        return Response(PaymentResultSerializer(result.to_dict()).data)
```

## Architecture

This package provides a complete payment solution with embedded provider clients:

```
┌───────────────────────────────────────────────────────────────────┐
│                      django-payments-tr                           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Provider Abstraction Layer                                  │  │
│  │  - PaymentProvider abstract base class                       │  │
│  │  - PaymentResult, RefundResult, WebhookResult               │  │
│  │  - Per-country provider selection                            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Turkey-Specific Features                                    │  │
│  │  - KDV (VAT) calculation                                     │  │
│  │  - TCKN, IBAN, VKN validation                               │  │
│  │  - EFT payment workflow                                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────┐    ┌────────────────────────┐        │
│  │  IyzicoClient          │    │  StripeProvider        │        │
│  │  (embedded)            │    │                        │        │
│  │  - Checkout forms      │    │  - PaymentIntent       │        │
│  │  - 3D Secure           │    │  - Webhooks            │        │
│  │  - Installments        │    │  - Refunds             │        │
│  │  - Subscriptions       │    │  - Subscriptions       │        │
│  │  - Card storage        │    │                        │        │
│  └───────────┬────────────┘    └───────────┬────────────┘        │
└──────────────┼─────────────────────────────┼─────────────────────┘
               ▼                             ▼
      ┌─────────────────┐           ┌─────────────────┐
      │    iyzipay      │           │     stripe      │
      │  (Python SDK)   │           │  (Python SDK)   │
      └─────────────────┘           └─────────────────┘
```

**Note**: The iyzico client is fully embedded in this package. You don't need a separate django-iyzico installation.

## Low-Level iyzico Client

For advanced use cases, you can access the embedded `IyzicoClient` directly:

```python
from payments_tr.providers.iyzico import get_client, IyzicoClient

# Get a configured client (uses Django settings)
client = get_client()

# Or create with explicit settings
client = IyzicoClient(
    api_key="your-api-key",
    secret_key="your-secret-key",
    base_url="https://sandbox-api.iyzipay.com"
)

# Create checkout form
response = client.create_checkout_form(
    order_data={
        "locale": "tr",
        "conversationId": "123456",
        "price": "100.00",
        "paidPrice": "100.00",
        "currency": "TRY",
        "basketId": "B123",
        "paymentGroup": "PRODUCT",
    },
    buyer={
        "id": "BY789",
        "name": "John",
        "surname": "Doe",
        "email": "john@example.com",
        "gsmNumber": "+905551234567",
        "identityNumber": "11111111111",
        "registrationAddress": "Istanbul, Turkey",
        "city": "Istanbul",
        "country": "Turkey",
        "ip": "85.34.78.112",
    },
    billing_address={
        "contactName": "John Doe",
        "city": "Istanbul",
        "country": "Turkey",
        "address": "Istanbul, Turkey",
    },
    basket_items=[
        {
            "id": "ITEM1",
            "name": "Product Name",
            "category1": "Category",
            "itemType": "PHYSICAL",
            "price": "100.00",
        }
    ],
    callback_url="https://example.com/callback",
)

# Retrieve checkout form result (after callback)
result = client.retrieve_checkout_form(token)

# Process refund
refund_response = client.refund_payment(
    payment_id="12345678",
    ip_address="85.34.78.112",
    amount=Decimal("50.00"),  # Partial refund
    reason="Customer request",
)
```

### iyzico Client Features

The embedded client supports:

| Feature | Method |
|---------|--------|
| Checkout Form | `create_checkout_form()`, `retrieve_checkout_form()` |
| 3D Secure | Automatic with checkout forms |
| Refunds | `refund_payment()` (full and partial) |
| Installments | `get_installment_info()` |
| Card Storage | `create_card()`, `delete_card()` |
| BIN Lookup | `retrieve_bin_number()` |
| Subscriptions | `payments_tr.providers.iyzico.subscriptions` module |

### iyzico Model Mixin

For Django models with iyzico-specific fields:

```python
from django.db import models
from payments_tr.providers.iyzico.models import AbstractIyzicoPayment

class Payment(AbstractIyzicoPayment):
    """Payment model with iyzico fields pre-configured."""
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    description = models.TextField(blank=True)

    # AbstractIyzicoPayment provides:
    # - iyzico_token
    # - iyzico_conversation_id
    # - iyzico_payment_id
    # - status, amount, currency fields
    # - QuerySet methods for filtering by status
```

## Configuration Reference

```python
# settings.py

# Default payment provider (used when no country match)
PAYMENT_PROVIDER = "stripe"  # or "iyzico"

# Per-country provider mapping (optional)
PAYMENT_PROVIDERS_BY_COUNTRY = {
    "TR": "iyzico",   # Turkey uses iyzico
    "US": "stripe",   # USA uses Stripe
    "GB": "stripe",   # UK uses Stripe
}

# iyzico settings
IYZICO_API_KEY = "..."
IYZICO_SECRET_KEY = "..."
IYZICO_BASE_URL = "api.iyzipay.com"

# Stripe settings
STRIPE_SECRET_KEY = "sk_..."
STRIPE_PUBLISHABLE_KEY = "pk_..."
STRIPE_WEBHOOK_SECRET = "whsec_..."
```

## Development

```bash
# Clone the repo
git clone https://github.com/aladagemre/django-payments-tr
cd django-payments-tr

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .

# Run type checking
mypy src
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## Related Projects

- [django-iyzico](https://github.com/aladagemre/django-iyzico) - The iyzico client is now **embedded** in django-payments-tr. The standalone package is deprecated in favor of this unified solution.
