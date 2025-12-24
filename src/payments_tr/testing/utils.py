"""
Testing utilities and helpers.

This module provides helper functions for testing payment operations.
"""

from __future__ import annotations

from typing import Any

from payments_tr.providers.base import BuyerInfo, PaymentResult, RefundResult


class MockPayment:
    """Mock payment object for testing."""

    def __init__(
        self,
        id: int | str = 1,
        amount: int = 10000,
        currency: str = "TRY",
    ):
        """
        Initialize mock payment.

        Args:
            id: Payment ID
            amount: Amount in smallest currency unit (e.g., kuruş)
            currency: Currency code
        """
        self.id = id
        self.amount = amount
        self.currency = currency


def create_test_payment(
    id: int | str = 1,
    amount: int = 10000,
    currency: str = "TRY",
) -> MockPayment:
    """
    Create a test payment object.

    Args:
        id: Payment ID
        amount: Amount in smallest currency unit
        currency: Currency code

    Returns:
        Mock payment object

    Example:
        >>> payment = create_test_payment(id=123, amount=5000, currency="TRY")
        >>> assert payment.amount == 5000
    """
    return MockPayment(id=id, amount=amount, currency=currency)


def create_test_buyer_info(
    email: str = "test@example.com",
    name: str = "Test",
    surname: str = "User",
    **kwargs: Any,
) -> BuyerInfo:
    """
    Create test buyer information.

    Args:
        email: Buyer email
        name: First name
        surname: Last name
        **kwargs: Additional buyer info fields

    Returns:
        BuyerInfo instance

    Example:
        >>> buyer = create_test_buyer_info(email="user@test.com")
        >>> assert buyer.email == "user@test.com"
    """
    return BuyerInfo(
        email=email,
        name=name,
        surname=surname,
        **kwargs,
    )


def assert_payment_success(
    result: PaymentResult,
    expected_status: str = "succeeded",
) -> None:
    """
    Assert that payment result is successful.

    Args:
        result: PaymentResult to check
        expected_status: Expected status string

    Raises:
        AssertionError: If payment is not successful

    Example:
        >>> result = provider.create_payment(payment)
        >>> assert_payment_success(result)
    """
    assert result.success, f"Payment failed: {result.error_message}"
    if expected_status:
        assert result.status == expected_status, (
            f"Expected status '{expected_status}', got '{result.status}'"
        )
    assert result.provider_payment_id is not None, "Missing provider payment ID"


def assert_payment_failed(
    result: PaymentResult,
    expected_error_code: str | None = None,
) -> None:
    """
    Assert that payment result is failed.

    Args:
        result: PaymentResult to check
        expected_error_code: Expected error code (optional)

    Raises:
        AssertionError: If payment is successful

    Example:
        >>> result = provider.create_payment(payment)
        >>> assert_payment_failed(result, expected_error_code="CARD_DECLINED")
    """
    assert not result.success, "Payment succeeded when failure was expected"
    assert result.error_message is not None, "Missing error message"
    if expected_error_code:
        assert result.error_code == expected_error_code, (
            f"Expected error code '{expected_error_code}', got '{result.error_code}'"
        )


def assert_refund_success(
    result: RefundResult,
    expected_amount: int | None = None,
) -> None:
    """
    Assert that refund result is successful.

    Args:
        result: RefundResult to check
        expected_amount: Expected refund amount (optional)

    Raises:
        AssertionError: If refund is not successful

    Example:
        >>> result = provider.create_refund(payment, amount=5000)
        >>> assert_refund_success(result, expected_amount=5000)
    """
    assert result.success, f"Refund failed: {result.error_message}"
    assert result.provider_refund_id is not None, "Missing provider refund ID"
    if expected_amount is not None:
        assert result.amount == expected_amount, (
            f"Expected amount {expected_amount}, got {result.amount}"
        )


class PaymentTestCase:
    """
    Base test case for payment testing.

    Provides helper methods and common setup for payment tests.

    Example:
        >>> class TestMyPayments(PaymentTestCase):
        ...     def test_payment_creation(self):
        ...         payment = self.create_payment()
        ...         result = self.provider.create_payment(payment)
        ...         self.assert_payment_success(result)
    """

    def setup_method(self):
        """Set up test method."""
        from payments_tr.testing.mocks import MockPaymentProvider

        self.provider = MockPaymentProvider()

    def teardown_method(self):
        """Tear down test method."""
        if hasattr(self, "provider"):
            self.provider.reset()

    def create_payment(
        self,
        id: int | str = 1,
        amount: int = 10000,
        currency: str = "TRY",
    ) -> MockPayment:
        """Create test payment."""
        return create_test_payment(id=id, amount=amount, currency=currency)

    def create_buyer_info(
        self,
        email: str = "test@example.com",
        **kwargs: Any,
    ) -> BuyerInfo:
        """Create test buyer info."""
        return create_test_buyer_info(email=email, **kwargs)

    def assert_payment_success(
        self,
        result: PaymentResult,
        expected_status: str = "succeeded",
    ) -> None:
        """Assert payment success."""
        assert_payment_success(result, expected_status)

    def assert_payment_failed(
        self,
        result: PaymentResult,
        expected_error_code: str | None = None,
    ) -> None:
        """Assert payment failure."""
        assert_payment_failed(result, expected_error_code)

    def assert_refund_success(
        self,
        result: RefundResult,
        expected_amount: int | None = None,
    ) -> None:
        """Assert refund success."""
        assert_refund_success(result, expected_amount)
