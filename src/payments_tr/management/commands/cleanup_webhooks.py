"""
Management command to clean up old webhook events.

Usage:
    python manage.py cleanup_webhooks --days 30
    python manage.py cleanup_webhooks --days 7 --dry-run
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Clean up old webhook events"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete events older than this many days (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        days = options.get("days", 30)
        dry_run = options.get("dry_run", False)

        # Load webhook model
        try:
            from django.conf import settings

            webhook_model_path = getattr(settings, "PAYMENTS_TR_WEBHOOK_MODEL", None)

            if not webhook_model_path:
                raise CommandError(
                    "PAYMENTS_TR_WEBHOOK_MODEL not configured in settings."
                )

            app_label, model_name = webhook_model_path.rsplit(".", 1)
            from django.apps import apps

            WebhookEvent = apps.get_model(app_label, model_name)

        except Exception as e:
            raise CommandError(f"Failed to load webhook model: {e}")

        # Import replayer for cleanup
        from payments_tr.webhooks.replay import WebhookReplayer

        replayer = WebhookReplayer(WebhookEvent)

        if dry_run:
            # Count events that would be deleted
            from datetime import timedelta

            from django.utils import timezone

            cutoff = timezone.now() - timedelta(days=days)
            count = WebhookEvent.objects.filter(
                created_at__lt=cutoff, processed=True, success=True
            ).count()

            self.stdout.write(
                f"Would delete {count} webhook events older than {days} days"
            )
        else:
            # Actually delete
            count = replayer.cleanup_old_events(days=days)

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Deleted {count} webhook events older than {days} days"
                )
            )
