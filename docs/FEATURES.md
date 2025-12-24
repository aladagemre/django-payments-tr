# Advanced Features Guide

This guide covers the advanced features added to django-payments-tr for production use.

## Table of Contents

- [Security Features](#security-features)
- [Payment Signals](#payment-signals)
- [Webhook Management](#webhook-management)
- [Retry Logic](#retry-logic)
- [Async Support](#async-support)
- [Logging](#logging)
- [Health Checks](#health-checks)
- [Decorators](#decorators)
- [Management Commands](#management-commands)
- [Testing Utilities](#testing-utilities)

## Security Features

### Webhook Signature Verification

Verify webhook authenticity to prevent spoofing attacks.

#### iyzico Webhook Verification

```python
from payments_tr.security import IyzicoWebhookVerifier

# In settings.py
PAYMENTS_TR = {
    "SECURITY": {
        "IYZICO_WEBHOOK_SECRET": "your-webhook-secret",
        "VERIFY_WEBHOOKS": True,
    }
}

# In your webhook view
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def iyzico_webhook(request):
    verifier = IyzicoWebhookVerifier()
    signature = request.headers.get("X-Iyzico-Signature")

    if not verifier.verify(request.body, signature):
        return HttpResponseForbidden("Invalid signature")

    # Process webhook...
    return JsonResponse({"status": "received"})
```

### Rate Limiting

Protect webhook endpoints from abuse.

```python
from payments_tr.security import RateLimiter

# Configure in settings
PAYMENTS_TR = {
    "SECURITY": {
        "ENABLE_RATE_LIMITING": True,
        "RATE_LIMIT_REQUESTS": 100,  # requests
        "RATE_LIMIT_WINDOW": 60,     # seconds
    }
}

# Use in views
limiter = RateLimiter()

@csrf_exempt
def webhook_view(request):
    identifier = request.META.get("REMOTE_ADDR")

    if not limiter.allow(identifier):
        return HttpResponse("Rate limit exceeded", status=429)

    # Process webhook...
```

### Audit Logging

Track sensitive operations for compliance.

```python
from payments_tr.security import AuditLogger

audit = AuditLogger()

def process_refund(payment, amount, user):
    provider = get_payment_provider()
    result = provider.create_refund(payment, amount=amount)

    # Log the operation
    audit.log_refund(
        user=str(user),
        payment_id=payment.id,
        provider=provider.provider_name,
        success=result.success,
        amount=amount,
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    return result
```

### Idempotency

Prevent duplicate webhook processing.

```python
from payments_tr.security import IdempotencyManager

manager = IdempotencyManager()

def process_webhook(event_id, data):
    if not manager.check(event_id):
        return  # Already processed

    # Process webhook...
    process_payment(data)

    # Mark as processed
    manager.mark_processed(event_id)
```

Or use as a decorator:

```python
from payments_tr.security import idempotent

@idempotent(lambda webhook_id: f"webhook:{webhook_id}")
def process_webhook(webhook_id, data):
    # This will only run once per webhook_id
    process_payment(data)
```

## Payment Signals

Connect to payment lifecycle events.

### Available Signals

```python
from payments_tr import signals
from django.dispatch import receiver

@receiver(signals.payment_created)
def on_payment_created(sender, payment, provider, result, **kwargs):
    print(f"Payment {payment.id} created with {provider}")

@receiver(signals.payment_confirmed)
def on_payment_confirmed(sender, payment, provider, result, **kwargs):
    # Send confirmation email
    send_confirmation_email(payment.user)

@receiver(signals.payment_failed)
def on_payment_failed(sender, payment, provider, result, error_message, **kwargs):
    # Log failure, notify admin
    logger.error(f"Payment {payment.id} failed: {error_message}")

@receiver(signals.payment_refunded)
def on_payment_refunded(sender, payment, provider, result, amount, reason, **kwargs):
    # Process refund logic
    update_order_status(payment.order)

@receiver(signals.webhook_received)
def on_webhook_received(sender, provider, event_type, result, payload, **kwargs):
    # Log webhook event
    logger.info(f"Webhook received: {provider} - {event_type}")

@receiver(signals.eft_approved)
def on_eft_approved(sender, payment, approved_by, approval_service, **kwargs):
    # Send approval notification
    notify_user(payment.user, "EFT payment approved")

@receiver(signals.eft_rejected)
def on_eft_rejected(sender, payment, rejected_by, reason, approval_service, **kwargs):
    # Send rejection notification
    notify_user(payment.user, f"EFT payment rejected: {reason}")
```

## Webhook Management

### Webhook Event Logging

Store and replay webhooks.

#### Create Webhook Model

```python
# models.py
from payments_tr.webhooks import AbstractWebhookEvent

class WebhookEvent(AbstractWebhookEvent):
    class Meta:
        db_table = 'webhook_events'
        indexes = [
            models.Index(fields=['provider', 'event_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['processed', 'success']),
        ]
```

#### Configure in Settings

```python
# settings.py
PAYMENTS_TR = {
    "WEBHOOK_MODEL": "myapp.WebhookEvent",
}
```

#### Log Webhooks

```python
def process_webhook(request):
    # Create webhook event
    event = WebhookEvent.objects.create(
        provider="stripe",
        event_type="payment.succeeded",
        event_id=request.data.get("id"),
        payload=request.data,
        headers=dict(request.headers),
        signature=request.headers.get("Stripe-Signature"),
        ip_address=request.META.get("REMOTE_ADDR"),
    )

    try:
        # Process webhook
        provider = get_payment_provider()
        result = provider.handle_webhook(request.body)

        if result.success:
            event.mark_success()
        else:
            event.mark_failed(result.error_message)
    except Exception as e:
        event.mark_failed(str(e))
        event.schedule_retry(delay_seconds=60)
```

### Webhook Replay

Replay failed or pending webhooks.

```python
from payments_tr.webhooks import WebhookReplayer
from myapp.models import WebhookEvent

replayer = WebhookReplayer(WebhookEvent)

def process_event(event):
    provider = get_payment_provider(event.provider)
    return provider.handle_webhook(event.payload, event.signature)

# Replay failed webhooks
stats = replayer.replay_failed(process_event)
print(f"Replayed {stats['success']}/{stats['total']} webhooks")

# Replay webhooks for specific provider
stats = replayer.replay_by_provider("stripe", process_event)

# Cleanup old webhooks (older than 30 days)
count = replayer.cleanup_old_events(days=30)
```

## Retry Logic

Automatically retry failed operations.

### Using Decorator

```python
from payments_tr.retry import retry_with_backoff

@retry_with_backoff(max_attempts=3, initial_delay=1.0)
def create_payment(payment):
    provider = get_payment_provider()
    return provider.create_payment(payment)

# Will retry up to 3 times with exponential backoff
result = create_payment(payment)
```

### Using Context Manager

```python
from payments_tr.retry import RetryableOperation

retry = RetryableOperation(max_attempts=3, exponential_base=2)

for attempt in retry:
    with attempt:
        result = provider.create_payment(payment)
        break  # Success, exit retry loop
```

### Async Retry

```python
from payments_tr.retry import async_retry_with_backoff

@async_retry_with_backoff(max_attempts=3)
async def create_payment_async(payment):
    provider = await get_async_payment_provider()
    return await provider.create_payment_async(payment)
```

## Async Support

Use async/await for non-blocking operations.

### Basic Usage

```python
from payments_tr import get_async_payment_provider

async def process_payment(payment):
    provider = get_async_payment_provider("stripe")

    # All operations are async
    result = await provider.create_payment_async(
        payment,
        callback_url="https://example.com/callback"
    )

    return result
```

### With Django Async Views

```python
from django.http import JsonResponse
from payments_tr import get_async_payment_provider

async def create_payment_view(request):
    provider = get_async_payment_provider()

    result = await provider.create_payment_async(
        payment,
        callback_url=request.build_absolute_uri('/callback/')
    )

    return JsonResponse(result.to_dict())
```

## Logging

Comprehensive logging with structured data.

### Configure Logging

```python
# settings.py
PAYMENTS_TR = {
    "LOGGING": {
        "LEVEL": "INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
        "FILE": "/var/log/django/payments.log",
        "DEBUG": False,
        "FILTER_SENSITIVE_DATA": True,
    }
}

# In your app's AppConfig
from payments_tr.logging_config import setup_django_logging

class MyAppConfig(AppConfig):
    def ready(self):
        setup_django_logging()
```

### Using Payment Logger

```python
from payments_tr.logging_config import get_logger

logger = get_logger()

# Log payment events
logger.payment_created(
    payment_id=payment.id,
    provider="stripe",
    amount=payment.amount,
    currency="TRY"
)

logger.payment_confirmed(
    payment_id=payment.id,
    provider="stripe",
    provider_payment_id=result.provider_payment_id
)

logger.payment_failed(
    payment_id=payment.id,
    provider="stripe",
    error="Card declined",
    error_code="card_declined"
)

logger.webhook_received(
    provider="stripe",
    event_type="payment.succeeded",
    event_id="evt_123"
)
```

## Health Checks

Monitor provider health and configuration.

### Check Single Provider

```python
from payments_tr.health import ProviderHealthChecker
from payments_tr import get_payment_provider

checker = ProviderHealthChecker()
provider = get_payment_provider("stripe")

result = checker.check_provider(provider, test_mode=True)

print(f"Provider: {result.provider}")
print(f"Healthy: {result.healthy}")
print(f"Message: {result.message}")
print(f"Response time: {result.response_time_ms}ms")
```

### Check All Providers

```python
checker = ProviderHealthChecker()
results = checker.check_all_providers()

for name, result in results.items():
    status = "✓" if result.healthy else "✗"
    print(f"{status} {name}: {result.message}")
```

### Django Health Check Integration

```python
# views.py
from django.http import JsonResponse
from payments_tr.health import ProviderHealthChecker

def health_check(request):
    checker = ProviderHealthChecker()
    results = checker.check_all_providers()

    all_healthy = all(r.healthy for r in results.values())
    status_code = 200 if all_healthy else 503

    return JsonResponse(
        {
            "status": "healthy" if all_healthy else "unhealthy",
            "providers": {
                name: result.to_dict()
                for name, result in results.items()
            }
        },
        status=status_code
    )
```

## Decorators

Useful decorators for payment operations.

```python
from payments_tr.decorators import (
    atomic_payment_operation,
    log_payment_operation,
    measure_payment_time,
    with_audit_log,
    cache_provider_result,
)

# Wrap in database transaction
@atomic_payment_operation
def process_payment_and_update_order(payment, order):
    result = provider.create_payment(payment)
    if result.success:
        order.status = 'paid'
        order.save()
    return result

# Log operation start/end
@log_payment_operation(log_start=True, log_end=True)
def create_payment(payment, provider):
    return provider.create_payment(payment)

# Measure execution time
@measure_payment_time
def expensive_operation(payment):
    return provider.create_payment(payment)

# Audit log
@with_audit_log('refund')
def process_refund(payment, amount, user):
    return provider.create_refund(payment, amount=amount)

# Cache results
@cache_provider_result(ttl=60)
def get_payment_status(provider_payment_id):
    return provider.get_payment_status(provider_payment_id)
```

## Management Commands

Django management commands for common tasks.

### Check Provider Health

```bash
# Check all providers
python manage.py check_providers

# Check specific provider
python manage.py check_providers --provider stripe

# Check production configuration
python manage.py check_providers --production --verbose
```

### Replay Webhooks

```bash
# Replay failed webhooks
python manage.py replay_webhooks --failed

# Replay pending webhooks
python manage.py replay_webhooks --pending

# Replay for specific provider
python manage.py replay_webhooks --provider stripe

# Limit number of webhooks
python manage.py replay_webhooks --failed --limit 10

# Disable exponential backoff
python manage.py replay_webhooks --failed --no-backoff
```

### Cleanup Old Webhooks

```bash
# Delete webhooks older than 30 days
python manage.py cleanup_webhooks --days 30

# Dry run (show what would be deleted)
python manage.py cleanup_webhooks --days 7 --dry-run
```

## Testing Utilities

Mock providers and test helpers.

### Using Mock Provider

```python
from payments_tr.testing import MockPaymentProvider

def test_payment_creation():
    provider = MockPaymentProvider()

    # Configure mock to succeed
    provider.set_next_result(PaymentResult(
        success=True,
        provider_payment_id="test_123"
    ))

    result = provider.create_payment(payment)

    assert result.success
    assert result.provider_payment_id == "test_123"
    assert provider.get_call_count() == 1

def test_payment_failure():
    provider = MockPaymentProvider()

    # Configure mock to fail
    provider.set_should_fail(True, message="Card declined")

    result = provider.create_payment(payment)

    assert not result.success
    assert result.error_message == "Card declined"
```

### Test Helpers

```python
from payments_tr.testing import (
    create_test_payment,
    create_test_buyer_info,
    assert_payment_success,
    assert_payment_failed,
)

def test_payment_flow():
    # Create test objects
    payment = create_test_payment(id=123, amount=10000)
    buyer = create_test_buyer_info(email="test@example.com")

    # Process payment
    result = provider.create_payment(payment, buyer_info=buyer)

    # Assert results
    assert_payment_success(result, expected_status="succeeded")

def test_payment_failure():
    result = provider.create_payment(payment)
    assert_payment_failed(result, expected_error_code="CARD_DECLINED")
```

### Payment Test Case

```python
from payments_tr.testing import PaymentTestCase

class TestPayments(PaymentTestCase):
    def test_payment_creation(self):
        payment = self.create_payment()
        buyer = self.create_buyer_info()

        result = self.provider.create_payment(payment, buyer_info=buyer)

        self.assert_payment_success(result)
```

## CLI Tool

Test providers without Django.

```bash
# Check health
python -m payments_tr.cli check-health --provider stripe

# Test payment creation
python -m payments_tr.cli test-payment --provider stripe --amount 1000

# Validate configuration
python -m payments_tr.cli validate-config

# List available providers
python -m payments_tr.cli list-providers

# Verbose output
python -m payments_tr.cli check-health --verbose
```

## Configuration Validation

Validate settings at startup.

```python
# In your app's AppConfig
from payments_tr.config import check_configuration

class MyAppConfig(AppConfig):
    def ready(self):
        check_configuration()
```

Or manually:

```python
from payments_tr.config import validate_settings

result = validate_settings(raise_on_error=False)

if result.has_errors():
    for error in result.errors:
        print(f"Error: {error}")

if result.has_warnings():
    for warning in result.warnings:
        print(f"Warning: {warning}")
```
