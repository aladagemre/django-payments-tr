# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.2] - 2026-05-10

Patch release. Type-only cleanup pass — no public API change, no
runtime behaviour change. `pytest -q` still 1349/1349 green.

### Internal

- **`mypy --strict` cleanup, pass 1.** Reduced the strict-mode error
  count from **367 → 107** across 14 files. Fully cleaned: `admin.py`
  (94 → 0), `viewsets.py` (26 → 0), `subscriptions/manager.py`
  (24 → 0), `iyzico/models.py` (18 → 0), `installments/views.py`
  (18 → 0), plus `models.py`, `decorators.py`, `iyzico/settings.py`,
  `iyzico/utils.py`, `iyzico/monitoring.py`, `retry.py`,
  `subscriptions/models.py`, plus the `0001_initial` migration's
  `CheckConstraint(**{...})` call. The fixes break down as:
  - Roughly 200 trivial annotation additions (return types on
    functions that clearly return one thing, generic parameters on
    `QuerySet[Any]` / `Manager[Any]` / `dict[str, Any]`, and
    narrowing of `dict | None` to `dict[str, Any] | None`).
  - Switched the Iyzico admin classes to the type-aware `@admin.display`
    / `@admin.action` decorators, eliminating the dominant
    `Callable.short_description has no attribute` family of errors.
  - 48 explicit `# type: ignore[code]` comments — every one carries a
    specific check-name (no bare `# type: ignore`). The dominant
    categories are `[misc]` (11) for dynamic-base ViewSet / ModelAdmin
    subclassing, `[import-untyped]` (9) for `rest_framework` and
    `django_filters` (no upstream stubs), `[untyped-decorator]` (8)
    for `@action` (DRF is untyped), and `[type-arg]` (4) for
    `ModelAdmin` which is non-subscriptable at runtime in the Django
    version we target.
  - Two `cast()` adapters in `iyzico/utils.py:parse_iyzico_response`
    where the runtime type is narrower than mypy can prove through
    `json.loads`.
  - `User = get_user_model()` in `subscriptions/manager.py` is now
    swapped for a `TYPE_CHECKING` `User = Any` alias so the dozens
    of `User?.id` resolutions go away without forcing a concrete
    `AUTH_USER_MODEL` choice on integrators.
  - `IyzicoPaymentAdminMixin` learnt a `TYPE_CHECKING`-only
    `ModelAdmin` base so `self.message_user`, `self.get_queryset` etc.
    resolve cleanly while runtime MRO stays unchanged.

  The remaining 107 errors are concentrated in a handful of
  files (`tasks.py`, `serializers.py`, `monitoring.py` already
  cleaned, `stripe.py`, `installments/client.py`, ...) and skew
  toward `[no-any-return]` and `[type-arg]` patterns that need a
  bigger pass; left for follow-up.

- **One real bug surfaced and flagged for follow-up.** In
  `IyzicoClient.delete_card`, `card_user_key` is typed as `str` (and
  required by the Iyzico SDK) but the matching `PaymentMethod`
  model field is `CharField(null=True)`. We added a single
  `# type: ignore[arg-type]` at the admin callsite rather than
  silently coercing `None` to `""` (which would have changed
  runtime behaviour). The right structural fix — either tightening
  the model to `null=False` once data is migrated, or widening the
  client signature to `str | None` and short-circuiting on `None` —
  is left to a follow-up release.

## [0.5.1] - 2026-05-10

Patch release. Four small but load-bearing fixes around concurrency,
outbound resilience, and SAST hygiene. No public API change.

### Fixed

- **Subscription manager webhook race.** `_handle_failed_payment` and
  `_handle_successful_payment` previously did a full-row
  `subscription.save()` after mutating two or three columns. Concurrent
  webhook delivery for the same subscription would field-stomp: the
  helper's UPDATE overwrote sibling columns (e.g. `last_payment_attempt`)
  that another writer had just committed. Both helpers now use
  `save(update_fields=[...])` listing only the columns they mutate, plus
  `updated_at`. Audited every other `subscription.save()` callsite on a
  write path in the same module — `cancel_subscription` (both branches),
  `pause_subscription`, `resume_subscription`, `upgrade_subscription`,
  `downgrade_subscription` (both branches) — and converted them all the
  same way. The lone `super().save(*args, **kwargs)` in
  `PaymentMethod.save()` is a save-override that intentionally persists
  the full row and stays as-is.

### Security

