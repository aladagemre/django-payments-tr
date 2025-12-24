"""Tests for testing utilities (mocks and utils)."""

import pytest

from payments_tr.providers.base import BuyerInfo, PaymentResult, RefundResult, WebhookResult
from payments_tr.testing.mocks import MockPaymentProvider, MockWebhookEvent
from payments_tr.testing.utils import (
    MockPayment,
    PaymentTestCase,
    assert_payment_failed,
    assert_payment_success,
    assert_refund_success,
    create_test_buyer_info,
    create_test_payment,
)


class TestMockPaymentProvider:
    """Test MockPaymentProvider class."""

    def test_provider_name(self):
        """Test provider name."""
        provider = MockPaymentProvider()
        assert provider.provider_name == "mock"

    def test_init(self):
        """Test initialization."""
        provider = MockPaymentProvider()
        assert provider.calls == []
        assert provider._next_result is None
        assert provider._should_fail is False
        assert provider._failure_message == "Mock payment failed"

    def test_set_next_result(self):
        """Test setting next result."""
        provider = MockPaymentProvider()
        result = PaymentResult(success=True, provider_payment_id="test_123")
        provider.set_next_result(result)
        assert provider._next_result == result

    def test_set_should_fail(self):
        """Test configuring provider to fail."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True, "Custom error")
        assert provider._should_fail is True
        assert provider._failure_message == "Custom error"

    def test_set_should_fail_default_message(self):
        """Test setting should fail with default message."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True)
        assert provider._should_fail is True
        assert provider._failure_message == "Mock payment failed"

    def test_reset(self):
        """Test resetting provider state."""
        provider = MockPaymentProvider()
        provider.calls.append({"test": "data"})
        provider._next_result = PaymentResult(success=True)
        provider._should_fail = True
        provider._failure_message = "Custom error"

        provider.reset()

        assert provider.calls == []
        assert provider._next_result is None
        assert provider._should_fail is False
        assert provider._failure_message == "Mock payment failed"

    def test_create_payment_default(self):
        """Test creating payment with default success."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123", amount=5000)

        result = provider.create_payment(payment)

        assert result.success is True
        assert result.provider_payment_id == "mock_pay_123"
        assert result.status == "succeeded"
        assert result.token == "tok_mock_pay_123"

    def test_create_payment_records_call(self):
        """Test that create_payment records the call."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123", amount=5000)
        buyer_info = BuyerInfo(email="test@example.com")

        provider.create_payment(
            payment,
            currency="USD",
            callback_url="https://example.com/callback",
            buyer_info=buyer_info,
        )

        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["method"] == "create_payment"
        assert call["payment"] == payment
        assert call["currency"] == "USD"
        assert call["callback_url"] == "https://example.com/callback"
        assert call["buyer_info"] == buyer_info

    def test_create_payment_with_failure(self):
        """Test creating payment when configured to fail."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True, "Payment declined")
        payment = MockPayment(id="pay_123")

        result = provider.create_payment(payment)

        assert result.success is False
        assert result.error_message == "Payment declined"
        assert result.error_code == "MOCK_ERROR"

    def test_create_payment_with_custom_result(self):
        """Test creating payment with custom result."""
        provider = MockPaymentProvider()
        custom_result = PaymentResult(
            success=True,
            provider_payment_id="custom_123",
            status="pending",
        )
        provider.set_next_result(custom_result)
        payment = MockPayment(id="pay_123")

        result = provider.create_payment(payment)

        assert result == custom_result
        # Next result should be cleared
        assert provider._next_result is None

    def test_confirm_payment_default(self):
        """Test confirming payment with default success."""
        provider = MockPaymentProvider()

        result = provider.confirm_payment("pay_123")

        assert result.success is True
        assert result.provider_payment_id == "pay_123"
        assert result.status == "succeeded"

    def test_confirm_payment_records_call(self):
        """Test that confirm_payment records the call."""
        provider = MockPaymentProvider()

        provider.confirm_payment("pay_123")

        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["method"] == "confirm_payment"
        assert call["provider_payment_id"] == "pay_123"

    def test_confirm_payment_with_failure(self):
        """Test confirming payment when configured to fail."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True)

        result = provider.confirm_payment("pay_123")

        assert result.success is False
        assert result.error_code == "MOCK_ERROR"

    def test_confirm_payment_with_custom_result(self):
        """Test confirming payment with custom result."""
        provider = MockPaymentProvider()
        custom_result = PaymentResult(success=True, status="processing")
        provider.set_next_result(custom_result)

        result = provider.confirm_payment("pay_123")

        assert result == custom_result

    def test_create_refund_default(self):
        """Test creating refund with default success."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123", amount=10000)

        result = provider.create_refund(payment, amount=5000, reason="Customer request")

        assert result.success is True
        assert result.provider_refund_id == "refund_mock_pay_123"
        assert result.amount == 5000
        assert result.status == "succeeded"

    def test_create_refund_full_amount(self):
        """Test creating refund for full amount."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123", amount=10000)

        result = provider.create_refund(payment)

        assert result.success is True
        assert result.amount == 10000  # Full amount

    def test_create_refund_records_call(self):
        """Test that create_refund records the call."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123", amount=10000)

        provider.create_refund(payment, amount=5000, reason="Test")

        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["method"] == "create_refund"
        assert call["payment"] == payment
        assert call["amount"] == 5000
        assert call["reason"] == "Test"

    def test_create_refund_with_failure(self):
        """Test creating refund when configured to fail."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True)
        payment = MockPayment(id="pay_123")

        result = provider.create_refund(payment)

        assert result.success is False
        assert result.error_code == "MOCK_ERROR"

    def test_create_refund_with_custom_result(self):
        """Test creating refund with custom result."""
        provider = MockPaymentProvider()
        custom_result = RefundResult(success=True, provider_refund_id="custom_ref")
        provider.set_next_result(custom_result)
        payment = MockPayment(id="pay_123")

        result = provider.create_refund(payment)

        assert result == custom_result

    def test_handle_webhook_default(self):
        """Test handling webhook with default success."""
        provider = MockPaymentProvider()

        result = provider.handle_webhook(
            payload=b'{"event": "payment.succeeded"}',
            signature="sig_123",
        )

        assert result.success is True
        assert result.event_type == "payment.succeeded"
        assert result.provider_payment_id == "mock_payment_123"
        assert result.status == "succeeded"

    def test_handle_webhook_records_call(self):
        """Test that handle_webhook records the call."""
        provider = MockPaymentProvider()
        payload = {"event": "test"}

        provider.handle_webhook(payload=payload, signature="sig_123")

        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["method"] == "handle_webhook"
        assert call["payload"] == payload
        assert call["signature"] == "sig_123"

    def test_handle_webhook_with_failure(self):
        """Test handling webhook when configured to fail."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True)

        result = provider.handle_webhook(payload=b"test")

        assert result.success is False
        assert result.error_code == "MOCK_ERROR"

    def test_handle_webhook_with_custom_result(self):
        """Test handling webhook with custom result."""
        provider = MockPaymentProvider()
        custom_result = WebhookResult(
            success=True,
            event_type="payment.failed",
            provider_payment_id="pay_456",
        )
        provider.set_next_result(custom_result)

        result = provider.handle_webhook(payload=b"test")

        assert result == custom_result

    def test_get_payment_status_default(self):
        """Test getting payment status with default."""
        provider = MockPaymentProvider()

        status = provider.get_payment_status("pay_123")

        assert status == "succeeded"

    def test_get_payment_status_records_call(self):
        """Test that get_payment_status records the call."""
        provider = MockPaymentProvider()

        provider.get_payment_status("pay_123")

        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["method"] == "get_payment_status"
        assert call["provider_payment_id"] == "pay_123"

    def test_get_payment_status_with_failure(self):
        """Test getting payment status when configured to fail."""
        provider = MockPaymentProvider()
        provider.set_should_fail(True)

        status = provider.get_payment_status("pay_123")

        assert status == "failed"

    def test_get_call_count_total(self):
        """Test getting total call count."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123")

        provider.create_payment(payment)
        provider.confirm_payment("pay_123")
        provider.get_payment_status("pay_123")

        assert provider.get_call_count() == 3

    def test_get_call_count_by_method(self):
        """Test getting call count for specific method."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123")

        provider.create_payment(payment)
        provider.create_payment(payment)
        provider.confirm_payment("pay_123")

        assert provider.get_call_count("create_payment") == 2
        assert provider.get_call_count("confirm_payment") == 1
        assert provider.get_call_count("create_refund") == 0

    def test_get_last_call_overall(self):
        """Test getting last call overall."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123")

        provider.create_payment(payment)
        provider.confirm_payment("pay_456")

        last_call = provider.get_last_call()
        assert last_call["method"] == "confirm_payment"
        assert last_call["provider_payment_id"] == "pay_456"

    def test_get_last_call_by_method(self):
        """Test getting last call for specific method."""
        provider = MockPaymentProvider()
        payment = MockPayment(id="pay_123")

        provider.create_payment(payment)
        provider.confirm_payment("pay_456")
        provider.create_payment(payment)

        last_create = provider.get_last_call("create_payment")
        assert last_create["method"] == "create_payment"

        last_confirm = provider.get_last_call("confirm_payment")
        assert last_confirm["provider_payment_id"] == "pay_456"

    def test_get_last_call_empty(self):
        """Test getting last call when no calls made."""
        provider = MockPaymentProvider()

        assert provider.get_last_call() is None
        assert provider.get_last_call("create_payment") is None

    def test_supports_methods(self):
        """Test support checking methods."""
        provider = MockPaymentProvider()

        assert provider.supports_checkout_form() is True
        assert provider.supports_redirect() is True
        assert provider.supports_installments() is True
        assert provider.supports_subscriptions() is True


