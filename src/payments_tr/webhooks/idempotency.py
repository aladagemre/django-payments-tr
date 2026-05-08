"""
Webhook replay-protection helpers.

Payment providers (Iyzico, Stripe) deliver webhooks at-least-once: the
same event may arrive multiple times after timeouts, retries, or
deliberate replay attacks. Without dedup, downstream signal handlers
will mark an order paid twice, refund twice, or fire a fulfillment
twice — exactly the kind of incident PCI-DSS scope exists to prevent.

The :class:`AbstractWebhookEvent` model already declares ``event_id``
as ``unique=True``. The helpers below let callers atomically record a
new event and reject duplicates, regardless of which concrete model
they extend it with.

Recommended pattern in a Django webhook view::

    from payments_tr.webhooks import build_idempotency_key, record_webhook_or_skip
    from myapp.models import IyzicoWebhookEvent

    @csrf_exempt
    def iyzico_webhook(request):
        provider = IyzicoProvider()
        result = provider.handle_webhook(request.body, ...)
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
            # Already seen — return 200 so provider stops retrying.
            return JsonResponse({"status": "duplicate"}, status=200)

        # First time — fan out to business logic.
        my_signal.send(...)
        event.mark_success()
        return JsonResponse({"status": "ok"}, status=200)
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


def build_idempotency_key(provider: str, result: Any) -> str:
    """
    Construct a canonical event-id string for a webhook result.

    Different providers identify events differently:

    - **Iyzico** delivers a ``paymentId`` per event. The same paymentId
      can appear with different ``iyziEventType`` values (auth vs.
      capture vs. cancel), so the key must include both.
    - **Stripe** ships a globally-unique ``id`` on every event object;
      that id alone is the canonical key.

    Args:
        provider: Provider name (``"iyzico"``, ``"stripe"``, etc.) Used
            as a prefix so different providers can never collide on
            ``event_id`` even if their internal IDs overlap.
        result: A :class:`payments_tr.providers.base.WebhookResult` or
            equivalent — anything with ``provider_payment_id`` and
            ``event_type`` attributes is acceptable.

    Returns:
        A string suitable for the ``event_id`` column of
        :class:`AbstractWebhookEvent`.

    Raises:
        ValueError: If neither ``provider_payment_id`` nor a
            provider-specific id is available — without that, dedup is
            impossible and we must not silently accept the event.
    """
    provider_payment_id = getattr(result, "provider_payment_id", None) or ""
    event_type = getattr(result, "event_type", None) or ""

    if not provider_payment_id:
        raise ValueError(
            "Cannot build idempotency key: WebhookResult lacks "
            "provider_payment_id. Without it, the event cannot be "
            "deduplicated and must be rejected."
        )

    return f"{provider}:{provider_payment_id}:{event_type}"


def record_webhook_or_skip(
    model: Any,
    *,
    provider: str,
    event_id: str,
    event_type: str = "",
    payload: dict[str, Any] | None = None,
    signature: str = "",
    headers: dict[str, Any] | None = None,
    payment_id: str = "",
    provider_payment_id: str = "",
    ip_address: str | None = None,
) -> tuple[Any, bool]:
    """
    Atomically record a webhook event, returning ``(event, created)``.

    On the **first** delivery for a given ``event_id``, returns the
    newly-created row with ``created=True``. On any subsequent delivery,
    returns the existing row with ``created=False`` — the caller MUST
    NOT re-fire downstream effects in that case.

    The ``unique=True`` constraint on ``event_id`` (declared in
    :class:`AbstractWebhookEvent`) plus the ``transaction.atomic`` /
    ``IntegrityError`` fallback closes the get-or-create race window
    that would otherwise allow concurrent duplicate processing.

    Args:
        model: Concrete subclass of :class:`AbstractWebhookEvent`.
        provider: Provider name (``"iyzico"``, ``"stripe"``, ...).
        event_id: Output of :func:`build_idempotency_key`.
        event_type: Provider-emitted event type, e.g.
            ``"payment.success"``.
        payload: Webhook body (will be persisted as JSON). Should be
            sanitized of card data and PII before being passed in.
        signature: Optional signature header for audit trail.
        headers: Optional HTTP headers (audit trail). Keep minimal — do
            not store ``Authorization`` etc.
        payment_id: Internal payment ID, if known.
        provider_payment_id: Provider's payment ID, if known.
        ip_address: IP address of the webhook sender.

    Returns:
        Tuple of ``(event_row, created_bool)``.
    """
    payload = payload if payload is not None else {}
    headers = headers if headers is not None else {}

    defaults = {
        "provider": provider,
        "event_type": event_type,
        "payload": payload,
        "signature": signature,
        "headers": headers,
        "payment_id": payment_id,
        "provider_payment_id": provider_payment_id,
        "ip_address": ip_address,
    }

    try:
        with transaction.atomic():
            event, created = model.objects.get_or_create(
                event_id=event_id,
                defaults=defaults,
            )
    except IntegrityError:
        # Race: another worker inserted between get and create.
        # Fall back to the existing row.
        logger.info(
            "Webhook idempotency race resolved by IntegrityError fallback "
            "for event_id=%s",
            event_id,
        )
        event = model.objects.get(event_id=event_id)
        created = False

    if not created:
        logger.info(
            "Duplicate webhook ignored: provider=%s event_id=%s "
            "(first seen at %s)",
            provider,
            event_id,
            getattr(event, "created_at", "?"),
        )

    return event, created
