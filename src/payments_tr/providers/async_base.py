"""
Async versions of payment provider interfaces.

This module provides async/await support for payment operations,
allowing for non-blocking I/O in async frameworks like Django async views,
FastAPI, or aiohttp applications.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any

from payments_tr.providers.base import (
    BuyerInfo,
    PaymentLike,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
)


def run_sync_in_thread(func):
    """Decorator to run sync function in thread pool."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    return wrapper


class AsyncPaymentProvider(ABC):
    """
    Abstract base class for async payment providers.

    This interface mirrors PaymentProvider but uses async/await.
    Providers can implement this interface for native async support,
    or use AsyncProviderAdapter to wrap a sync provider.

    Example:
        >>> provider = AsyncStripeAdapter()
        >>> result = await provider.create_payment_async(payment, callback_url="...")
    """

    provider_name: str = ""

    @abstractmethod
    async def create_payment_async(
        self,
        payment: PaymentLike,
        *,
        currency: str = "TRY",
        callback_url: str | None = None,
        buyer_info: BuyerInfo | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """
        Create a payment with the provider (async).

        Args:
            payment: Payment object with id, amount, currency
            currency: Currency code (default: TRY)
            callback_url: URL for provider callbacks/redirects
            buyer_info: Buyer information for the payment
            **kwargs: Provider-specific options

        Returns:
            PaymentResult with provider-specific details
        """
        pass

    @abstractmethod
    async def confirm_payment_async(self, provider_payment_id: str) -> PaymentResult:
        """
        Confirm/retrieve a payment status (async).

        Args:
            provider_payment_id: The provider's payment/transaction ID

        Returns:
            PaymentResult with confirmation status
        """
        pass

    @abstractmethod
    async def create_refund_async(
        self,
        payment: PaymentLike,
        amount: int | None = None,
        reason: str = "",
        **kwargs: Any,
    ) -> RefundResult:
        """
        Create a refund for a payment (async).

        Args:
            payment: The original payment to refund
            amount: Amount to refund, or None for full refund
            reason: Reason for the refund
            **kwargs: Provider-specific options

        Returns:
            RefundResult with refund details
        """
        pass

    @abstractmethod
    async def handle_webhook_async(
        self,
        payload: bytes,
        signature: str | None = None,
        **kwargs: Any,
    ) -> WebhookResult:
        """
        Handle a webhook/callback from the provider (async).

        Args:
            payload: Raw webhook payload (bytes)
            signature: Webhook signature for verification
            **kwargs: Additional data

        Returns:
            WebhookResult with event processing status
        """
        pass

    @abstractmethod
    async def get_payment_status_async(self, provider_payment_id: str) -> str:
        """
        Get the current status of a payment (async).

        Args:
            provider_payment_id: The provider's payment/transaction ID

        Returns:
            Status string
        """
        pass

    def supports_checkout_form(self) -> bool:
        """Whether the provider supports an embedded checkout form."""
        return False

    def supports_redirect(self) -> bool:
        """Whether the provider uses redirect-based checkout."""
        return False

    def supports_subscriptions(self) -> bool:
        """Whether the provider supports recurring/subscription payments."""
        return False

    def supports_installments(self) -> bool:
        """Whether the provider supports installment payments."""
        return False


class AsyncProviderAdapter(AsyncPaymentProvider):
    """
    Adapter to use sync PaymentProvider in async context.

    This adapter wraps a synchronous provider and runs its methods
    in a thread pool to avoid blocking the event loop.

    Example:
        >>> sync_provider = IyzicoAdapter()
        >>> async_provider = AsyncProviderAdapter(sync_provider)
        >>> result = await async_provider.create_payment_async(payment)
    """

    def __init__(self, sync_provider: PaymentProvider):
        """
        Initialize adapter with sync provider.

        Args:
            sync_provider: Synchronous PaymentProvider instance
        """
        self.sync_provider = sync_provider
        self.provider_name = sync_provider.provider_name

    async def create_payment_async(
        self,
        payment: PaymentLike,
        *,
        currency: str = "TRY",
        callback_url: str | None = None,
        buyer_info: BuyerInfo | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """Create payment in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.sync_provider.create_payment(
                payment,
                currency=currency,
                callback_url=callback_url,
                buyer_info=buyer_info,
                **kwargs,
            ),
        )

    async def confirm_payment_async(self, provider_payment_id: str) -> PaymentResult:
        """Confirm payment in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.sync_provider.confirm_payment(provider_payment_id)
        )

    async def create_refund_async(
        self,
        payment: PaymentLike,
        amount: int | None = None,
        reason: str = "",
        **kwargs: Any,
    ) -> RefundResult:
        """Create refund in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.sync_provider.create_refund(
                payment, amount=amount, reason=reason, **kwargs
            ),
        )

    async def handle_webhook_async(
        self,
        payload: bytes,
        signature: str | None = None,
        **kwargs: Any,
    ) -> WebhookResult:
        """Handle webhook in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.sync_provider.handle_webhook(
                payload, signature=signature, **kwargs
            ),
        )

    async def get_payment_status_async(self, provider_payment_id: str) -> str:
        """Get payment status in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.sync_provider.get_payment_status(provider_payment_id)
        )

    def supports_checkout_form(self) -> bool:
        """Whether the provider supports an embedded checkout form."""
        return self.sync_provider.supports_checkout_form()

    def supports_redirect(self) -> bool:
        """Whether the provider uses redirect-based checkout."""
        return self.sync_provider.supports_redirect()

    def supports_subscriptions(self) -> bool:
        """Whether the provider supports recurring/subscription payments."""
        return self.sync_provider.supports_subscriptions()

    def supports_installments(self) -> bool:
        """Whether the provider supports installment payments."""
        return self.sync_provider.supports_installments()


def get_async_payment_provider(
    name: str | None = None,
) -> AsyncPaymentProvider:
    """
    Get an async payment provider by name.

    This function wraps the sync provider with AsyncProviderAdapter.
    Future implementations may provide native async providers.

    Args:
        name: Provider name (e.g., 'iyzico', 'stripe'), or None for default

    Returns:
        AsyncPaymentProvider instance

    Example:
        >>> provider = get_async_payment_provider('stripe')
        >>> result = await provider.create_payment_async(payment)
    """
    from payments_tr.providers.registry import get_payment_provider

    sync_provider = get_payment_provider(name)
    return AsyncProviderAdapter(sync_provider)
