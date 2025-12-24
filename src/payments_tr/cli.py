#!/usr/bin/env python
"""
CLI tool for testing payment providers.

This tool allows testing provider configuration and operations
without needing a full Django application.

Usage:
    python -m payments_tr.cli check-health --provider stripe
    python -m payments_tr.cli test-payment --provider stripe --amount 1000
    python -m payments_tr.cli validate-config
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def check_health(args: Any) -> int:
    """Check provider health."""
    try:
        # Setup Django if needed
        _setup_django()

        from payments_tr.health import ProviderHealthChecker
        from payments_tr.providers.registry import get_payment_provider

        provider_name = args.provider or "default"
        print(f"Checking health for provider: {provider_name}")
        print("-" * 50)

        provider = get_payment_provider(provider_name if provider_name != "default" else None)
        checker = ProviderHealthChecker()
        result = checker.check_provider(provider, test_mode=not args.production)

        # Display result
        status = "✓ HEALTHY" if result.healthy else "✗ UNHEALTHY"
        print(f"Status: {status}")
        print(f"Message: {result.message}")

        if result.response_time_ms:
            print(f"Response time: {result.response_time_ms:.0f}ms")

        if result.details:
            print(f"Details: {json.dumps(result.details, indent=2)}")

        return 0 if result.healthy else 1

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def test_payment(args: Any) -> int:
    """Test payment creation."""
    try:
        _setup_django()

        from payments_tr.providers.registry import get_payment_provider
        from payments_tr.testing.utils import create_test_payment, create_test_buyer_info

        provider_name = args.provider or "default"
        amount = args.amount or 1000

        print(f"Testing payment with provider: {provider_name}")
        print(f"Amount: {amount/100:.2f} TRY")
        print("-" * 50)

        # Create test payment
        payment = create_test_payment(id="test_cli", amount=amount, currency="TRY")
        buyer_info = create_test_buyer_info(email="test@example.com")

        # Get provider
        provider = get_payment_provider(provider_name if provider_name != "default" else None)

        # Create payment
        print("Creating payment...")
        result = provider.create_payment(
            payment,
            callback_url="https://example.com/callback",
            buyer_info=buyer_info,
        )

        # Display result
        print(f"Success: {result.success}")
        print(f"Status: {result.status}")

        if result.success:
            print(f"Provider Payment ID: {result.provider_payment_id}")
            if result.checkout_url:
                print(f"Checkout URL: {result.checkout_url}")
            if result.client_secret:
                print(f"Client Secret: {result.client_secret}")
        else:
            print(f"Error: {result.error_message}")
            print(f"Error Code: {result.error_code}")

        if args.verbose and result.raw_response:
            print(f"\nRaw Response:\n{json.dumps(result.raw_response, indent=2)}")

        return 0 if result.success else 1

    except Exception as e:
        logger.error(f"Payment test failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def validate_config(args: Any) -> int:
    """Validate configuration."""
    try:
        _setup_django()

        from payments_tr.config import validate_settings

        print("Validating PAYMENTS_TR configuration...")
        print("-" * 50)

        result = validate_settings(raise_on_error=False)

        if result.has_errors():
            print("ERRORS:")
            for error in result.errors:
                print(f"  ✗ {error}")

        if result.has_warnings():
            print("\nWARNINGS:")
            for warning in result.warnings:
                print(f"  ⚠ {warning}")

        if result.valid and not result.has_warnings():
            print("✓ Configuration is valid")
            return 0
        elif result.valid:
            print("\n✓ Configuration is valid (with warnings)")
            return 0
        else:
            print("\n✗ Configuration has errors")
            return 1

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def list_providers(args: Any) -> int:
    """List available providers."""
    try:
        _setup_django()

        from payments_tr.providers.registry import ProviderRegistry

        print("Available payment providers:")
        print("-" * 50)

        registry = ProviderRegistry()
        providers = registry.list_providers()

        if not providers:
            print("No providers registered")
            return 0

        for provider_name in providers:
            try:
                provider = registry.get(provider_name)
                features = []
                if provider.supports_checkout_form():
                    features.append("checkout")
                if provider.supports_redirect():
                    features.append("redirect")
                if provider.supports_installments():
                    features.append("installments")
                if provider.supports_subscriptions():
                    features.append("subscriptions")

                feature_str = ", ".join(features) if features else "none"
                print(f"  • {provider_name}: {feature_str}")
            except Exception as e:
                print(f"  • {provider_name}: [error: {e}]")

        return 0

    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def _setup_django() -> None:
    """Setup Django if needed."""
    try:
        import django
        from django.conf import settings

        if not settings.configured:
            # Minimal Django configuration
            settings.configure(
                DEBUG=True,
                DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.sqlite3",
                        "NAME": ":memory:",
                    }
                },
                INSTALLED_APPS=[
                    "django.contrib.contenttypes",
                    "django.contrib.auth",
                    "payments_tr",
                ],
                SECRET_KEY="test-secret-key",
                USE_TZ=True,
            )
            django.setup()
    except ImportError:
        logger.warning("Django not available, some features may not work")


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="CLI tool for testing payment providers",
        prog="payments-tr",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # check-health command
    health_parser = subparsers.add_parser(
        "check-health",
        help="Check provider health",
    )
    health_parser.add_argument(
        "--provider",
        type=str,
        help="Provider name (e.g., stripe, iyzico)",
    )
    health_parser.add_argument(
        "--production",
        action="store_true",
        help="Check production configuration",
    )

    # test-payment command
    payment_parser = subparsers.add_parser(
        "test-payment",
        help="Test payment creation",
    )
    payment_parser.add_argument(
        "--provider",
        type=str,
        help="Provider name (e.g., stripe, iyzico)",
    )
    payment_parser.add_argument(
        "--amount",
        type=int,
        default=1000,
        help="Payment amount in smallest unit (default: 1000 = 10.00 TRY)",
    )

    # validate-config command
    subparsers.add_parser(
        "validate-config",
        help="Validate PAYMENTS_TR configuration",
    )

    # list-providers command
    subparsers.add_parser(
        "list-providers",
        help="List available providers",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to appropriate handler
    handlers = {
        "check-health": check_health,
        "test-payment": test_payment,
        "validate-config": validate_config,
        "list-providers": list_providers,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        logger.error(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
