"""Tests for webhook replay protection."""

from __future__ import annotations

import pytest

from payments_tr.providers.base import WebhookResult
from payments_tr.webhooks import build_idempotency_key, record_webhook_or_skip
from tests.webhooks.models import ConcreteWebhookEvent


class TestBuildIdempotencyKey:
    def test_builds_iyzico_key(self):
        result = WebhookResult(
            success=True,
            event_type="payment.success",
            provider_payment_id="pay_abc123",
        )
        assert build_idempotency_key("iyzico", result) == "iyzico:pay_abc123:payment.success"

    def test_builds_stripe_key(self):
        result = WebhookResult(
            success=True,
            event_type="payment_intent.succeeded",
            provider_payment_id="evt_xyz",
        )
        assert (
            build_idempotency_key("stripe", result)
            == "stripe:evt_xyz:payment_intent.succeeded"
        )

    def test_provider_prefix_prevents_cross_provider_collision(self):
        # Different providers may emit the same internal id; the prefix
        # keeps them distinct in the dedup table.
        a = build_idempotency_key("iyzico", WebhookResult(success=True, provider_payment_id="X"))
        b = build_idempotency_key("stripe", WebhookResult(success=True, provider_payment_id="X"))
        assert a != b

    def test_missing_provider_id_raises(self):
        result = WebhookResult(success=True, event_type="payment.success")
        with pytest.raises(ValueError, match="provider_payment_id"):
            build_idempotency_key("iyzico", result)


@pytest.mark.django_db
class TestRecordWebhookOrSkip:
    def test_first_delivery_creates_row(self):
        event, created = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_1:payment.success",
            event_type="payment.success",
            payload={"foo": "bar"},
        )
        assert created is True
        assert event.event_id == "iyzico:pay_1:payment.success"
        assert event.payload == {"foo": "bar"}

    def test_second_delivery_returns_existing_row(self):
        first, created_first = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_2:payment.success",
            payload={"original": True},
        )
        assert created_first is True

        second, created_second = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_2:payment.success",
            # Even with a different payload, we must NOT overwrite —
            # the key is the source of truth.
            payload={"replayed": True},
        )
        assert created_second is False
        assert second.pk == first.pk
        assert second.payload == {"original": True}

    def test_different_event_ids_create_distinct_rows(self):
        _, c1 = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_3:payment.success",
        )
        _, c2 = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_4:payment.success",
        )
        assert c1 is True
        assert c2 is True
        assert ConcreteWebhookEvent.objects.count() == 2

    def test_same_internal_id_different_event_type_creates_distinct_rows(self):
        # Iyzico emits multiple event types per paymentId (auth + capture
        # + cancel); each one is a distinct event that must be processed.
        _, c1 = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_5:payment.auth",
        )
        _, c2 = record_webhook_or_skip(
            ConcreteWebhookEvent,
            provider="iyzico",
            event_id="iyzico:pay_5:payment.capture",
        )
        assert c1 is True
        assert c2 is True
