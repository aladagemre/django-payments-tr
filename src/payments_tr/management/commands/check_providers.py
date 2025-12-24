"""
Management command to check payment provider health.

Usage:
    python manage.py check_providers
    python manage.py check_providers --provider stripe
    python manage.py check_providers --verbose
"""

from django.core.management.base import BaseCommand

from payments_tr.health import ProviderHealthChecker


class Command(BaseCommand):
    help = "Check health of payment providers"

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            type=str,
            help="Check specific provider only",
        )
        parser.add_argument(
            "--test-mode",
            action="store_true",
            default=True,
            help="Check test/sandbox configuration (default: True)",
        )
        parser.add_argument(
            "--production",
            action="store_true",
            help="Check production configuration",
        )

    def handle(self, *args, **options):
        provider_name = options.get("provider")
        test_mode = not options.get("production", False)
        verbose = options.get("verbosity", 1) > 1

        checker = ProviderHealthChecker()

        if provider_name:
            # Check specific provider
            self.stdout.write(f"Checking provider: {provider_name}")
            self.stdout.write("-" * 50)

            try:
                from payments_tr.providers.registry import get_payment_provider

                provider = get_payment_provider(provider_name)
                result = checker.check_provider(provider, test_mode)
                self._display_result(result, verbose)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to check provider: {e}")
                )
        else:
            # Check all providers
            self.stdout.write("Checking all providers...")
            self.stdout.write("-" * 50)

            results = checker.check_all_providers(test_mode)

            for name, result in results.items():
                self._display_result(result, verbose)
                self.stdout.write("")

            # Summary
            total = len(results)
            healthy = sum(1 for r in results.values() if r.healthy)
            unhealthy = total - healthy

            self.stdout.write("-" * 50)
            self.stdout.write(f"Total: {total} | Healthy: {healthy} | Unhealthy: {unhealthy}")

            if unhealthy > 0:
                self.stdout.write(
                    self.style.WARNING(f"{unhealthy} provider(s) are not healthy!")
                )

    def _display_result(self, result, verbose):
        """Display health check result."""
        status_symbol = "✓" if result.healthy else "✗"
        status_style = self.style.SUCCESS if result.healthy else self.style.ERROR

        self.stdout.write(
            status_style(f"{status_symbol} {result.provider}: {result.message}")
        )

        if verbose:
            if result.response_time_ms:
                self.stdout.write(f"  Response time: {result.response_time_ms:.0f}ms")
            if result.details:
                self.stdout.write(f"  Details: {result.details}")
