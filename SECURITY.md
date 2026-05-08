# Security Best Practices

This document covers production-grade hardening for django-payments-tr.
All code samples reference APIs that ship with the package; nothing
here is illustrative-only.

## Table of Contents

- [Reporting a Vulnerability](#reporting-a-vulnerability)
- [Webhook Security](#webhook-security)
- [Replay Protection (Idempotency)](#replay-protection-idempotency)
- [API Key Management](#api-key-management)
- [Rate Limiting](#rate-limiting)
- [Audit Logging](#audit-logging)
- [Data Protection](#data-protection)
- [Production Checklist](#production-checklist)
- [Incident Response](#incident-response)

## Reporting a Vulnerability

Email **emre@aladagemre.com** with details, reproduction steps, and
impact assessment. **Do not** open a public GitHub issue for
unpatched vulnerabilities. Expect an acknowledgement within 72 hours.

## Webhook Security

### 1. Always verify webhook signatures

The base provider's `handle_webhook` template method enforces
signature presence; subclass providers cannot bypass it. Stripe raises
`ValueError` on missing signatures; Iyzico opts into alternative auth
(server-side token retrieval) and the helper
`verify_webhook_signature` is used by the shipped Iyzico webhook view.

```python
# settings.py
IYZICO_WEBHOOK_SECRET = os.environ["IYZICO_WEBHOOK_SECRET"]
STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
```

`verify_webhook_signature(payload, signature, secret)` is **fail-closed**
in v0.4.0+: if `secret` is empty, it returns `False` and refuses to
accept the webhook. Earlier versions returned `True` in that case.

```python
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden
from payments_tr import get_payment_provider
from payments_tr.providers.iyzico.utils import verify_webhook_signature
from payments_tr.providers.iyzico.settings import iyzico_settings

@csrf_exempt
def iyzico_webhook(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    signature = request.headers.get("X-Iyzico-Signature", "")
    if not verify_webhook_signature(
        request.body, signature, iyzico_settings.webhook_secret
    ):
        return HttpResponseForbidden("Invalid signature")

    provider = get_payment_provider("iyzico")
    result = provider.handle_webhook(request.body, signature=signature)
    return JsonResponse({"status": "received" if result.success else "rejected"})
```

### 2. Use HTTPS for webhook endpoints

- Configure webhook URLs with HTTPS only.
- Use valid SSL/TLS certificates.
- Redirect HTTP to HTTPS.

### 3. Restrict by source IP

Iyzico publishes a list of webhook source IPs. Configure
`IYZICO_WEBHOOK_ALLOWED_IPS` to enforce the whitelist:

```python
IYZICO_WEBHOOK_ALLOWED_IPS = ["52.20.0.0/16", "..."]  # from Iyzico docs
IYZICO_TRUST_X_FORWARDED_FOR = True  # only if behind a trusted proxy
```

The `get_client_ip` helper validates `X-Forwarded-For` entries
defensively (port suffix stripping, IPv6 bracket handling, format
validation) before checking the allowlist.

## Replay Protection (Idempotency)

Payment providers deliver webhooks at-least-once: the same event may
arrive multiple times after timeouts, retries, or replay attacks.
Without dedup, downstream signal handlers will mark an order paid
twice or refund twice.

The package ships an `AbstractWebhookEvent` model and helpers in
`payments_tr.webhooks`:

```python
# myapp/models.py
from payments_tr.webhooks import AbstractWebhookEvent

class IyzicoWebhookEvent(AbstractWebhookEvent):
    class Meta(AbstractWebhookEvent.Meta):
        db_table = "iyzico_webhook_events"
```

```python
# myapp/views.py
from payments_tr import get_payment_provider
from payments_tr.webhooks import build_idempotency_key, record_webhook_or_skip
from myapp.models import IyzicoWebhookEvent

@csrf_exempt
def iyzico_webhook(request):
    provider = get_payment_provider("iyzico")
    result = provider.handle_webhook(request.body)
    if not result.success:
        return JsonResponse({"status": "rejected"}, status=400)

    event_id = build_idempotency_key("iyzico", result)
    event, created = record_webhook_or_skip(
        IyzicoWebhookEvent,
        provider="iyzico",
        event_id=event_id,
        event_type=result.event_type or "",
        payload=result.raw_response or {},
    )
    if not created:
        # Duplicate — return 200 so provider stops retrying.
        return JsonResponse({"status": "duplicate"}, status=200)

    # First time — fan out to business logic.
    fulfill_order(result.payment_id)
    event.mark_success()
    return JsonResponse({"status": "ok"}, status=200)
```

The `event_id` column has `unique=True`, so concurrent duplicate
deliveries are resolved by an `IntegrityError` fallback inside
`record_webhook_or_skip`.

## TOCTOU Defense on Confirmation

Always pass `expected_amount` (smallest unit, e.g. kuruş) and
`expected_currency` to `confirm_payment`. The provider rejects with
`error_code="AMOUNT_MISMATCH"` / `"CURRENCY_MISMATCH"` if the
provider-confirmed values disagree, defeating the classic "buy a 10 TL
session, complete a 100 TL checkout" attack.

```python
result = provider.confirm_payment(
    token,
    expected_amount=order.amount_kurus,
    expected_currency="TRY",
)
if not result.success:
    log_security_event(result.error_code, ...)
    return reject()
```

Calling without these parameters logs a warning and skips validation —
do not ship that path to production.

## API Key Management

### 1. Never commit credentials

- Use environment variables for all secrets.
- Add `.env` to `.gitignore`.
- Use different credentials for dev/staging/production.

```bash
# .env (NEVER commit)
STRIPE_API_KEY=sk_live_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
IYZICO_API_KEY=xxxxx
IYZICO_SECRET_KEY=xxxxx
IYZICO_WEBHOOK_SECRET=xxxxx
```

### 2. Rotate keys regularly

- Rotate API keys every 90 days.
- Rotate webhook secrets every 180 days.
- Document the rotation procedure.

### 3. Fail fast in production

```python
# settings.py
if not DEBUG:
    for var in ("IYZICO_API_KEY", "IYZICO_SECRET_KEY", "IYZICO_WEBHOOK_SECRET"):
        if not os.environ.get(var):
            raise ImproperlyConfigured(f"{var} not set in production")
```

### 4. Restrict key permissions

- **Stripe**: Create restricted keys with minimal permissions.
- **iyzico**: Use separate API keys for different environments.

## Rate Limiting

The shipped iyzico webhook view (`payments_tr.providers.iyzico.views.webhook_view`)
has built-in IP-based rate limiting via Django's cache. Tune via:

```python
# settings.py
IYZICO_WEBHOOK_RATE_LIMIT = 100   # requests per window
IYZICO_WEBHOOK_RATE_WINDOW = 60   # seconds
```

For custom views, wrap with django-ratelimit or your platform's
built-in (Cloudflare, AWS WAF, nginx `limit_req`).

## Audit Logging

> **No audit-log model is shipped with the package.** Consumers are
> responsible for recording who initiated each payment / refund /
> subscription change, when, from what IP. PCI-DSS Req. 10 and KVKK
> Art. 12 require this for forensic readiness.

Recommended: an append-only model written from a centralised helper
in your application:

```python
# myapp/models.py
class PaymentAuditEvent(models.Model):
    actor_user_id = models.IntegerField(null=True)  # null = system
    payment_id = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64)  # 'created' | 'refunded' | ...
    before = models.JSONField()
    after = models.JSONField()
    ip_address = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
```

Hook into payment / refund flows from your application code and write
one row per state transition. Ship the table to a write-once destination
(SIEM, S3 with object-lock) for tamper evidence.

## Data Protection

### 1. Never store card data

- **NEVER** store full card numbers, CVV/CVC, or full expiry dates.
- Use provider tokens (`payment.iyzico_payment_id`,
  `payment.stripe_payment_intent_id`) — the provider holds the card.

The shipped `AbstractIyzicoPayment` model has no `card_number` /
`cvv` columns by schema design.

### 2. PII masking in logs

`sanitize_log_data` in `payments_tr.providers.iyzico.utils` masks
card data **and** PII (TCKN, GSM, email, billing/shipping address)
before lines reach the logger. Use it whenever you log a request or
response body:

```python
logger.debug("Iyzico request: %s", sanitize_log_data(request_data))
```

For tokens, log a fingerprint, not a prefix:

```python
from payments_tr.providers.iyzico.utils import fingerprint_token
logger.info("Token=%s", fingerprint_token(token))  # 'sha256:abcdef012345'
```

### 3. Encrypt sensitive fields at rest

The `AbstractPayment.raw_response` field stores provider responses
(needed for refund correlation). Even after `sanitize_log_data`, it
contains buyer email/name/IP. Wrap it with field-level encryption if
your threat model includes DB compromise:

```python
from django_cryptography.fields import encrypt

class MyPayment(AbstractPayment):
    raw_response = encrypt(models.JSONField(default=dict))
```

### 4. GDPR / KVKK erasure

> **No erasure helper is shipped with the package.** Consumers must
> implement subject erasure carefully because financial records are
> often subject to multi-year retention obligations that conflict
> with right-to-erasure.

Recommended pattern: pseudonymize, do not hard-delete:

```python
def pseudonymize_payment_subject(user):
    Payment.objects.filter(user=user).update(
        buyer_email="erased@example.invalid",
        buyer_name="ERASED",
        buyer_surname="ERASED",
        # Preserve amount/currency/status — needed for tax retention.
    )
```

Document the pseudonymization in your privacy notice and DPA.

### 5. Data retention

Use `cleanup_old_payments` with an explicit `--keep-successful` value
matching your local statutory minimum:

- Turkey (VUK): 5 years (`--keep-successful 1825`)
- Many EU member states: 7-10 years (`--keep-successful 2555` to `3650`)

The command refuses to run without `--keep-successful` (v0.4.0+) and
warns if the value is below 1825 days.

```bash
python manage.py cleanup_old_payments \
    --model myapp.models.Payment \
    --keep-successful 1825 \
    --days 365
```

## Production Checklist

- [ ] `IYZICO_WEBHOOK_SECRET` is set (fail-closed without it)
- [ ] `IYZICO_WEBHOOK_ALLOWED_IPS` is set to the official Iyzico IPs
- [ ] `STRIPE_WEBHOOK_SECRET` is set
- [ ] All API keys are production keys (not test keys)
- [ ] HTTPS enforced for all payment endpoints
- [ ] `confirm_payment` is always called with `expected_amount` and
      `expected_currency`
- [ ] A concrete `WebhookEvent` model is created and `record_webhook_or_skip`
      runs before downstream side effects
- [ ] An audit log table is in place (consumer-side)
- [ ] `cleanup_old_payments` is scheduled with a jurisdiction-appropriate
      `--keep-successful` value
- [ ] Database backups are encrypted at rest
- [ ] Error monitoring is configured (Sentry, etc.)
- [ ] Security headers are set (CSP, HSTS, X-Frame-Options)

```python
# settings.py — security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## Incident Response

### If API keys are compromised

1. **Immediately** revoke the compromised keys in the provider dashboard.
2. Generate new keys.
3. Update environment variables / secret manager.
4. Deploy updated configuration.
5. Review audit logs for unauthorized activity.
6. Notify the payment provider if a transaction was made under the
   compromised key.

### If webhook secret is compromised

1. Generate a new webhook secret in the provider dashboard.
2. Update `IYZICO_WEBHOOK_SECRET` / `STRIPE_WEBHOOK_SECRET`.
3. Deploy.
4. Monitor for `error: invalid signature` in logs — confirms the
   rotation took effect.

## Monitoring & Alerts

Set up alerts for:

- Failed webhook signature verifications
  (`grep "Webhook signature mismatch" application.log`)
- `AMOUNT_MISMATCH` / `CURRENCY_MISMATCH` PaymentResults — these
  indicate either a bug or an active TOCTOU attack
- Rate-limit exceeded events
- Failed refund attempts
- Unusual payment patterns (volume / geography)

## Additional Resources

- [PCI DSS Compliance Guide](https://www.pcisecuritystandards.org/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Stripe Security Best Practices](https://stripe.com/docs/security/guide)
- [iyzico Security Documentation](https://dev.iyzipay.com/)
- [KVKK Resmi Web Sitesi](https://www.kvkk.gov.tr/)
