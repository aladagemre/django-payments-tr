"""Test fixtures for webhook idempotency tests."""

import pytest


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Create the concrete webhook event table for tests."""
    from django.db import connection

    from tests.webhooks.models import ConcreteWebhookEvent

    with django_db_blocker.unblock():
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(ConcreteWebhookEvent)

    yield

    with django_db_blocker.unblock():
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(ConcreteWebhookEvent)