- **Outbound HTTPS timeout for the iyzipay SDK.** The bundled `iyzipay`
  SDK (v1.0.45) constructs `http.client.HTTPSConnection(options['base_url'])`
  in `IyzipayResource.connect` with no `timeout=`. A slow / hung Iyzico
  endpoint could therefore pin a Celery or gunicorn worker thread until
  the kernel-level TCP timeout (often minutes) — a real DoS amplification
  vector. We now monkey-patch `IyzipayResource.connect` at module import
  to thread an explicit timeout through to the underlying
  `HTTPSConnection`. New setting `IYZICO_CONNECTION_TIMEOUT` (default
  30 s) exposes the value. The patch reads the setting lazily on each
  call so test-time `override_settings` is honoured. Documented in
  `SECURITY.md` Production Checklist with a new "Outbound HTTPS timeout"
  subsection. Chose the SDK monkey-patch over `socket.setdefaulttimeout()`
  because the latter would change the timeout of every socket in the
  Python process (Postgres, Redis, internal RPC, …) — far too broad.

### Documentation

- **README "Data Processing & Sub-processors" section.** Adds the
  GDPR Art. 30 / KVKK Art. 16 disclosure that downstream integrators
  need to populate their RoPA. Covers Iyzico (Türkiye, SCC-based
  transfer mechanism) and Stripe (Ireland for EU, US for global,
  Stripe DPA reference), the exhaustive list of fields sent on each
  flow, what the library keeps in the integrator's own DB versus what
  is forwarded to providers, and a worked `cleanup_old_payments`
  invocation cross-linked from `SECURITY.md`.

### Internal

- **Audited 14 Bandit B308/B703 `mark_safe()` hits in admin code.**
  Reviewed every callsite in `eft/admin.py` (4) and
  `providers/iyzico/admin.py` (10). Eight are static-literal calls
  with no interpolation. Three are dynamic builders that route every
  interpolated value through `django.utils.html.escape` before string
  concatenation. Zero risky callsites; no rewrites needed. Added inline
  `# nosec` directives plus an audit comment so future SAST sweeps do
  not have to re-derive the analysis.

## [0.5.0] - 2026-05-08

This release adds Iyzico marketplace ("işyeri gelir paylaşımı") support so
downstream apps no longer have to drop down to the bare `iyzipay` SDK to get
per-basket-item revenue splitting. The change is **fully additive** —
existing v0.4.0 callers see no behaviour change unless they opt in via the
new `marketplace=True` flag, the new `payment_transaction_id` refund kwarg,
or the new `SubMerchantClient` / `AbstractSubMerchantOwner` symbols.

### Added

- **Marketplace basket validation in `IyzicoClient.create_checkout_form`.**
  When any basket item carries `subMerchantKey` / `subMerchantPrice`, the
  client now enforces:
  - the two fields are required *together* on each marketplace item
    (`MARKETPLACE_FIELDS_INCOMPLETE`);
  - empty/whitespace `subMerchantKey` is rejected
    (`MARKETPLACE_EMPTY_SUBMERCHANT_KEY`) — the bare SDK silently no-ops;
  - per-item: `subMerchantPrice <= price`
    (`MARKETPLACE_SUBMERCHANT_EXCEEDS_ITEM_PRICE`);
  - cross-item: `sum(subMerchantPrice) <= paidPrice`
    (`MARKETPLACE_SUBMERCHANT_SUM_EXCEEDS_PAID_PRICE`).

  All comparisons run through `Decimal`, so float drift cannot let bad
  splits through. The validator is exposed publicly as
  `payments_tr.providers.iyzico.client.validate_marketplace_basket` for
  callers that want to pre-check baskets before posting.
- **`IyzicoProvider.create_payment(marketplace=True)`.** Strict mode that
  requires every basket item to be sub-merchant routed and rejects the
  default synthetic single-item basket fallback (which would otherwise
  route 100% of revenue to the platform). `marketplace=False` (the
  default) keeps v0.4.0 behaviour byte-for-byte.
- **`IyzicoProvider.supports_marketplace() -> True`.**
- **New module `payments_tr.providers.iyzico.submerchant`** wrapping the
  Iyzico sub-merchant lifecycle endpoints:
  - `SubMerchantClient.create(...)` — registers a seller, validates IBAN
    via `validate_iban_tr`, TCKN via `validate_tckn` (PERSONAL types),
    VKN via `validate_vkn` (company types). Returns a frozen
    `SubMerchantResponse` dataclass. Type-conditional required fields
    are enforced before the API call.
  - `SubMerchantClient.update(...)` — sends only the fields the caller
    supplies (PATCH semantics), rejects unknown kwargs with a clear
    error code rather than silently dropping them.
  - `SubMerchantClient.retrieve(external_id)` — looks up by the
    caller-side external id (matches the official SDK behaviour).
  - `SubMerchantType` `str`-Enum: `PERSONAL`, `PRIVATE_COMPANY`,
    `LIMITED_OR_JOINT_STOCK_COMPANY`.
  - Transport failures wrap into `PaymentError`; application-level
    failures stay in-band on the response (`is_successful=False`).
