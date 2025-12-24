"""
Management command to replay failed or pending webhooks.

Usage:
    python manage.py replay_webhooks --failed
    python manage.py replay_webhooks --pending
    python manage.py replay_webhooks --provider stripe
    python manage.py replay_webhooks --limit 10
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Replay failed or pending webhooks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--failed",
            action="store_true",
            help="Replay failed webhooks",
        )
        parser.add_argument(
            "--pending",
            action="store_true",
            help="Replay pending webhooks",
        )
        parser.add_argument(
            "--provider",
            type=str,
            help="Replay webhooks for specific provider only",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of webhooks to replay",
        )
        parser.add_argument(
            "--no-backoff",
            action="store_true",
            help="Disable exponential backoff for retries",
        )

    def handle(self, *args, **options):
        failed = options.get("failed", False)
        pending = options.get("pending", False)
        provider = options.get("provider")
        limit = options.get("limit")
        exponential_backoff = not options.get("no_backoff", False)

        # Need webhook model from user's app
        try:
            # Try to import from Django settings
            from django.conf import settings

            payments_settings = getattr(settings, "PAYMENTS_TR", {})
            webhook_model_path = payments_settings.get("WEBHOOK_MODEL")

            if not webhook_model_path:
                raise CommandError(
                    "PAYMENTS_TR['WEBHOOK_MODEL'] not configured in settings. "
                    "Set it to your webhook model path, e.g., 'myapp.WebhookEvent'"
                )

            # Import the model
            app_label, model_name = webhook_model_path.rsplit(".", 1)
            from django.apps import apps

            WebhookEvent = apps.get_model(app_label, model_name)

        except Exception as e:
            raise CommandError(f"Failed to load webhook model: {e}")

        # Import replayer
        from payments_tr.webhooks.replay import WebhookReplayer

        replayer = WebhookReplayer(WebhookEvent)

        # Define webhook processor
        def process_webhook(event):
            from payments_tr.providers.registry import get_payment_provider

            provider = get_payment_provider(event.provider)
            result = provider.handle_webhook(
                payload=event.payload, signature=event.signature
            )
            return result

        # Execute replay
        self.stdout.write("Starting webhook replay...")
        self.stdout.write("-" * 50)

        try:
            if provider:
                stats = replayer.replay_by_provider(
                    provider=provider,
                    processor=process_webhook,
                    max_events=limit,
                    exponential_backoff=exponential_backoff,
                )
            elif failed:
                stats = replayer.replay_failed(
                    processor=process_webhook,
                    max_events=limit,
                    exponential_backoff=exponential_backoff,
                )
            elif pending:
                stats = replayer.replay_pending(
                    processor=process_webhook,
                    max_events=limit,
                    exponential_backoff=exponential_backoff,
                )
            else:
                # Default: replay both failed and pending
                self.stdout.write("Replaying failed webhooks...")
                failed_stats = replayer.replay_failed(
                    processor=process_webhook,
                    max_events=limit,
                    exponential_backoff=exponential_backoff,
                )

                self.stdout.write("\nReplaying pending webhooks...")
                pending_stats = replayer.replay_pending(
                    processor=process_webhook,
                    max_events=limit,
                    exponential_backoff=exponential_backoff,
                )

                # Combine stats
                stats = {
                    "total": failed_stats["total"] + pending_stats["total"],
                    "success": failed_stats["success"] + pending_stats["success"],
                    "failed": failed_stats["failed"] + pending_stats["failed"],
                }

            # Display results
            self.stdout.write("-" * 50)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully processed: {stats['success']}/{stats['total']}"
                )
            )

            if stats["failed"] > 0:
                self.stdout.write(
                    self.style.WARNING(f"⚠ Failed: {stats['failed']}/{stats['total']}")
                )

        except Exception as e:
            raise CommandError(f"Webhook replay failed: {e}")
