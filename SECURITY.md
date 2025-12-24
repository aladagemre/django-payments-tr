# Security Best Practices

This document outlines security best practices for using django-payments-tr in production.

## Table of Contents

- [Webhook Security](#webhook-security)
- [API Key Management](#api-key-management)
- [Rate Limiting](#rate-limiting)
- [Audit Logging](#audit-logging)
- [Data Protection](#data-protection)
- [Production Checklist](#production-checklist)

## Webhook Security

### 1. Always Verify Webhook Signatures

**Critical:** Never process webhooks without verifying signatures in production.

```python
# settings.py
PAYMENTS_TR = {
    "SECURITY": {
        "VERIFY_WEBHOOKS": True,  # Always True in production
        "IYZICO_WEBHOOK_SECRET": os.environ.get("IYZICO_WEBHOOK_SECRET"),
    }
}
```

### 2. Use HTTPS for Webhook Endpoints

- Configure webhook URLs with HTTPS only
- Use valid SSL/TLS certificates
- Redirect HTTP to HTTPS

```python
# Example webhook endpoint
from django.views.decorators.csrf import csrf_exempt
from payments_tr import get_payment_provider
from payments_tr.security import IyzicoWebhookVerifier

@csrf_exempt
def iyzico_webhook(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # Verify signature
    verifier = IyzicoWebhookVerifier()
    signature = request.headers.get("X-Iyzico-Signature")

    if not verifier.verify(request.body, signature):
        logger.warning("Invalid webhook signature")
        return HttpResponseForbidden("Invalid signature")

    # Process webhook
    provider = get_payment_provider("iyzico")
    result = provider.handle_webhook(request.body, signature)

    return JsonResponse({"status": "received"})
```

### 3. Implement Idempotency

Prevent duplicate processing of webhooks:

```python
from payments_tr.security import IdempotencyManager

manager = IdempotencyManager()

@csrf_exempt
def process_webhook(request):
    event_id = request.headers.get("X-Event-ID")

    if not manager.check(event_id):
        logger.info(f"Webhook {event_id} already processed")
        return JsonResponse({"status": "already_processed"})

    # Process webhook
    process_payment_event(request.body)

    # Mark as processed
    manager.mark_processed(event_id)

    return JsonResponse({"status": "processed"})
```

## API Key Management

### 1. Never Commit Credentials

- Use environment variables for all secrets
- Add `.env` to `.gitignore`
- Use different credentials for dev/staging/production

```bash
# .env (NEVER commit this file)
STRIPE_API_KEY=sk_live_xxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxx
IYZICO_API_KEY=xxxxx
IYZICO_SECRET_KEY=xxxxx
```

### 2. Rotate Keys Regularly

- Rotate API keys every 90 days
- Rotate webhook secrets every 180 days
- Have a key rotation procedure documented

### 3. Use Test Keys in Development

```python
# settings.py
import os

PAYMENTS_TR = {
    "STRIPE_API_KEY": os.environ.get(
        "STRIPE_API_KEY",
        "sk_test_xxxxx" if DEBUG else None
    ),
}

# Fail fast in production if keys are missing
if not DEBUG and not PAYMENTS_TR.get("STRIPE_API_KEY"):
    raise ImproperlyConfigured("STRIPE_API_KEY not set in production")
```

### 4. Restrict Key Permissions

- Use restricted API keys when possible
- Stripe: Create restricted keys with minimal permissions
- iyzico: Use separate API keys for different environments

## Rate Limiting

### 1. Enable Rate Limiting for Webhooks

```python
# settings.py
PAYMENTS_TR = {
    "SECURITY": {
        "ENABLE_RATE_LIMITING": True,
        "RATE_LIMIT_REQUESTS": 100,  # per minute
        "RATE_LIMIT_WINDOW": 60,
    }
}
```

### 2. Implement in Webhook Views

```python
from payments_tr.security import RateLimiter

limiter = RateLimiter()

@csrf_exempt
def webhook_view(request):
    # Get client identifier (IP or API key)
    identifier = request.META.get("REMOTE_ADDR")

    if not limiter.allow(identifier):
        logger.warning(f"Rate limit exceeded for {identifier}")
        return HttpResponse("Rate limit exceeded", status=429)

    # Process webhook
    return process_webhook(request)
```

## Audit Logging

### 1. Enable Audit Logging

```python
# settings.py
PAYMENTS_TR = {
    "SECURITY": {
        "ENABLE_AUDIT_LOG": True,
        "AUDIT_LOG_SENSITIVE_DATA": False,  # Never True in production
    }
}
```

### 2. Log Sensitive Operations

```python
from payments_tr.security import AuditLogger

audit = AuditLogger()

def process_refund(request, payment_id):
    user = request.user
    payment = Payment.objects.get(id=payment_id)

    # Create refund
    provider = get_payment_provider()
    result = provider.create_refund(
        payment,
        amount=request.POST.get("amount"),
        reason=request.POST.get("reason")
    )

    # Audit log
    audit.log_refund(
        user=str(user),
        payment_id=payment_id,
        provider=provider.provider_name,
        success=result.success,
        amount=request.POST.get("amount"),
        reason=request.POST.get("reason"),
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    return result
```

### 3. Monitor Audit Logs

- Set up alerts for failed operations
- Review audit logs regularly
- Store logs securely (separate from application logs)

```python
# logging configuration
LOGGING = {
    "handlers": {
        "audit_file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/payments/audit.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 10,
            "formatter": "json",
        },
    },
    "loggers": {
        "payments_tr.audit": {
            "handlers": ["audit_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
```

## Data Protection

### 1. Never Store Card Data

- **NEVER** store full card numbers
- **NEVER** store CVV/CVC codes
- Use provider tokens instead

```python
# ✗ BAD - Don't do this
payment.card_number = "4242424242424242"

# ✓ GOOD - Store provider token
payment.stripe_payment_id = "pi_xxxxx"
```

### 2. Encrypt Sensitive Data

- Use Django's field encryption for PII
- Encrypt database backups
- Use encrypted connections (SSL/TLS) for all external APIs

```python
from django.db import models
from django_cryptography.fields import encrypt

class Payment(models.Model):
    # Encrypt sensitive fields
    customer_email = encrypt(models.EmailField())
    billing_address = encrypt(models.TextField())
```

### 3. Comply with PCI DSS

- Never handle card data directly in your application
- Use provider-hosted checkout forms (Stripe Checkout, iyzico Checkout)
- Use payment provider SDKs that handle card data

### 4. GDPR/KVKK Compliance

```python
# Implement data deletion
def delete_user_payment_data(user_id):
    # Delete or anonymize payment records
    Payment.objects.filter(user_id=user_id).update(
        customer_email="deleted@example.com",
        customer_name="DELETED",
        billing_address="",
    )
```

## Production Checklist

### Before Going Live

- [ ] All API keys are production keys (not test keys)
- [ ] Webhook signature verification is enabled
- [ ] HTTPS is enforced for all payment endpoints
- [ ] Rate limiting is enabled
- [ ] Audit logging is configured
- [ ] No sensitive data in logs (`AUDIT_LOG_SENSITIVE_DATA=False`)
- [ ] Database backups are encrypted
- [ ] Error monitoring is configured (Sentry, etc.)
- [ ] Webhook endpoints are not publicly listed
- [ ] CSRF protection is properly configured
- [ ] Security headers are set (CSP, X-Frame-Options, etc.)

### Configuration Validation

Run the configuration validator:

```bash
python manage.py check_providers
python -m payments_tr.cli validate-config
```

### Security Headers

```python
# settings.py
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

## Incident Response

### If API Keys Are Compromised

1. **Immediately** revoke compromised keys
2. Generate new keys
3. Update environment variables
4. Deploy updated configuration
5. Review audit logs for unauthorized activity
6. Notify payment provider if needed

### If Webhook Secret Is Compromised

1. Generate new webhook secret
2. Update configuration
3. Update webhook endpoints in provider dashboard
4. Deploy changes
5. Monitor for suspicious webhook activity

## Monitoring and Alerts

### Set Up Alerts For

- Failed webhook signature verifications
- Rate limit exceeded events
- Failed refund attempts
- Unusual payment patterns
- API authentication errors

```python
# Example: Alert on failed webhooks
from django.core.mail import mail_admins

def handle_webhook_failure(event_id, error):
    logger.error(f"Webhook {event_id} failed: {error}")

    if should_alert(error):
        mail_admins(
            subject=f"Payment Webhook Failure: {event_id}",
            message=f"Error: {error}",
            fail_silently=False,
        )
```

## Additional Resources

- [PCI DSS Compliance Guide](https://www.pcisecuritystandards.org/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Stripe Security Best Practices](https://stripe.com/docs/security/guide)
- [iyzico Security Documentation](https://dev.iyzipay.com/)

## Reporting Security Issues

If you discover a security vulnerability, please email security@example.com. Do not open a public GitHub issue.
