"""
Payment provider registry and factory.

This module provides a registry for payment providers and factory functions
to get the configured provider instance.

Supports per-country provider selection for multi-country deployments:

    # settings.py
    PAYMENT_PROVIDERS_BY_COUNTRY = {
        "TR": "iyzico",   # Turkey uses iyzico
        "US": "stripe",   # USA uses Stripe
        "BR": "pagarme",  # Brazil uses local provider
    }
    PAYMENT_PROVIDER = "stripe"  # Default fallback

    # Usage
    provider = get_payment_provider(country_code="TR")  # Gets iyzico
    provider = get_payment_provider(country_code="US")  # Gets Stripe
    provider = get_payment_provider(country_code="XX")  # Falls back to default
"""

from __future__ import annotations

import logging
from functools import cache, lru_cache
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from payments_tr.providers.base import PaymentProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for payment provider classes.

    This allows dynamic registration of payment providers and
    retrieval based on configuration.

    Example:
        >>> from payments_tr.providers import registry
        >>> registry.register("custom", CustomProvider)
        >>> provider = registry.get("custom")
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[PaymentProvider]] = {}

    def register(self, name: str, provider_class: type[PaymentProvider]) -> None:
        """
        Register a payment provider.

        Args:
            name: Provider identifier (e.g., "iyzico", "stripe")
            provider_class: Provider class (not instance)
        """
        name = name.lower()
        self._providers[name] = provider_class
        logger.debug(f"Registered payment provider: {name}")

    def unregister(self, name: str) -> None:
        """
        Unregister a payment provider.

        Args:
            name: Provider identifier to remove
        """
        name = name.lower()
        if name in self._providers:
            del self._providers[name]
            logger.debug(f"Unregistered payment provider: {name}")

    def get(
        self,
        name: str | None = None,
        country_code: str | None = None,
    ) -> PaymentProvider:
        """
        Get a provider instance.

        Provider selection priority:
        1. Explicit `name` parameter (highest priority)
        2. Country-specific provider from PAYMENT_PROVIDERS_BY_COUNTRY
        3. Default provider from PAYMENT_PROVIDER setting
        4. "stripe" as ultimate fallback

        Args:
            name: Explicit provider name (overrides country selection)
            country_code: ISO 3166-1 alpha-2 country code (e.g., "TR", "US")

        Returns:
            PaymentProvider instance

        Raises:
            ValueError: If provider not found

        Examples:
            >>> registry.get()                      # Default provider
            >>> registry.get("iyzico")              # Explicit provider
            >>> registry.get(country_code="TR")     # Country-based selection
        """
        # Priority 1: Explicit provider name
        if name:
            resolved_name = name.lower()
        # Priority 2: Country-specific provider
        elif country_code:
            resolved_name = self._get_provider_for_country(country_code)
        # Priority 3: Default provider from settings
        else:
            resolved_name = self._get_default_name()

        if resolved_name not in self._providers:
            available = ", ".join(self._providers.keys()) or "none"
            raise ValueError(
                f"Unknown payment provider: {resolved_name}. "
                f"Available providers: {available}. "
                f"Make sure the provider package is installed "
                f"(e.g., pip install django-payments-tr[{resolved_name}])"
            )

        logger.debug(
            f"Using payment provider: {resolved_name}"
            + (f" (country: {country_code})" if country_code else "")
        )
        return self._providers[resolved_name]()

    def _get_provider_for_country(self, country_code: str) -> str:
        """
        Get the provider name for a specific country.

        Args:
            country_code: ISO 3166-1 alpha-2 country code

        Returns:
            Provider name string
        """
        providers_by_country = getattr(settings, "PAYMENT_PROVIDERS_BY_COUNTRY", {})
        country_upper = country_code.upper()

        if country_upper in providers_by_country:
            return providers_by_country[country_upper].lower()

        return self._get_default_name()

    def get_class(self, name: str) -> type[PaymentProvider]:
        """
        Get a provider class by name (without instantiating).

        Args:
            name: Provider name

        Returns:
            PaymentProvider class

        Raises:
            ValueError: If provider not found
        """
        name = name.lower()
        if name not in self._providers:
            available = ", ".join(self._providers.keys()) or "none"
            raise ValueError(f"Unknown payment provider: {name}. Available: {available}")
        return self._providers[name]

    def list_providers(self) -> list[str]:
        """
        List all registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def is_registered(self, name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider is registered
        """
        return name.lower() in self._providers

    def _get_default_name(self) -> str:
        """Get the default provider name from settings."""
        return getattr(settings, "PAYMENT_PROVIDER", "stripe")

    def clear(self) -> None:
        """Clear all registered providers (useful for testing)."""
        self._providers.clear()


# Global registry instance
registry = ProviderRegistry()


