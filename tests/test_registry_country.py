"""Tests for per-country payment provider selection."""

import pytest

from payments_tr.providers import (
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
    get_available_providers,
    get_payment_provider,
    get_provider_for_country,
    get_provider_name,
    get_supported_countries,
    is_iyzico_enabled,
    is_stripe_enabled,
    registry,
)


class MockStripeProvider(PaymentProvider):
    """Mock Stripe provider for testing."""

    provider_name = "stripe"

    def create_payment(self, payment, **kwargs):
        return PaymentResult(success=True)

    def confirm_payment(self, provider_payment_id):
        return PaymentResult(success=True)

    def create_refund(self, payment, amount=None, reason="", **kwargs):
        return RefundResult(success=True)

    def handle_webhook(self, payload, signature=None, **kwargs):
        return WebhookResult(success=True)

    def get_payment_status(self, provider_payment_id):
        return "succeeded"


class MockIyzicoProvider(PaymentProvider):
    """Mock iyzico provider for testing."""

    provider_name = "iyzico"

    def create_payment(self, payment, **kwargs):
        return PaymentResult(success=True)

    def confirm_payment(self, provider_payment_id):
        return PaymentResult(success=True)

    def create_refund(self, payment, amount=None, reason="", **kwargs):
        return RefundResult(success=True)

    def handle_webhook(self, payload, signature=None, **kwargs):
        return WebhookResult(success=True)

    def get_payment_status(self, provider_payment_id):
        return "succeeded"


@pytest.fixture
def setup_providers():
    """Set up mock providers before each test."""
    registry.clear()
    registry.register("stripe", MockStripeProvider)
    registry.register("iyzico", MockIyzicoProvider)
    yield
    registry.clear()


class TestPerCountryProviderSelection:
    """Tests for per-country payment provider selection."""

    def test_get_provider_for_turkey_returns_iyzico(self, settings, setup_providers):
        """Test that Turkey (TR) gets iyzico provider."""
        settings.PAYMENT_PROVIDER = "stripe"  # Default
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico"}

        provider = get_payment_provider(country_code="TR")
        assert isinstance(provider, MockIyzicoProvider)
        assert provider.provider_name == "iyzico"

    def test_get_provider_for_us_returns_stripe(self, settings, setup_providers):
        """Test that USA (US) gets Stripe provider."""
        settings.PAYMENT_PROVIDER = "iyzico"  # Default
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico", "US": "stripe"}

        provider = get_payment_provider(country_code="US")
        assert isinstance(provider, MockStripeProvider)
        assert provider.provider_name == "stripe"

    def test_unknown_country_uses_default_provider(self, settings, setup_providers):
        """Test that unknown country codes fall back to default provider."""
        settings.PAYMENT_PROVIDER = "stripe"
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico"}

        # Unknown country should use default
        provider = get_payment_provider(country_code="XX")
        assert isinstance(provider, MockStripeProvider)

    def test_country_code_case_insensitive(self, settings, setup_providers):
        """Test that country codes are case insensitive."""
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico"}

        # Lowercase should work
        provider = get_payment_provider(country_code="tr")
        assert isinstance(provider, MockIyzicoProvider)

    def test_explicit_provider_name_overrides_country(self, settings, setup_providers):
        """Test that explicit provider_name takes precedence over country_code."""
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico"}

        # Even with country_code=TR, explicit name should win
        provider = get_payment_provider(name="stripe", country_code="TR")
        assert isinstance(provider, MockStripeProvider)

    def test_get_provider_for_country_helper(self, settings, setup_providers):
        """Test get_provider_for_country helper function."""
        settings.PAYMENT_PROVIDER = "stripe"
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico", "DE": "stripe"}

        assert get_provider_for_country("TR") == "iyzico"
        assert get_provider_for_country("DE") == "stripe"
        assert get_provider_for_country("XX") == "stripe"  # Default

    def test_get_provider_name_with_country(self, settings, setup_providers):
        """Test get_provider_name with country_code parameter."""
        settings.PAYMENT_PROVIDER = "stripe"
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico"}

        assert get_provider_name() == "stripe"
        assert get_provider_name(country_code="TR") == "iyzico"
        assert get_provider_name(country_code="US") == "stripe"  # Default

    def test_is_iyzico_enabled_with_country(self, settings, setup_providers):
        """Test is_iyzico_enabled with country_code parameter."""
        settings.PAYMENT_PROVIDER = "stripe"
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "iyzico"}

        assert is_iyzico_enabled() is False
        assert is_iyzico_enabled(country_code="TR") is True
        assert is_iyzico_enabled(country_code="US") is False

    def test_is_stripe_enabled_with_country(self, settings, setup_providers):
        """Test is_stripe_enabled with country_code parameter."""
        settings.PAYMENT_PROVIDER = "iyzico"
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"US": "stripe"}

        assert is_stripe_enabled() is False
        assert is_stripe_enabled(country_code="US") is True
        assert is_stripe_enabled(country_code="TR") is False

    def test_get_supported_countries(self, settings, setup_providers):
        """Test get_supported_countries helper function."""
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {
            "TR": "iyzico",
            "US": "stripe",
            "GB": "stripe",
        }

        countries = get_supported_countries()
        assert countries == {"TR": "iyzico", "US": "stripe", "GB": "stripe"}

    def test_get_supported_countries_empty(self, settings, setup_providers):
        """Test get_supported_countries when no countries configured."""
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {}
        assert get_supported_countries() == {}

    def test_get_available_providers(self, setup_providers):
        """Test get_available_providers lists all registered providers."""
        providers = get_available_providers()
        assert "stripe" in providers
        assert "iyzico" in providers

    def test_no_country_setting_uses_default(self, settings, setup_providers):
        """Test that missing PAYMENT_PROVIDERS_BY_COUNTRY uses default."""
        settings.PAYMENT_PROVIDER = "stripe"
        # Remove the setting if it exists
        if hasattr(settings, "PAYMENT_PROVIDERS_BY_COUNTRY"):
            delattr(settings, "PAYMENT_PROVIDERS_BY_COUNTRY")

        provider = get_payment_provider(country_code="TR")
        assert isinstance(provider, MockStripeProvider)  # Falls back to default

    def test_provider_name_case_insensitive_in_settings(self, settings, setup_providers):
        """Test that provider names in settings are case insensitive."""
        settings.PAYMENT_PROVIDERS_BY_COUNTRY = {"TR": "IYZICO"}  # Uppercase

        provider = get_payment_provider(country_code="TR")
        assert isinstance(provider, MockIyzicoProvider)
