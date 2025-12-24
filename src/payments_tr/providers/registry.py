"""
Payment provider registry and factory.

This module provides a registry for payment providers and factory functions
to get the configured provider instance.
"""

from __future__ import annotations

import logging
from functools import cache
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from payments_tr.providers.base import PaymentProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for payment provider classes.

    This allows dynamic registration of provider adapters and
    retrieval based on configuration.

    Example:
        >>> from payments_tr.providers import registry
        >>> registry.register("custom", CustomProviderAdapter)
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

    def get(self, name: str | None = None) -> PaymentProvider:
        """
        Get a provider instance by name.

        Args:
            name: Provider name, or None to use configured default

        Returns:
            PaymentProvider instance

        Raises:
            ValueError: If provider not found
        """
        name = (name or self._get_default_name()).lower()

        if name not in self._providers:
            available = ", ".join(self._providers.keys()) or "none"
            raise ValueError(
                f"Unknown payment provider: {name}. "
                f"Available providers: {available}. "
                f"Make sure the provider package is installed "
                f"(e.g., pip install django-payments-tr[{name}])"
            )

        logger.info(f"Using payment provider: {name}")
        return self._providers[name]()

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
        payments_settings = getattr(settings, "PAYMENTS_TR", {})
        return payments_settings.get("DEFAULT_PROVIDER", "stripe")

    def clear(self) -> None:
        """Clear all registered providers (useful for testing)."""
        self._providers.clear()


# Global registry instance
registry = ProviderRegistry()


def get_payment_provider(name: str | None = None) -> PaymentProvider:
    """
    Get the configured payment provider instance.

    The provider is determined by:
    1. The name parameter if provided
    2. The PAYMENT_PROVIDER Django setting
    3. Default to "stripe" if neither is set

    Args:
        name: Optional provider name to use instead of setting

    Returns:
        PaymentProvider instance

    Raises:
        ValueError: If the provider name is not recognized

    Example:
        >>> provider = get_payment_provider()
        >>> result = provider.create_payment(payment, callback_url=url)

        >>> iyzico = get_payment_provider("iyzico")
        >>> stripe = get_payment_provider("stripe")
    """
    return registry.get(name)


@cache
def get_default_provider() -> PaymentProvider:
    """
    Get the default payment provider (cached).

    This is useful for views that need a consistent provider instance.
    The result is cached for the lifetime of the process.

    Returns:
        PaymentProvider instance
    """
    return get_payment_provider()


def get_provider_name() -> str:
    """
    Get the name of the configured payment provider.

    Returns:
        Provider name string (e.g., "stripe" or "iyzico")
    """
    payments_settings = getattr(settings, "PAYMENTS_TR", {})
    return payments_settings.get("DEFAULT_PROVIDER", "stripe").lower()


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
        >>> register_provider("paytr", PayTRAdapter)
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
