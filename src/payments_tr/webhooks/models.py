"""
Webhook event logging models.

These are abstract models that applications can extend to store
webhook events for debugging, replay, and audit purposes.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class AbstractWebhookEvent(models.Model):
    """
    Abstract model for storing webhook events.

    Applications should extend this model to create their own webhook event storage.

    Example:
        >>> class WebhookEvent(AbstractWebhookEvent):
        ...     class Meta:
        ...         db_table = 'webhook_events'
        ...         indexes = [
        ...             models.Index(fields=['provider', 'event_type']),
        ...             models.Index(fields=['created_at']),
        ...         ]
    """

    # Event identification
    provider = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Payment provider name (e.g., 'iyzico', 'stripe')",
    )
    event_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Type of event (e.g., 'payment.succeeded', 'refund.created')",
    )
    event_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique event ID from provider (for idempotency)",
    )

    # Webhook data
    payload = models.JSONField(
        help_text="Full webhook payload as JSON"
    )
    headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="HTTP headers from webhook request",
    )
    signature = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Webhook signature for verification",
    )

    # Processing status
    processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this webhook has been processed",
    )
    processing_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing started",
    )
    processing_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing completed",
    )
    success = models.BooleanField(
        default=False,
        help_text="Whether processing was successful",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error message if processing failed",
    )

    # Retry tracking
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times processing has been retried",
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum number of retries allowed",
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to retry processing",
    )

    # Associated payment
    payment_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Associated payment ID from your system",
    )
    provider_payment_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Provider's payment ID",
    )

    # Metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of webhook sender",
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="User agent of webhook sender",
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When webhook was received",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When record was last updated",
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider} - {self.event_type} ({self.event_id})"

    def mark_processing_started(self) -> None:
        """Mark webhook as processing started."""
        self.processing_started_at = timezone.now()
        self.save(update_fields=["processing_started_at"])

    def mark_success(self) -> None:
        """Mark webhook as successfully processed."""
        self.processed = True
        self.success = True
        self.processing_completed_at = timezone.now()
        self.save(
            update_fields=["processed", "success", "processing_completed_at"]
        )

    def mark_failed(self, error_message: str) -> None:
        """Mark webhook processing as failed."""
        self.processed = True
        self.success = False
        self.error_message = error_message
        self.processing_completed_at = timezone.now()
        self.retry_count += 1
        self.save(
            update_fields=[
                "processed",
                "success",
                "error_message",
                "processing_completed_at",
                "retry_count",
            ]
        )

    def should_retry(self) -> bool:
        """Check if webhook should be retried."""
        if self.retry_count >= self.max_retries:
            return False
        if self.success:
            return False
        if self.next_retry_at and self.next_retry_at > timezone.now():
            return False
        return True

    def schedule_retry(self, delay_seconds: int = 60) -> None:
        """Schedule webhook for retry."""
        from datetime import timedelta

        self.next_retry_at = timezone.now() + timedelta(seconds=delay_seconds)
        self.processed = False
        self.save(update_fields=["next_retry_at", "processed"])

    @property
    def is_pending(self) -> bool:
        """Check if webhook is pending processing."""
        return not self.processed

    @property
    def is_processing(self) -> bool:
        """Check if webhook is currently being processed."""
        return (
            self.processing_started_at is not None
            and self.processing_completed_at is None
        )

    @property
    def is_failed(self) -> bool:
        """Check if webhook processing failed."""
        return self.processed and not self.success

    @property
    def can_retry(self) -> bool:
        """Check if webhook can be retried."""
        return self.is_failed and self.retry_count < self.max_retries
