"""
Provider health check functionality.

This module provides utilities to check if payment providers are
configured correctly and accessible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone as django_timezone

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a provider health check."""

    provider: str
    healthy: bool
    message: str
    details: dict[str, Any]
    checked_at: datetime
    response_time_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "provider": self.provider,
            "healthy": self.healthy,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
            "response_time_ms": self.response_time_ms,
        }


class ProviderHealthChecker:
    """
    Health checker for payment providers.

    Example:
        >>> from payments_tr import get_payment_provider
        >>> provider = get_payment_provider('stripe')
        >>> checker = ProviderHealthChecker()
        >>> result = checker.check_provider(provider)
        >>> print(f"Provider healthy: {result.healthy}")
    """

    def check_provider(
        self,
        provider: Any,
        test_mode: bool = True,
    ) -> HealthCheckResult:
        """
        Check if a provider is healthy and configured correctly.

        Args:
            provider: PaymentProvider instance
            test_mode: Use test/sandbox credentials

        Returns:
            HealthCheckResult with health status
        """
        import time

        provider_name = getattr(provider, "provider_name", "unknown")
        start_time = time.time()
        checked_at = django_timezone.now()

        try:
            # Check basic configuration
            if not provider_name:
                return HealthCheckResult(
                    provider=provider_name,
                    healthy=False,
                    message="Provider name not set",
                    details={},
                    checked_at=checked_at,
                )

            # Provider-specific health checks
            if provider_name == "stripe":
                result = self._check_stripe(provider, test_mode)
            elif provider_name == "iyzico":
                result = self._check_iyzico(provider, test_mode)
            else:
                result = self._check_generic(provider, test_mode)

            # Calculate response time
            response_time = (time.time() - start_time) * 1000
            result.response_time_ms = response_time

            return result

        except Exception as e:
            logger.error(f"Health check failed for {provider_name}: {e}")
            return HealthCheckResult(
                provider=provider_name,
                healthy=False,
                message=f"Health check error: {str(e)}",
                details={"error": str(e)},
                checked_at=checked_at,
            )

    def _check_stripe(self, provider: Any, test_mode: bool) -> HealthCheckResult:
        """Check Stripe provider health."""
        from payments_tr.providers.stripe import StripeAdapter

        if not isinstance(provider, StripeAdapter):
            return HealthCheckResult(
                provider="stripe",
                healthy=False,
                message="Invalid provider type",
                details={},
                checked_at=django_timezone.now(),
            )

        try:
            # Try to get API key
            import stripe

            api_key = stripe.api_key
            if not api_key:
                return HealthCheckResult(
                    provider="stripe",
                    healthy=False,
                    message="Stripe API key not configured",
                    details={},
                    checked_at=django_timezone.now(),
                )

            # Check if using test key in test mode
            is_test_key = api_key.startswith("sk_test_")
            if test_mode and not is_test_key:
                return HealthCheckResult(
                    provider="stripe",
                    healthy=False,
                    message="Not using test API key in test mode",
                    details={"test_mode": test_mode, "is_test_key": is_test_key},
                    checked_at=django_timezone.now(),
                )

            # Try a simple API call (list payment methods)
            try:
                stripe.PaymentMethod.list(limit=1)
            except stripe.error.AuthenticationError:
                return HealthCheckResult(
                    provider="stripe",
                    healthy=False,
                    message="Stripe API authentication failed",
                    details={"test_mode": test_mode},
                    checked_at=django_timezone.now(),
                )

            return HealthCheckResult(
                provider="stripe",
                healthy=True,
                message="Stripe provider healthy",
                details={"test_mode": test_mode, "is_test_key": is_test_key},
                checked_at=django_timezone.now(),
            )

        except ImportError:
            return HealthCheckResult(
                provider="stripe",
                healthy=False,
                message="Stripe package not installed",
                details={},
                checked_at=django_timezone.now(),
            )
        except Exception as e:
            return HealthCheckResult(
                provider="stripe",
                healthy=False,
                message=f"Stripe health check failed: {str(e)}",
                details={"error": str(e)},
                checked_at=django_timezone.now(),
            )

    def _check_iyzico(self, provider: Any, test_mode: bool) -> HealthCheckResult:
        """Check iyzico provider health."""
        from payments_tr.providers.iyzico import IyzicoAdapter

        if not isinstance(provider, IyzicoAdapter):
            return HealthCheckResult(
                provider="iyzico",
                healthy=False,
                message="Invalid provider type",
                details={},
                checked_at=django_timezone.now(),
            )

        try:
            # Check if client is initialized
            if not hasattr(provider, "_client") or provider._client is None:
                return HealthCheckResult(
                    provider="iyzico",
                    healthy=False,
                    message="iyzico client not initialized",
                    details={},
                    checked_at=django_timezone.now(),
                )

            # Basic configuration check
            return HealthCheckResult(
                provider="iyzico",
                healthy=True,
                message="iyzico provider configured",
                details={"test_mode": test_mode},
                checked_at=django_timezone.now(),
            )

        except ImportError:
            return HealthCheckResult(
                provider="iyzico",
                healthy=False,
                message="django-iyzico package not installed",
                details={},
                checked_at=django_timezone.now(),
            )
        except Exception as e:
            return HealthCheckResult(
                provider="iyzico",
                healthy=False,
                message=f"iyzico health check failed: {str(e)}",
                details={"error": str(e)},
                checked_at=django_timezone.now(),
            )

    def _check_generic(self, provider: Any, test_mode: bool) -> HealthCheckResult:
        """Generic health check for unknown providers."""
        provider_name = getattr(provider, "provider_name", "unknown")

        # Just check if provider has required methods
        required_methods = [
            "create_payment",
            "confirm_payment",
            "create_refund",
            "handle_webhook",
            "get_payment_status",
        ]

        missing_methods = [
            method for method in required_methods if not hasattr(provider, method)
        ]

        if missing_methods:
            return HealthCheckResult(
                provider=provider_name,
                healthy=False,
                message=f"Missing required methods: {', '.join(missing_methods)}",
                details={"missing_methods": missing_methods},
                checked_at=django_timezone.now(),
            )

        return HealthCheckResult(
            provider=provider_name,
            healthy=True,
            message="Provider has required methods",
            details={"test_mode": test_mode},
            checked_at=django_timezone.now(),
        )

    def check_all_providers(
        self, test_mode: bool = True
    ) -> dict[str, HealthCheckResult]:
        """
        Check health of all registered providers.

        Args:
            test_mode: Use test/sandbox credentials

        Returns:
            Dictionary mapping provider names to health check results

        Example:
            >>> checker = ProviderHealthChecker()
            >>> results = checker.check_all_providers()
            >>> for name, result in results.items():
            ...     print(f"{name}: {'✓' if result.healthy else '✗'}")
        """
        from payments_tr.providers.registry import ProviderRegistry

        registry = ProviderRegistry()
        results = {}

        for provider_name in registry.list_providers():
            try:
                provider = registry.get(provider_name)
                result = self.check_provider(provider, test_mode)
                results[provider_name] = result
            except Exception as e:
                logger.error(f"Failed to check provider {provider_name}: {e}")
                results[provider_name] = HealthCheckResult(
                    provider=provider_name,
                    healthy=False,
                    message=f"Failed to load provider: {str(e)}",
                    details={"error": str(e)},
                    checked_at=django_timezone.now(),
                )

        return results
