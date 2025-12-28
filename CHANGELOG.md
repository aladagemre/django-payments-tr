# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-12-29

### Changed

- **BREAKING**: Renamed `IyzicoAdapter` to `IyzicoProvider` for consistency
- **BREAKING**: Renamed `StripeAdapter` to `StripeProvider` for consistency
- **BREAKING**: Renamed `adapter.py` to `provider.py` in iyzico module
- **BREAKING**: Renamed `get_adapter()` to `get_provider()` in iyzico module
- Consistent `*Provider` naming convention throughout the codebase
- Updated all documentation to reflect new naming

### Removed

- Backwards compatibility aliases (library is new, no legacy support needed)

## [0.2.0] - 2025-12-28

### Added

- **Per-Country Provider Selection**: Support for different payment providers per country

  - `get_payment_provider(country_code="TR")` returns country-specific provider
  - `PAYMENT_PROVIDERS_BY_COUNTRY` setting for country-to-provider mapping
  - Falls back to `PAYMENT_PROVIDER` for unconfigured countries

- **New Helper Functions**:

  - `get_provider_for_country(country_code)` - Get provider name for a country
  - `get_supported_countries()` - Get all configured country-provider mappings
  - `get_available_providers()` - List all registered provider names
  - `is_iyzico_enabled(country_code=None)` - Check if iyzico is active
  - `is_stripe_enabled(country_code=None)` - Check if Stripe is active
  - `get_provider_for_country_cached(country_code)` - Cached country provider lookup

- **Caching**: Added LRU cache for country-specific provider lookups (up to 32 countries)

### Changed

- `get_payment_provider()` now accepts optional `country_code` parameter
- `get_provider_name()` now accepts optional `country_code` parameter
- Logging changed from INFO to DEBUG for provider selection (less noisy in production)

## [0.1.0] - 2025-12-23

### Added

- **Provider Abstraction Layer**: Unified interface for multiple payment gateways

  - `PaymentProvider` abstract base class with standard methods
  - `PaymentResult`, `RefundResult`, and `WebhookResult` dataclasses
  - Provider registry with `register_provider()` and `get_payment_provider()`

- **iyzico Provider**: Full integration with embedded iyzico client

  - `IyzicoClient` - Low-level API client for direct iyzico access
  - `IyzicoProvider` - High-level provider conforming to `PaymentProvider` interface
  - Payment creation with checkout form (3D Secure)
  - Payment confirmation and status checking
  - Refund processing (full and partial)
  - Webhook handling for payment notifications
  - Installment support
  - Card storage (PCI DSS compliant tokenization)
  - BIN lookup
  - Subscription management

- **Stripe Provider**: Direct Stripe API integration

  - PaymentIntent creation
  - Payment confirmation
  - Refund processing
  - Webhook signature verification

- **Turkey-Specific Utilities**:

  - **KDV (VAT)**: `calculate_kdv()`, `amount_with_kdv()`, `extract_kdv()` with standard (20%), reduced (10%), and super-reduced (1%) rates
  - **TC Kimlik No**: `validate_tckn()` with checksum verification
  - **Turkish IBAN**: `validate_iban_tr()` with format and checksum validation
  - **VKN (Tax Number)**: `validate_vkn()` for business tax IDs
  - **Phone Numbers**: `validate_phone_tr()` and `format_phone()` for Turkish mobile/landline numbers

- **EFT Payment Workflow**:

  - `EFTPaymentFieldsMixin` model mixin for EFT-specific fields
  - `EFTPaymentAdminMixin` with approve/reject admin actions
  - `EFTApprovalService` for programmatic payment approval/rejection
  - Status tracking: pending, approved, rejected

- **Django Integration**:

  - Django app configuration (`payments_tr`)
  - Admin integration with custom actions
  - DRF serializers for common operations

- **DRF Serializers** (`payments_tr.contrib.serializers`):
  - `PaymentIntentCreateSerializer`
  - `PaymentResultSerializer`
  - `RefundResultSerializer`
  - `EFTPaymentCreateSerializer`
  - `EFTPaymentApprovalSerializer`

### Dependencies

- Django 4.2, 5.0, 5.1 support
- Python 3.12, 3.13 support
- Optional: `iyzipay` for iyzico integration (embedded client included)
- Optional: `stripe` for Stripe integration

[0.3.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.3.0
[0.2.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.2.0
[0.1.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.1.0
