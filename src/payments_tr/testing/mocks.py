"""
Mock payment providers for testing.

These mocks allow testing payment flows without making actual API calls
to payment providers.
"""

from __future__ import annotations

from typing import Any

from payments_tr.providers.base import (
    BuyerInfo,
    PaymentLike,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
)


class MockPaymentProvider(PaymentProvider):
    """
    Mock payment provider for testing.

    This provider simulates payment operations without making real API calls.
    Useful for testing payment flows in isolation.

    Example:
        >>> provider = MockPaymentProvider()
        >>> provider.set_next_result(PaymentResult(success=True, provider_payment_id="test_123"))
        >>> result = provider.create_payment(payment)
        >>> assert result.success
    """

    provider_name = "mock"

    def __init__(self):
        """Initialize mock provider."""
        self.calls: list[dict[str, Any]] = []
        self._next_result: Any = None
        self._should_fail = False
        self._failure_message = "Mock payment failed"

    def set_next_result(self, result: Any) -> None:
        """
        Set the next result to return.

        Args:
            result: PaymentResult, RefundResult, or WebhookResult to return
        """
        self._next_result = result

    def set_should_fail(
        self, should_fail: bool = True, message: str = "Mock payment failed"
    ) -> None:
        """
        Configure provider to fail on next operation.

        Args:
            should_fail: Whether to fail
            message: Error message to return
        """
        self._should_fail = should_fail
        self._failure_message = message

    def reset(self) -> None:
        """Reset mock state."""
        self.calls = []
        self._next_result = None
        self._should_fail = False
        self._failure_message = "Mock payment failed"

    def create_payment(
        self,
        payment: PaymentLike,
        *,
        currency: str = "TRY",
        callback_url: str | None = None,
        buyer_info: BuyerInfo | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """Create a mock payment."""
        self.calls.append(
            {
                "method": "create_payment",
                "payment": payment,
                "currency": currency,
                "callback_url": callback_url,
                "buyer_info": buyer_info,
                "kwargs": kwargs,
            }
        )

        if self._should_fail:
            return PaymentResult(
                success=False,
                error_message=self._failure_message,
                error_code="MOCK_ERROR",
            )

        if self._next_result:
            result = self._next_result
            self._next_result = None
            return result

        # Default success result
        return PaymentResult(
            success=True,
            provider_payment_id=f"mock_{payment.id}",
            status="succeeded",
            token=f"tok_mock_{payment.id}",
        )

    def confirm_payment(self, provider_payment_id: str) -> PaymentResult:
        """Confirm a mock payment."""
        self.calls.append(
            {
                "method": "confirm_payment",
                "provider_payment_id": provider_payment_id,
            }
        )

        if self._should_fail:
            return PaymentResult(
                success=False,
                error_message=self._failure_message,
                error_code="MOCK_ERROR",
            )

        if self._next_result:
            result = self._next_result
            self._next_result = None
            return result

        return PaymentResult(
            success=True,
            provider_payment_id=provider_payment_id,
            status="succeeded",
        )

    def create_refund(
        self,
        payment: PaymentLike,
        amount: int | None = None,
        reason: str = "",
        **kwargs: Any,
    ) -> RefundResult:
        """Create a mock refund."""
        self.calls.append(
            {
                "method": "create_refund",
                "payment": payment,
                "amount": amount,
                "reason": reason,
                "kwargs": kwargs,
            }
        )

        if self._should_fail:
            return RefundResult(
                success=False,
                error_message=self._failure_message,
                error_code="MOCK_ERROR",
            )

        if self._next_result:
            result = self._next_result
            self._next_result = None
            return result

        return RefundResult(
            success=True,
            provider_refund_id=f"refund_mock_{payment.id}",
            amount=amount or payment.amount,
            status="succeeded",
        )

    def handle_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        **kwargs: Any,
    ) -> WebhookResult:
        """Handle a mock webhook."""
        self.calls.append(
            {
                "method": "handle_webhook",
                "payload": payload,
                "signature": signature,
                "kwargs": kwargs,
            }
        )

        if self._should_fail:
            return WebhookResult(
                success=False,
                error_message=self._failure_message,
                error_code="MOCK_ERROR",
            )

        if self._next_result:
            result = self._next_result
            self._next_result = None
            return result

        return WebhookResult(
            success=True,
            event_type="payment.succeeded",
            provider_payment_id="mock_payment_123",
            status="succeeded",
        )

    def get_payment_status(self, provider_payment_id: str) -> str:
        """Get mock payment status."""
        self.calls.append(
            {
                "method": "get_payment_status",
                "provider_payment_id": provider_payment_id,
            }
        )

        if self._should_fail:
            return "failed"

        return "succeeded"

    def get_call_count(self, method: str | None = None) -> int:
        """
        Get number of times a method was called.

        Args:
            method: Method name, or None for total calls

        Returns:
            Number of calls
        """
        if method is None:
            return len(self.calls)
        return sum(1 for call in self.calls if call["method"] == method)

    def get_last_call(self, method: str | None = None) -> dict[str, Any] | None:
        """
        Get last call to a method.

        Args:
            method: Method name, or None for last call overall

        Returns:
            Call dictionary or None
        """
        if method is None:
            return self.calls[-1] if self.calls else None

        for call in reversed(self.calls):
            if call["method"] == method:
                return call
        return None

    def supports_checkout_form(self) -> bool:
        """Mock supports checkout form."""
        return True

    def supports_redirect(self) -> bool:
        """Mock supports redirect."""
        return True

    def supports_installments(self) -> bool:
        """Mock supports installments."""
        return True

    def supports_subscriptions(self) -> bool:
        """Mock supports subscriptions."""
        return True


class MockWebhookEvent:
    """Mock webhook event for testing."""

    def __init__(
        self,
        provider: str = "mock",
        event_type: str = "payment.succeeded",
        event_id: str = "evt_mock_123",
        payload: dict[str, Any] | None = None,
        signature: str = "mock_signature",
    ):
        """Initialize mock webhook event."""
        self.provider = provider
        self.event_type = event_type
        self.event_id = event_id
        self.payload = payload or {}
        self.signature = signature
        self.processed = False
        self.success = False
        self.retry_count = 0
        self.max_retries = 3

    def mark_processing_started(self) -> None:
        """Mark as processing."""
        pass

    def mark_success(self) -> None:
        """Mark as successful."""
        self.processed = True
        self.success = True

    def mark_failed(self, error_message: str) -> None:
        """Mark as failed."""
        self.processed = True
        self.success = False
        self.retry_count += 1

    def should_retry(self) -> bool:
        """Check if should retry."""
        return self.retry_count < self.max_retries and not self.success

    def schedule_retry(self, delay_seconds: int = 60) -> None:
        """Schedule retry."""
        self.processed = False
