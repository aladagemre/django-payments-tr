# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-12-23

### Added

- **Provider Abstraction Layer**: Unified interface for multiple payment gateways
  - `PaymentProvider` abstract base class with standard methods
  - `PaymentResult`, `RefundResult`, and `WebhookResult` dataclasses
  - Provider registry with `register_provider()` and `get_payment_provider()`

- **iyzico Provider**: Full integration via django-iyzico
  - Payment creation with checkout form
  - Payment confirmation and status checking
  - Refund processing (full and partial)
  - Webhook handling for payment notifications

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
- Optional: django-iyzico for iyzico integration
- Optional: stripe for Stripe integration

[0.1.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.1.0