def get_payment_provider(
    name: str | None = None,
    country_code: str | None = None,
) -> PaymentProvider:
    """
    Get a payment provider instance.

    Provider selection priority:
    1. Explicit `name` parameter (highest priority)
    2. Country-specific provider from PAYMENT_PROVIDERS_BY_COUNTRY
    3. Default provider from PAYMENT_PROVIDER setting
    4. "stripe" as ultimate fallback

    Args:
        name: Explicit provider name (overrides country selection)
        country_code: ISO 3166-1 alpha-2 country code (e.g., "TR", "US", "GB")

    Returns:
        PaymentProvider instance

    Raises:
        ValueError: If the provider name is not recognized

    Examples:
        >>> # Use default/global provider
        >>> provider = get_payment_provider()

        >>> # Use country-specific provider
        >>> provider = get_payment_provider(country_code="TR")  # Gets iyzico for Turkey

        >>> # Explicitly specify provider (ignores country)
        >>> provider = get_payment_provider(name="stripe")

        >>> # Create payment
        >>> result = provider.create_payment(payment, callback_url=url)
    """
    return registry.get(name, country_code=country_code)


@cache
def get_default_provider() -> PaymentProvider:
    """
    Get the default payment provider (cached).

    This is useful for views that need a consistent provider instance.
    The result is cached for the lifetime of the process.

    Note: For country-specific providers, use get_payment_provider(country_code=...)
    instead, as this returns only the global default.

    Returns:
        PaymentProvider instance
    """
    return get_payment_provider()


@lru_cache(maxsize=32)
def get_provider_for_country_cached(country_code: str) -> PaymentProvider:
    """
    Get a country-specific payment provider instance (cached).

    Caches up to 32 country-provider combinations to avoid
    repeated instantiation of provider objects.

    Args:
        country_code: ISO 3166-1 alpha-2 country code

    Returns:
        PaymentProvider instance for the specified country
    """
    return get_payment_provider(country_code=country_code)


def get_provider_name(country_code: str | None = None) -> str:
    """
    Get the name of the payment provider that would be used.

    Args:
        country_code: Optional country code to check country-specific provider

    Returns:
        Provider name string (e.g., "stripe" or "iyzico")

    Examples:
        >>> get_provider_name()           # "stripe" (default)
        >>> get_provider_name("TR")       # "iyzico" (if configured)
    """
    if country_code:
        return get_provider_for_country(country_code)
    return getattr(settings, "PAYMENT_PROVIDER", "stripe").lower()


def get_provider_for_country(country_code: str) -> str:
    """
    Get the provider name for a specific country.

    Looks up the country in PAYMENT_PROVIDERS_BY_COUNTRY setting,
    falls back to the default provider if country not configured.

    Args:
        country_code: ISO 3166-1 alpha-2 country code (e.g., "TR", "US")

    Returns:
        Provider name string (e.g., "stripe" or "iyzico")

    Examples:
        >>> get_provider_for_country("TR")  # "iyzico"
        >>> get_provider_for_country("US")  # "stripe"
        >>> get_provider_for_country("XX")  # "stripe" (default fallback)
    """
    providers_by_country = getattr(settings, "PAYMENT_PROVIDERS_BY_COUNTRY", {})
    country_upper = country_code.upper()

    if country_upper in providers_by_country:
        return providers_by_country[country_upper].lower()

    return getattr(settings, "PAYMENT_PROVIDER", "stripe").lower()


def get_supported_countries() -> dict[str, str]:
    """
    Get all configured country-provider mappings.

    Returns:
        Dictionary mapping country codes to provider names

    Example:
        >>> get_supported_countries()
        {"TR": "iyzico", "US": "stripe", "GB": "stripe"}
    """
    return dict(getattr(settings, "PAYMENT_PROVIDERS_BY_COUNTRY", {}))


def get_available_providers() -> list[str]:
    """
    Get list of all registered provider names.

    Returns:
        List of provider name strings

    Example:
        >>> get_available_providers()
        ["stripe", "iyzico"]
    """
    return registry.list_providers()


def register_provider(name: str, provider_class: type[PaymentProvider]) -> None:
    """
    Register a custom payment provider.

    This is a convenience function for registering providers without
    directly accessing the registry.

    Args:
        name: Provider identifier
        provider_class: Provider class implementing PaymentProvider

    Example:
        >>> from payments_tr import register_provider
        >>> register_provider("paytr", PayTRProvider)
    """
    registry.register(name, provider_class)


def is_provider_available(name: str) -> bool:
    """
    Check if a provider is available (registered).

    Args:
        name: Provider name

    Returns:
        True if provider is registered and available
    """
    return registry.is_registered(name)


def is_iyzico_enabled(country_code: str | None = None) -> bool:
    """
    Check if iyzico is the payment provider.

    Args:
        country_code: Optional country code to check country-specific provider

    Returns:
        True if iyzico is the configured provider

    Examples:
        >>> is_iyzico_enabled()           # Check default
        >>> is_iyzico_enabled("TR")       # Check for Turkey
    """
    return get_provider_name(country_code) == "iyzico"


def is_stripe_enabled(country_code: str | None = None) -> bool:
    """
    Check if Stripe is the payment provider.

    Args:
        country_code: Optional country code to check country-specific provider

    Returns:
        True if Stripe is the configured provider

    Examples:
        >>> is_stripe_enabled()           # Check default
        >>> is_stripe_enabled("US")       # Check for USA
    """
    return get_provider_name(country_code) == "stripe"