- **`AbstractSubMerchantOwner` model mixin** in
  `payments_tr.providers.iyzico.models`. Storage fields for sub-merchant
  key, type, external id, IBAN, TCKN, tax office, VKN, legal company
  title — all optional. `clean()` runs the TR validators when fields are
  non-empty and enforces the same type-conditional required-field rules
  as `SubMerchantClient.create`. **No automatic migration is shipped**;
  consumers add the mixin to their seller model and run
  `makemigrations` themselves.
- **Item-level refund attribution.**
  - `RefundResponse.payment_transaction_id` property exposing the basket
    item id that a marketplace refund applied to.
  - `IyzicoClient.refund_payment(payment_transaction_id=...)` and
    `IyzicoProvider.create_refund(payment_transaction_id=...)` accept an
    item-level transaction id and prefer it over the order-level
    `payment_id` when present. Falls back to `payment_id` for
    non-marketplace refunds (no behaviour change for v0.4.0 callers).

### Documentation

- New top-level `docs/marketplace.md` with the end-to-end flow:
  register sub-merchant → store key on seller model → create payment →
  handle callback → refund.
- New `Marketplace (sub-merchant) payments` section in `README.md` with
  a multi-file-single-seller example.

### Compatibility

- No public symbol from v0.4.0 was removed or renamed. The new
  `marketplace` parameter on `IyzicoClient.create_checkout_form` and
  `IyzicoProvider.create_payment` defaults to `False`. The new
  `payment_transaction_id` parameters default to `None` — non-marketplace
  refunds emit identical request bytes to v0.4.0.
- TRY-only marketplace currency support in v0.5.0 (Iyzico marketplace is
  TR-only in practice).

## [0.4.0] - 2026-05-08

This release is a security-hardening pass driven by an external SAST scan
plus a coordinated audit by three specialised agents (code-level, GDPR/
KVKK compliance, dependency CVE). Several breaking changes are required
to close exploit-grade gaps; migration notes are at the bottom.

### Security — Critical

- **Webhook signature verification is now enforced via a base-class
  template method that subclasses cannot bypass.** Previously the gate
  lived inside an `@abstractmethod` body which Python never executes for
  overridden methods; Stripe in particular soft-failed silently on
  missing signatures. `PaymentProvider.handle_webhook` is now a concrete
  template method that runs the auth check and delegates to a new
  abstract `_process_webhook`. Stripe and Iyzico migrate to the new
  hook; Iyzico opts into alternative auth (server-side token retrieval)
  via `_supports_alternative_webhook_auth() -> True`.
- **`confirm_payment` now accepts `expected_amount` and
  `expected_currency` for TOCTOU defense.** When supplied, the provider
  rejects the result with `error_code="AMOUNT_MISMATCH"` /
  `"CURRENCY_MISMATCH"` if the provider-confirmed values disagree with
  the order the application expected. Defeats the classic "buy a 10 TL
  session, complete a 100 TL checkout" attack. Calling without these
  parameters logs a warning and skips validation; do not rely on the
  warning path in production.
- **`verify_webhook_signature` is fail-closed when the secret is
  missing.** Previously returned `True` (silently accepting every
  payload), now returns `False`.
- **Money formatting in Iyzico request bodies uses `Decimal`, not
  `float`.** `payment.amount / 100` (float division) could introduce
  binary-float drift that breaks the HMAC signature on the request. The
  new `kurus_to_try_string` helper does exact integer-to-Decimal-to-
  string conversion.

### Security — High

- **Webhook replay-protection helpers in `payments_tr.webhooks`.** New
  `build_idempotency_key(provider, result)` and
  `record_webhook_or_skip(model, ...)` helpers leverage the existing
  `AbstractWebhookEvent.event_id` unique constraint to dedup
  duplicate deliveries. Atomic with `IntegrityError` fallback for
  concurrent races.
- **`sanitize_log_data` now masks PII** (TCKN/identityNumber, gsmNumber,
  email, registrationAddress, billingAddress, shippingAddress,
  webhook_secret) in addition to card data and API credentials.
  Required for KVKK Art. 12 / GDPR Art. 32 log hygiene.
- **Token logging uses SHA-256 fingerprints, not prefixes.** The new
  `fingerprint_token` helper returns `"sha256:<12 hex>"`. Even a 6-char
  token prefix is correlatable bearer-credential leakage in retained
  logs; the fingerprint is non-reversible. Affects log lines in
  `client.py` (3 sites), `views.py` (1 site), and
  `CheckoutFormResponse.__str__`.
- **Webhook-receiving view (`iyzico_webhook_view`) now passes the parsed
  payload through `sanitize_log_data` before logging at DEBUG**
  (previously emitted a raw `f-string` with full payload).
