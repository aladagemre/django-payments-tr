"""Concrete webhook event model for tests."""

from payments_tr.webhooks.models import AbstractWebhookEvent


class ConcreteWebhookEvent(AbstractWebhookEvent):
    """Concrete webhook event for replay-protection tests."""

    class Meta(AbstractWebhookEvent.Meta):
        db_table = "test_webhook_events"
        app_label = "tests"
