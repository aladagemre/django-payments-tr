"""Tests for provider health check functionality."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone as django_timezone

from payments_tr.health import HealthCheckResult, ProviderHealthChecker


class TestHealthCheckResult:
    """Test HealthCheckResult dataclass."""

    def test_init(self):
        """Test initialization of HealthCheckResult."""
        checked_at = django_timezone.now()
        result = HealthCheckResult(
            provider="stripe",
            healthy=True,
            message="All good",
            details={"test": "data"},
            checked_at=checked_at,
            response_time_ms=150.5,
        )

        assert result.provider == "stripe"
        assert result.healthy is True
        assert result.message == "All good"
        assert result.details == {"test": "data"}
        assert result.checked_at == checked_at
        assert result.response_time_ms == 150.5

    def test_init_without_response_time(self):
        """Test initialization without response time."""
        checked_at = django_timezone.now()
        result = HealthCheckResult(
            provider="stripe",
            healthy=True,
            message="All good",
            details={},
            checked_at=checked_at,
        )

        assert result.response_time_ms is None

    def test_to_dict(self):
        """Test converting health check result to dictionary."""
        checked_at = django_timezone.now()
        result = HealthCheckResult(
            provider="stripe",
            healthy=True,
            message="Provider healthy",
            details={"test_mode": True},
            checked_at=checked_at,
            response_time_ms=125.0,
        )

        result_dict = result.to_dict()

        assert result_dict["provider"] == "stripe"
        assert result_dict["healthy"] is True
        assert result_dict["message"] == "Provider healthy"
        assert result_dict["details"] == {"test_mode": True}
        assert result_dict["checked_at"] == checked_at.isoformat()
        assert result_dict["response_time_ms"] == 125.0

    def test_to_dict_none_response_time(self):
        """Test to_dict with None response time."""
        checked_at = django_timezone.now()
        result = HealthCheckResult(
            provider="stripe",
            healthy=False,
            message="Error",
            details={},
            checked_at=checked_at,
        )

        result_dict = result.to_dict()
        assert result_dict["response_time_ms"] is None


class TestProviderHealthChecker:
    """Test ProviderHealthChecker class."""

    def test_check_provider_empty_provider_name(self):
        """Test checking provider with empty provider_name."""
        checker = ProviderHealthChecker()
        provider = Mock()
        provider.provider_name = ""  # Empty string

        result = checker.check_provider(provider)

        assert result.provider == ""
        assert result.healthy is False
        assert "Provider name not set" in result.message
        assert result.response_time_ms is None

    def test_check_provider_calculates_response_time(self):
        """Test that check_provider calculates response time."""
        checker = ProviderHealthChecker()
        provider = Mock()
        provider.provider_name = "mock"
        provider.create_payment = Mock()
        provider.confirm_payment = Mock()
        provider.create_refund = Mock()
        provider.handle_webhook = Mock()
        provider.get_payment_status = Mock()

        result = checker.check_provider(provider)

        assert result.response_time_ms is not None
        assert result.response_time_ms >= 0

    def test_check_provider_exception_handling(self, caplog):
        """Test exception handling in check_provider."""
        import logging

        caplog.set_level(logging.ERROR)

        checker = ProviderHealthChecker()
        provider = Mock()
        provider.provider_name = "test"
        # Make provider raise exception when accessed
        provider.create_payment = Mock(side_effect=Exception("Test error"))

        # Patch _check_generic to raise exception
        with patch.object(
            checker, "_check_generic", side_effect=Exception("Health check failed")
        ):
            result = checker.check_provider(provider)

        assert result.healthy is False
        assert "Health check error" in result.message
        assert result.details["error"] == "Health check failed"
        assert "health check failed" in caplog.text.lower()

    def test_check_provider_stripe(self):
        """Test checking Stripe provider."""
        from payments_tr.providers.stripe import StripeAdapter

        checker = ProviderHealthChecker()
        provider = Mock(spec=StripeAdapter)
        provider.provider_name = "stripe"

        with patch.object(checker, "_check_stripe") as mock_check_stripe:
            mock_result = HealthCheckResult(
                provider="stripe",
                healthy=True,
                message="Healthy",
                details={},
                checked_at=django_timezone.now(),
            )
            mock_check_stripe.return_value = mock_result

            result = checker.check_provider(provider)

            mock_check_stripe.assert_called_once_with(provider, True)
            assert result.healthy is True
            assert result.response_time_ms is not None

    def test_check_provider_iyzico(self):
        """Test checking iyzico provider."""
        from payments_tr.providers.iyzico import IyzicoAdapter

        checker = ProviderHealthChecker()
        provider = Mock(spec=IyzicoAdapter)
        provider.provider_name = "iyzico"

        with patch.object(checker, "_check_iyzico") as mock_check_iyzico:
            mock_result = HealthCheckResult(
                provider="iyzico",
                healthy=True,
                message="Healthy",
                details={},
                checked_at=django_timezone.now(),
            )
            mock_check_iyzico.return_value = mock_result

            result = checker.check_provider(provider)

            mock_check_iyzico.assert_called_once_with(provider, True)
            assert result.healthy is True

    def test_check_provider_generic(self):
        """Test checking generic/unknown provider."""
        checker = ProviderHealthChecker()
        provider = Mock()
        provider.provider_name = "unknown_provider"

        with patch.object(checker, "_check_generic") as mock_check_generic:
            mock_result = HealthCheckResult(
                provider="unknown_provider",
                healthy=True,
                message="Healthy",
                details={},
                checked_at=django_timezone.now(),
            )
            mock_check_generic.return_value = mock_result

            result = checker.check_provider(provider)

            mock_check_generic.assert_called_once_with(provider, True)
            assert result.healthy is True

    def test_check_provider_test_mode_false(self):
        """Test checking provider with test_mode=False."""
        checker = ProviderHealthChecker()
        provider = Mock()
        provider.provider_name = "custom"

        with patch.object(checker, "_check_generic") as mock_check:
            mock_check.return_value = HealthCheckResult(
                provider="custom",
                healthy=True,
                message="OK",
                details={},
                checked_at=django_timezone.now(),
            )

            checker.check_provider(provider, test_mode=False)

            mock_check.assert_called_once_with(provider, False)


class TestCheckStripe:
    """Test _check_stripe method."""

    def test_check_stripe_invalid_provider_type(self):
        """Test Stripe check with wrong provider type."""
        checker = ProviderHealthChecker()
        provider = Mock()  # Not a StripeAdapter

        result = checker._check_stripe(provider, test_mode=True)

        assert result.provider == "stripe"
        assert result.healthy is False
        assert "Invalid provider type" in result.message


class TestCheckIyzico:
    """Test _check_iyzico method."""

    def test_check_iyzico_invalid_provider_type(self):
        """Test iyzico check with wrong provider type."""
        checker = ProviderHealthChecker()
        provider = Mock()  # Not an IyzicoAdapter

        result = checker._check_iyzico(provider, test_mode=True)

        assert result.provider == "iyzico"
        assert result.healthy is False
        assert "Invalid provider type" in result.message


class TestCheckGeneric:
    """Test _check_generic method."""

    def test_check_generic_all_methods_present(self):
        """Test generic check with all required methods."""
        checker = ProviderHealthChecker()
        provider = Mock()
        provider.provider_name = "custom"
        provider.create_payment = Mock()
        provider.confirm_payment = Mock()
        provider.create_refund = Mock()
        provider.handle_webhook = Mock()
        provider.get_payment_status = Mock()

        result = checker._check_generic(provider, test_mode=True)

        assert result.provider == "custom"
        assert result.healthy is True
        assert "required methods" in result.message
        assert result.details["test_mode"] is True

    def test_check_generic_missing_single_method(self):
        """Test generic check with one missing method."""
        checker = ProviderHealthChecker()
        # Use spec to control which methods exist
        provider = Mock(spec=["provider_name", "create_payment", "confirm_payment",
                               "create_refund", "handle_webhook"])
        provider.provider_name = "custom"

        result = checker._check_generic(provider, test_mode=True)

        assert result.healthy is False
        assert "Missing required methods" in result.message
        assert "get_payment_status" in result.details["missing_methods"]
        assert len(result.details["missing_methods"]) == 1

    def test_check_generic_missing_multiple_methods(self):
        """Test generic check with multiple missing methods."""
        checker = ProviderHealthChecker()
        # Use spec to control which methods exist
        provider = Mock(spec=["provider_name", "create_payment"])
        provider.provider_name = "custom"

        result = checker._check_generic(provider, test_mode=True)

        assert result.healthy is False
        assert "Missing required methods" in result.message
        assert len(result.details["missing_methods"]) == 4
        assert "confirm_payment" in result.details["missing_methods"]
        assert "create_refund" in result.details["missing_methods"]

    def test_check_generic_no_provider_name(self):
        """Test generic check without provider name."""
        checker = ProviderHealthChecker()
        provider = Mock(spec=["create_payment", "confirm_payment", "create_refund",
                               "handle_webhook", "get_payment_status"])

        result = checker._check_generic(provider, test_mode=False)

        assert result.provider == "unknown"
        assert result.healthy is True
        assert result.details["test_mode"] is False


class TestCheckAllProviders:
    """Test check_all_providers method."""

    def test_check_all_providers_integration(self):
        """Test checking all providers integration."""
        checker = ProviderHealthChecker()

        # Just verify the method doesn't crash and returns a dict
        with patch("payments_tr.providers.registry.ProviderRegistry") as MockRegistry:
            mock_registry = Mock()
            mock_registry.list_providers.return_value = []
            MockRegistry.return_value = mock_registry

            results = checker.check_all_providers()

        assert isinstance(results, dict)

    def test_check_all_providers_with_exception(self):
        """Test check_all_providers handles provider loading exceptions."""
        from payments_tr.health import HealthCheckResult

        checker = ProviderHealthChecker()

        # Mock ProviderRegistry class from where it's imported
        with patch("payments_tr.providers.registry.ProviderRegistry") as MockRegistry:
            mock_registry = Mock()
            mock_registry.list_providers.return_value = ["failing_provider"]
            mock_registry.get.side_effect = Exception("Provider load failed")
            MockRegistry.return_value = mock_registry

            results = checker.check_all_providers()

        # Should have result for the failing provider
        assert "failing_provider" in results
        assert results["failing_provider"].healthy is False
        assert "Failed to load provider" in results["failing_provider"].message
        assert "Provider load failed" in results["failing_provider"].details["error"]