- **`X-Forwarded-For` parsing now handles `203.0.113.5:54321` and
  `[2001:db8::1]:8080` formats.** AWS ALB and certain nginx
  configurations emit these legitimate forms; the previous code
  silently downgraded such IPs to `REMOTE_ADDR`, breaking PCI-DSS
  buyer-IP records. Implemented via the new
  `_strip_port_and_brackets` helper.

### Security — Operational

- **`cleanup_old_payments` now refuses to run without `--keep-successful`.**
  The previous default of 730 days (2 years) violated common financial
  retention obligations (TR VUK: 5 years; many EU member states: 7-10
  years). The command now requires an explicit value and warns when it
  is below 1825 days.
- **`pyproject.toml` Django bound tightened** to skip CVE-affected
  versions surfaced by `pip-audit`: `django>=4.2.30,!=5.0.*,!=5.1.*,<7.0`.
  Excludes EOL series 5.0 and 5.1 outright.
- **SECURITY.md rewritten** with code samples that reference
  actually-shipped APIs (the previous draft referenced
  `IyzicoWebhookVerifier`, `IdempotencyManager`, `RateLimiter`,
  `AuditLogger` modules that did not exist). Disclosure email is now
  real (`emre@aladagemre.com`).

### Added

- `payments_tr.webhooks.build_idempotency_key`
- `payments_tr.webhooks.record_webhook_or_skip`
- `payments_tr.providers.iyzico.utils.kurus_to_try_string`
- `payments_tr.providers.iyzico.utils.fingerprint_token`
- `payments_tr.providers.iyzico.utils._strip_port_and_brackets`
- 14 + 11 + 8 + 6 + 12 = 51 new tests across the surfaces above.

### Changed

- Test suite: 1187 → 1271+ passing tests (~7% expansion of coverage).
- `Development Status` classifier bumped from Alpha to Beta.

### Migration guide (v0.3.x → v0.4.0)

#### 1. Subclass providers must override `_process_webhook`, not `handle_webhook`

```python
# Before (v0.3.x)
class MyProvider(PaymentProvider):
    def handle_webhook(self, payload, signature=None, **kwargs):
        ...

# After (v0.4.0)
class MyProvider(PaymentProvider):
    def _process_webhook(self, payload, signature=None, **kwargs):
        ...

    # If the provider doesn't use HMAC signatures (e.g., uses
    # server-side token retrieval like Iyzico):
    def _supports_alternative_webhook_auth(self) -> bool:
        return True
```

Subclasses that fail to migrate raise `TypeError: Can't instantiate
abstract class MyProvider with abstract method _process_webhook`.

#### 2. Stripe `handle_webhook` now raises on missing signature

```python
# Before: returned WebhookResult(success=False, error_message="Missing Stripe signature")
# After: raises ValueError
try:
    result = stripe_provider.handle_webhook(payload, signature=sig)
except ValueError:
    return HttpResponseForbidden("Missing signature")
```

#### 3. `confirm_payment` strongly recommends expected amount/currency

```python
# Strongly recommended new pattern:
result = provider.confirm_payment(
    token,
    expected_amount=order.amount_kurus,  # int, smallest currency unit
    expected_currency="TRY",
)
if not result.success:
    if result.error_code in ("AMOUNT_MISMATCH", "CURRENCY_MISMATCH"):
        log_security_event(result)  # potential TOCTOU attempt
    return reject()
```

The old single-arg call still works but logs a warning.

#### 4. `verify_webhook_signature` no longer fail-opens

If your code passed an empty `secret` and relied on `True`, it will
now get `False`. Configure `IYZICO_WEBHOOK_SECRET`.

#### 5. `cleanup_old_payments` requires `--keep-successful`

```bash
# Before:
python manage.py cleanup_old_payments --model myapp.models.Payment

# After (must specify retention):
python manage.py cleanup_old_payments \
    --model myapp.models.Payment \
    --keep-successful 1825   # 5y for TR VUK; 2555+ for EU
```

#### 6. Log-line format changes

If you grep logs for `token_prefix=...***`, switch to
`token=sha256:...`. Same data, non-reversible.

## [0.3.2] - 2026-02-05

### Fixed

- Add migration to rename iyzico subscription indexes to Django's auto-generated naming convention and remove unused SubscriptionPayment indexes.

## [0.3.1] - 2026-02-04

### Fixed

- Add initial iyzico subscription migrations to ensure proper table creation order.

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

[0.3.2]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.3.2
[0.3.1]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.3.1
[0.3.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.3.0
[0.2.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.2.0
[0.1.0]: https://github.com/aladagemre/django-payments-tr/releases/tag/v0.1.0
