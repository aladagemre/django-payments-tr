"""
Webhook replay mechanism for failed or pending webhooks.

This module provides utilities to replay webhooks that failed processing
or are pending retry.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Callable

from django.utils import timezone

logger = logging.getLogger(__name__)


class WebhookReplayer:
    """
    Replay failed or pending webhooks.

    Example:
        >>> from myapp.models import WebhookEvent
        >>> from payments_tr import get_payment_provider
        >>>
        >>> def process_webhook(event):
        ...     provider = get_payment_provider(event.provider)
        ...     result = provider.handle_webhook(
        ...         payload=event.payload,
        ...         signature=event.signature
        ...     )
        ...     return result
        >>>
        >>> replayer = WebhookReplayer(WebhookEvent)
        >>> replayer.replay_failed(process_webhook)
    """

    def __init__(self, webhook_model: type):
        """
        Initialize webhook replayer.

        Args:
            webhook_model: Django model class that extends AbstractWebhookEvent
        """
        self.webhook_model = webhook_model

    def replay_event(
        self,
        event: Any,
        processor: Callable[[Any], Any],
        exponential_backoff: bool = True,
    ) -> bool:
        """
        Replay a single webhook event.

        Args:
            event: WebhookEvent instance
            processor: Callable that processes the event
            exponential_backoff: Use exponential backoff for retry delay

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            event.mark_processing_started()

            # Process the webhook
            result = processor(event)

            if result and getattr(result, "success", False):
                event.mark_success()
                logger.info(f"Successfully replayed webhook: {event.event_id}")
                return True
            else:
                error_msg = getattr(result, "error_message", "Processing failed")
                event.mark_failed(error_msg)
                self._schedule_retry(event, exponential_backoff)
                logger.warning(f"Failed to replay webhook: {event.event_id} - {error_msg}")
                return False

        except Exception as e:
            error_msg = str(e)
            event.mark_failed(error_msg)
            self._schedule_retry(event, exponential_backoff)
            logger.error(f"Error replaying webhook: {event.event_id} - {error_msg}", exc_info=True)
            return False

    def replay_failed(
        self,
        processor: Callable[[Any], Any],
        max_events: int | None = None,
        exponential_backoff: bool = True,
    ) -> dict[str, int]:
        """
        Replay all failed webhooks that can be retried.

        Args:
            processor: Callable that processes each event
            max_events: Maximum number of events to process (None for all)
            exponential_backoff: Use exponential backoff for retry delay

        Returns:
            Dictionary with success/failure counts
        """
        # Get failed events that should be retried
        queryset = self.webhook_model.objects.filter(
            processed=True,
            success=False,
        )

        # Filter by retry criteria
        now = timezone.now()
        queryset = queryset.filter(
            retry_count__lt=models.F("max_retries")
        ).filter(
            models.Q(next_retry_at__lte=now) | models.Q(next_retry_at__isnull=True)
        )

        if max_events:
            queryset = queryset[:max_events]

        stats = {"total": 0, "success": 0, "failed": 0}

        for event in queryset:
            stats["total"] += 1
            if self.replay_event(event, processor, exponential_backoff):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            f"Webhook replay completed: {stats['success']} succeeded, "
            f"{stats['failed']} failed, {stats['total']} total"
        )

        return stats

    def replay_pending(
        self,
        processor: Callable[[Any], Any],
        max_events: int | None = None,
        exponential_backoff: bool = True,
    ) -> dict[str, int]:
        """
        Replay all pending webhooks.

        Args:
            processor: Callable that processes each event
            max_events: Maximum number of events to process (None for all)
            exponential_backoff: Use exponential backoff for retry delay

        Returns:
            Dictionary with success/failure counts
        """
        queryset = self.webhook_model.objects.filter(
            processed=False,
        ).order_by("created_at")

        if max_events:
            queryset = queryset[:max_events]

        stats = {"total": 0, "success": 0, "failed": 0}

        for event in queryset:
            stats["total"] += 1
            if self.replay_event(event, processor, exponential_backoff):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            f"Pending webhook processing completed: {stats['success']} succeeded, "
            f"{stats['failed']} failed, {stats['total']} total"
        )

        return stats

    def replay_by_provider(
        self,
        provider: str,
        processor: Callable[[Any], Any],
        max_events: int | None = None,
        exponential_backoff: bool = True,
    ) -> dict[str, int]:
        """
        Replay webhooks for a specific provider.

        Args:
            provider: Provider name (e.g., 'iyzico', 'stripe')
            processor: Callable that processes each event
            max_events: Maximum number of events to process (None for all)
            exponential_backoff: Use exponential backoff for retry delay

        Returns:
            Dictionary with success/failure counts
        """
        queryset = self.webhook_model.objects.filter(
            provider=provider,
            processed=False,
        ).order_by("created_at")

        if max_events:
            queryset = queryset[:max_events]

        stats = {"total": 0, "success": 0, "failed": 0}

        for event in queryset:
            stats["total"] += 1
            if self.replay_event(event, processor, exponential_backoff):
                stats["success"] += 1
            else:
                stats["failed"] += 1

        logger.info(
            f"Webhook replay for {provider} completed: {stats['success']} succeeded, "
            f"{stats['failed']} failed, {stats['total']} total"
        )

        return stats

    def cleanup_old_events(self, days: int = 30) -> int:
        """
        Delete old webhook events to prevent database bloat.

        Args:
            days: Delete events older than this many days

        Returns:
            Number of events deleted
        """
        cutoff = timezone.now() - timedelta(days=days)
        count, _ = self.webhook_model.objects.filter(
            created_at__lt=cutoff,
            processed=True,
            success=True,
        ).delete()

        logger.info(f"Deleted {count} old webhook events (older than {days} days)")
        return count

    def _schedule_retry(self, event: Any, exponential_backoff: bool) -> None:
        """Schedule event for retry with optional exponential backoff."""
        if not event.should_retry():
            logger.info(
                f"Maximum retries ({event.max_retries}) reached for webhook: {event.event_id}"
            )
            return

        if exponential_backoff:
            # Exponential backoff: 60s, 120s, 240s, 480s, etc.
            delay = 60 * (2 ** event.retry_count)
        else:
            # Fixed delay of 60 seconds
            delay = 60

        event.schedule_retry(delay)
        logger.info(
            f"Scheduled retry #{event.retry_count} for webhook: {event.event_id} "
            f"in {delay} seconds"
        )


# Import models for type checking
try:
    from django.db import models
except ImportError:
    pass