class TestMockWebhookEvent:
    """Test MockWebhookEvent class."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        event = MockWebhookEvent()

        assert event.provider == "mock"
        assert event.event_type == "payment.succeeded"
        assert event.event_id == "evt_mock_123"
        assert event.payload == {}
        assert event.signature == "mock_signature"
        assert event.processed is False
        assert event.success is False
        assert event.retry_count == 0
        assert event.max_retries == 3

    def test_init_custom(self):
        """Test initialization with custom values."""
        payload = {"amount": 5000}
        event = MockWebhookEvent(
            provider="stripe",
            event_type="charge.succeeded",
            event_id="evt_123",
            payload=payload,
            signature="sig_abc",
        )

        assert event.provider == "stripe"
        assert event.event_type == "charge.succeeded"
        assert event.event_id == "evt_123"
        assert event.payload == payload
        assert event.signature == "sig_abc"

    def test_mark_processing_started(self):
        """Test marking processing started."""
        event = MockWebhookEvent()
        event.mark_processing_started()
        # This method is a no-op, just verify it doesn't raise

    def test_mark_success(self):
        """Test marking as successful."""
        event = MockWebhookEvent()
        event.mark_success()

        assert event.processed is True
        assert event.success is True

    def test_mark_failed(self):
        """Test marking as failed."""
        event = MockWebhookEvent()
        event.mark_failed("Test error")

        assert event.processed is True
        assert event.success is False
        assert event.retry_count == 1

    def test_mark_failed_increments_retry(self):
        """Test that marking failed increments retry count."""
        event = MockWebhookEvent()

        event.mark_failed("Error 1")
        assert event.retry_count == 1

        event.mark_failed("Error 2")
        assert event.retry_count == 2

    def test_should_retry_true(self):
        """Test should retry when under max retries."""
        event = MockWebhookEvent()
        event.mark_failed("Error")

        assert event.should_retry() is True

    def test_should_retry_false_at_max(self):
        """Test should not retry when at max retries."""
        event = MockWebhookEvent()

        # Fail 3 times to reach max
        for _ in range(3):
            event.mark_failed("Error")

        assert event.should_retry() is False

    def test_should_retry_false_when_successful(self):
        """Test should not retry when already successful."""
        event = MockWebhookEvent()
        event.mark_success()

        assert event.should_retry() is False

    def test_schedule_retry(self):
        """Test scheduling retry."""
        event = MockWebhookEvent()
        event.processed = True

        event.schedule_retry(delay_seconds=120)

        assert event.processed is False


class TestMockPayment:
    """Test MockPayment class."""

    def test_init(self):
        """Test initialization."""
        payment = MockPayment(id=123, amount=5000, currency="USD")

        assert payment.id == 123
        assert payment.amount == 5000
        assert payment.currency == "USD"

    def test_init_defaults(self):
        """Test initialization with defaults."""
        payment = MockPayment()

        assert payment.id == 1
        assert payment.amount == 10000
        assert payment.currency == "TRY"


class TestCreateTestPayment:
    """Test create_test_payment function."""

    def test_create_test_payment_defaults(self):
        """Test creating payment with defaults."""
        payment = create_test_payment()

        assert isinstance(payment, MockPayment)
        assert payment.id == 1
        assert payment.amount == 10000
        assert payment.currency == "TRY"

    def test_create_test_payment_custom(self):
        """Test creating payment with custom values."""
        payment = create_test_payment(id="pay_123", amount=5000, currency="USD")

        assert payment.id == "pay_123"
        assert payment.amount == 5000
        assert payment.currency == "USD"


class TestCreateTestBuyerInfo:
    """Test create_test_buyer_info function."""

    def test_create_test_buyer_info_defaults(self):
        """Test creating buyer info with defaults."""
        buyer = create_test_buyer_info()

        assert isinstance(buyer, BuyerInfo)
        assert buyer.email == "test@example.com"
        assert buyer.name == "Test"
        assert buyer.surname == "User"

    def test_create_test_buyer_info_custom(self):
        """Test creating buyer info with custom values."""
        buyer = create_test_buyer_info(
            email="custom@example.com",
            name="John",
            surname="Doe",
            phone="+905551234567",
        )

        assert buyer.email == "custom@example.com"
        assert buyer.name == "John"
        assert buyer.surname == "Doe"
        assert buyer.phone == "+905551234567"


class TestAssertPaymentSuccess:
    """Test assert_payment_success function."""

    def test_assert_payment_success_valid(self):
        """Test asserting successful payment."""
        result = PaymentResult(
            success=True,
            provider_payment_id="pay_123",
            status="succeeded",
        )

        # Should not raise
        assert_payment_success(result)

    def test_assert_payment_success_with_status(self):
        """Test asserting successful payment with specific status."""
        result = PaymentResult(
            success=True,
            provider_payment_id="pay_123",
            status="pending",
        )

        # Should not raise
        assert_payment_success(result, expected_status="pending")

    def test_assert_payment_success_failure(self):
        """Test asserting successful payment when it failed."""
        result = PaymentResult(success=False, error_message="Payment failed")

        with pytest.raises(AssertionError, match="Payment failed"):
            assert_payment_success(result)

    def test_assert_payment_success_wrong_status(self):
        """Test asserting successful payment with wrong status."""
        result = PaymentResult(
            success=True,
            provider_payment_id="pay_123",
            status="pending",
        )

        with pytest.raises(AssertionError, match="Expected status"):
            assert_payment_success(result, expected_status="succeeded")

    def test_assert_payment_success_missing_payment_id(self):
        """Test asserting successful payment without payment ID."""
        result = PaymentResult(success=True, status="succeeded")

        with pytest.raises(AssertionError, match="Missing provider payment ID"):
            assert_payment_success(result)


class TestAssertPaymentFailed:
    """Test assert_payment_failed function."""

    def test_assert_payment_failed_valid(self):
        """Test asserting failed payment."""
        result = PaymentResult(
            success=False,
            error_message="Card declined",
            error_code="CARD_DECLINED",
        )

        # Should not raise
        assert_payment_failed(result)

    def test_assert_payment_failed_with_error_code(self):
        """Test asserting failed payment with specific error code."""
        result = PaymentResult(
            success=False,
            error_message="Card declined",
            error_code="CARD_DECLINED",
        )

        # Should not raise
        assert_payment_failed(result, expected_error_code="CARD_DECLINED")

    def test_assert_payment_failed_success(self):
        """Test asserting failed payment when it succeeded."""
        result = PaymentResult(success=True, provider_payment_id="pay_123")

        with pytest.raises(AssertionError, match="succeeded when failure was expected"):
            assert_payment_failed(result)

    def test_assert_payment_failed_wrong_error_code(self):
        """Test asserting failed payment with wrong error code."""
        result = PaymentResult(
            success=False,
            error_message="Card declined",
            error_code="CARD_DECLINED",
        )

        with pytest.raises(AssertionError, match="Expected error code"):
            assert_payment_failed(result, expected_error_code="INSUFFICIENT_FUNDS")

    def test_assert_payment_failed_missing_error_message(self):
        """Test asserting failed payment without error message."""
        result = PaymentResult(success=False)

        with pytest.raises(AssertionError, match="Missing error message"):
            assert_payment_failed(result)


class TestAssertRefundSuccess:
    """Test assert_refund_success function."""

    def test_assert_refund_success_valid(self):
        """Test asserting successful refund."""
        result = RefundResult(
            success=True,
            provider_refund_id="ref_123",
            amount=5000,
        )

        # Should not raise
        assert_refund_success(result)

    def test_assert_refund_success_with_amount(self):
        """Test asserting successful refund with specific amount."""
        result = RefundResult(
            success=True,
            provider_refund_id="ref_123",
            amount=5000,
        )

        # Should not raise
        assert_refund_success(result, expected_amount=5000)

    def test_assert_refund_success_failure(self):
        """Test asserting successful refund when it failed."""
        result = RefundResult(success=False, error_message="Refund failed")

        with pytest.raises(AssertionError, match="Refund failed"):
            assert_refund_success(result)

    def test_assert_refund_success_missing_refund_id(self):
        """Test asserting successful refund without refund ID."""
        result = RefundResult(success=True, amount=5000)

        with pytest.raises(AssertionError, match="Missing provider refund ID"):
            assert_refund_success(result)

    def test_assert_refund_success_wrong_amount(self):
        """Test asserting successful refund with wrong amount."""
        result = RefundResult(
            success=True,
            provider_refund_id="ref_123",
            amount=3000,
        )

        with pytest.raises(AssertionError, match="Expected amount"):
            assert_refund_success(result, expected_amount=5000)


class TestPaymentTestCase:
    """Test PaymentTestCase class."""

    def test_setup_method(self):
        """Test setup method creates provider."""
        test_case = PaymentTestCase()
        test_case.setup_method()

        assert hasattr(test_case, "provider")
        assert isinstance(test_case.provider, MockPaymentProvider)

    def test_teardown_method(self):
        """Test teardown method resets provider."""
        test_case = PaymentTestCase()
        test_case.setup_method()

        # Make some calls
        payment = test_case.create_payment()
        test_case.provider.create_payment(payment)
        assert len(test_case.provider.calls) > 0

        # Teardown should reset
        test_case.teardown_method()
        assert len(test_case.provider.calls) == 0

    def test_create_payment(self):
        """Test create_payment helper method."""
        test_case = PaymentTestCase()

        payment = test_case.create_payment(id=123, amount=5000, currency="USD")

        assert isinstance(payment, MockPayment)
        assert payment.id == 123
        assert payment.amount == 5000
        assert payment.currency == "USD"

    def test_create_buyer_info(self):
        """Test create_buyer_info helper method."""
        test_case = PaymentTestCase()

        buyer = test_case.create_buyer_info(email="test@test.com", phone="+905551234567")

        assert isinstance(buyer, BuyerInfo)
        assert buyer.email == "test@test.com"
        assert buyer.phone == "+905551234567"

    def test_assert_payment_success_wrapper(self):
        """Test assert_payment_success wrapper method."""
        test_case = PaymentTestCase()

        result = PaymentResult(
            success=True,
            provider_payment_id="pay_123",
            status="succeeded",
        )

        # Should not raise
        test_case.assert_payment_success(result)

    def test_assert_payment_failed_wrapper(self):
        """Test assert_payment_failed wrapper method."""
        test_case = PaymentTestCase()

        result = PaymentResult(
            success=False,
            error_message="Error",
            error_code="TEST_ERROR",
        )

        # Should not raise
        test_case.assert_payment_failed(result, expected_error_code="TEST_ERROR")

    def test_assert_refund_success_wrapper(self):
        """Test assert_refund_success wrapper method."""
        test_case = PaymentTestCase()

        result = RefundResult(
            success=True,
            provider_refund_id="ref_123",
            amount=5000,
        )

        # Should not raise
        test_case.assert_refund_success(result, expected_amount=5000)
