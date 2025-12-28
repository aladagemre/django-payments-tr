"""Tests for iyzico payment provider."""

from unittest.mock import MagicMock, patch

import pytest

from payments_tr.providers.base import BuyerInfo


class MockCheckoutFormResponse:
    """Mock iyzico checkout form response."""

    def __init__(self, success=True, token="test_token"):
        self.token = token
        self.payment_page_url = "https://iyzico.com/checkout/test_token"
        self.checkout_form_content = "<form>...</form>"
        self._success = success

    def is_successful(self):
        return self._success

    def to_dict(self):
        return {
            "token": self.token,
            "paymentPageUrl": self.payment_page_url,
        }


class MockCheckoutFormResultResponse:
    """Mock iyzico checkout form result response."""

    def __init__(self, success=True, payment_id="pay_123"):
        self._success = success
        self.payment_id = payment_id
        self.payment_status = "SUCCESS" if success else "FAILURE"
        self.error_message = None if success else "Payment failed"

    def is_successful(self):
        return self._success

    def to_dict(self):
        return {
            "paymentId": self.payment_id,
            "paymentStatus": self.payment_status,
        }


class MockRefundResponse:
    """Mock iyzico refund response."""

    def __init__(self, refund_id="ref_123"):
        self.refund_id = refund_id

    def to_dict(self):
        return {"refundId": self.refund_id}


class MockIyzicoClient:
    """Mock IyzicoClient for testing."""

    def __init__(self):
        self.create_checkout_form_called = False
        self.retrieve_checkout_form_called = False
        self.refund_payment_called = False

    def create_checkout_form(self, **kwargs):
        self.create_checkout_form_called = True
        self.create_checkout_form_kwargs = kwargs
        return MockCheckoutFormResponse()

    def retrieve_checkout_form(self, token):
        self.retrieve_checkout_form_called = True
        return MockCheckoutFormResultResponse()

    def refund_payment(self, **kwargs):
        self.refund_payment_called = True
        return MockRefundResponse()


@pytest.fixture
def mock_iyzico_client():
    """Create mock iyzico client."""
    return MockIyzicoClient()


@pytest.fixture
def iyzico_adapter(mock_iyzico_client):
    """Create iyzico adapter with mocked client."""
    with patch.dict("sys.modules", {"django_iyzico": MagicMock()}):
        with patch(
            "payments_tr.providers.iyzico.IyzicoProvider.__init__",
            lambda self: None,
        ):
            from payments_tr.providers.iyzico import IyzicoProvider

            adapter = IyzicoProvider()
            adapter._client = mock_iyzico_client
            return adapter


class TestIyzicoProvider:
    """Tests for IyzicoProvider."""

    def test_provider_name(self, iyzico_adapter):
        """Test provider name."""
        assert iyzico_adapter.provider_name == "iyzico"

    def test_create_payment_missing_callback(self, iyzico_adapter, mock_payment):
        """Test create payment fails without callback URL."""
        result = iyzico_adapter.create_payment(mock_payment)

        assert result.success is False
        assert "callback_url is required" in result.error_message

    def test_create_payment_success(self, iyzico_adapter, mock_payment, mock_iyzico_client):
        """Test successful payment creation."""
        buyer_info = BuyerInfo(email="test@example.com", name="Test", surname="User")

        result = iyzico_adapter.create_payment(
            mock_payment,
            callback_url="https://example.com/callback",
            buyer_info=buyer_info,
        )

        assert result.success is True
        assert result.token == "test_token"
        assert mock_iyzico_client.create_checkout_form_called

    def test_create_payment_with_dict_buyer_info(
        self, iyzico_adapter, mock_payment, mock_iyzico_client
    ):
        """Test payment creation with dict buyer info."""
        buyer_info = {"email": "test@example.com", "name": "Test", "surname": "User"}

        result = iyzico_adapter.create_payment(
            mock_payment,
            callback_url="https://example.com/callback",
            buyer_info=buyer_info,
        )

        assert result.success is True

    def test_create_payment_exception(self, iyzico_adapter, mock_payment):
        """Test payment creation handles exceptions."""
        iyzico_adapter._client.create_checkout_form = MagicMock(side_effect=Exception("API error"))

        result = iyzico_adapter.create_payment(
            mock_payment,
            callback_url="https://example.com/callback",
            buyer_info={"email": "test@example.com"},
        )

        assert result.success is False
        assert "API error" in result.error_message

    def test_confirm_payment_success(self, iyzico_adapter, mock_iyzico_client):
        """Test successful payment confirmation."""
        result = iyzico_adapter.confirm_payment("test_token")

        assert result.success is True
        assert result.status == "succeeded"
        assert mock_iyzico_client.retrieve_checkout_form_called

    def test_confirm_payment_failure(self, iyzico_adapter):
        """Test payment confirmation failure."""
        iyzico_adapter._client.retrieve_checkout_form = MagicMock(
            return_value=MockCheckoutFormResultResponse(success=False)
        )

        result = iyzico_adapter.confirm_payment("test_token")

        assert result.success is False

    def test_confirm_payment_exception(self, iyzico_adapter):
        """Test payment confirmation handles exceptions."""
        iyzico_adapter._client.retrieve_checkout_form = MagicMock(
            side_effect=Exception("API error")
        )

        result = iyzico_adapter.confirm_payment("test_token")

        assert result.success is False
        assert "API error" in result.error_message

    def test_create_refund_success(self, iyzico_adapter, mock_payment, mock_iyzico_client):
        """Test successful refund creation."""
        mock_payment.iyzico_payment_id = "pay_123"

        result = iyzico_adapter.create_refund(mock_payment, amount=5000)

        assert result.success is True
        assert mock_iyzico_client.refund_payment_called

    def test_create_refund_missing_payment_id(self, iyzico_adapter, mock_payment):
        """Test refund fails without payment ID."""
        result = iyzico_adapter.create_refund(mock_payment)

        assert result.success is False
        assert "No iyzico payment ID" in result.error_message

    def test_create_refund_exception(self, iyzico_adapter, mock_payment):
        """Test refund handles exceptions."""
        mock_payment.iyzico_payment_id = "pay_123"
        iyzico_adapter._client.refund_payment = MagicMock(side_effect=Exception("Refund error"))

        result = iyzico_adapter.create_refund(mock_payment)

        assert result.success is False
        assert "Refund error" in result.error_message

    def test_handle_webhook_success(self, iyzico_adapter):
        """Test successful webhook handling."""
        payload = b'{"token": "test_token"}'

        result = iyzico_adapter.handle_webhook(payload)

        assert result.success is True
        assert result.event_type == "payment.success"

    def test_handle_webhook_dict_payload(self, iyzico_adapter):
        """Test webhook with dict payload."""
        payload = {"token": "test_token"}

        result = iyzico_adapter.handle_webhook(payload)

        assert result.success is True

    def test_handle_webhook_no_token(self, iyzico_adapter):
        """Test webhook fails without token."""
        payload = b"{}"

        result = iyzico_adapter.handle_webhook(payload)

        assert result.success is False
        assert "No token" in result.error_message

    def test_handle_webhook_failed_confirmation(self, iyzico_adapter):
        """Test webhook with failed payment confirmation."""
        iyzico_adapter._client.retrieve_checkout_form = MagicMock(
            return_value=MockCheckoutFormResultResponse(success=False)
        )
        payload = {"token": "test_token"}

        result = iyzico_adapter.handle_webhook(payload)

        assert result.success is False
        assert result.event_type == "payment.failed"

    def test_handle_webhook_exception(self, iyzico_adapter):
        """Test webhook handles exceptions."""
        iyzico_adapter._client.retrieve_checkout_form = MagicMock(
            side_effect=Exception("Webhook error")
        )
        payload = {"token": "test_token"}

        result = iyzico_adapter.handle_webhook(payload)

        assert result.success is False

    def test_get_payment_status(self, iyzico_adapter):
        """Test getting payment status."""
        status = iyzico_adapter.get_payment_status("test_token")
        assert status == "succeeded"

    def test_supports_checkout_form(self, iyzico_adapter):
        """Test supports_checkout_form returns True."""
        assert iyzico_adapter.supports_checkout_form() is True

    def test_supports_redirect(self, iyzico_adapter):
        """Test supports_redirect returns True."""
        assert iyzico_adapter.supports_redirect() is True

    def test_supports_installments(self, iyzico_adapter):
        """Test supports_installments returns True."""
        assert iyzico_adapter.supports_installments() is True

    def test_extract_buyer_info_from_payment(self, iyzico_adapter, mock_payment):
        """Test extracting buyer info from payment object."""
        # Payment without client
        buyer_info = iyzico_adapter._extract_buyer_info(mock_payment)
        assert buyer_info.email == "customer@example.com"

    def test_extract_buyer_info_from_payment_with_client(self, iyzico_adapter):
        """Test extracting buyer info from payment with client."""
        mock_payment = MagicMock()
        mock_payment.client = MagicMock()
        mock_payment.client.id = 1
        mock_payment.client.user = MagicMock()
        mock_payment.client.user.email = "client@example.com"
        mock_payment.client.user.first_name = "John"
        mock_payment.client.user.last_name = "Doe"
        mock_payment.client.phone = "+905551234567"

        buyer_info = iyzico_adapter._extract_buyer_info(mock_payment)
        assert buyer_info.email == "client@example.com"


class TestIyzicoEdgeCases:
    """Tests for iyzico edge cases and error handling."""

    def test_confirm_payment_exception_with_error_code(self, iyzico_adapter, mock_iyzico_client):
        """Test confirm_payment extracts error_code from exception."""
        # Create exception with error_code attribute
        error = Exception("Custom error")
        error.error_code = "CUSTOM_ERROR_CODE"
        mock_iyzico_client.retrieve_checkout_form = MagicMock(side_effect=error)

        result = iyzico_adapter.confirm_payment("token_123")

        assert result.success is False
        assert result.error_code == "CUSTOM_ERROR_CODE"

    def test_confirm_payment_exception_without_error_code(self, iyzico_adapter, mock_iyzico_client):
        """Test confirm_payment uses default error_code when not provided."""
        mock_iyzico_client.retrieve_checkout_form = MagicMock(
            side_effect=Exception("Generic error")
        )

        result = iyzico_adapter.confirm_payment("token_123")

        assert result.success is False
        assert result.error_code == "IYZICO_ERROR"

    def test_get_payment_status_unknown(self, iyzico_adapter):
        """Test get_payment_status returns unknown when status is None."""
        # Mock confirm_payment to return a failed result with None status
        with patch.object(iyzico_adapter, "confirm_payment") as mock_confirm:
            from payments_tr.providers import PaymentResult

            mock_confirm.return_value = PaymentResult(
                success=False,
                error_message="Payment failed",
                status=None,  # This should make get_payment_status return "unknown"
            )

            status = iyzico_adapter.get_payment_status("token_123")

            assert status == "unknown"

    def test_build_checkout_request_without_basket_items(self, iyzico_adapter, mock_payment):
        """Test _build_checkout_request uses default basket when not provided."""
        buyer_info = BuyerInfo(
            email="test@example.com",
            name="Test",
            surname="User",
            phone="+905551234567",
        )

        # Call without basket_items - should build default basket
        # Method returns tuple: (order_data, buyer_dict, address_dict, basket_items)
        _, _, _, basket_items = iyzico_adapter._build_checkout_request(
            mock_payment, "TRY", buyer_info
        )

        # Default basket should have at least one item
        assert len(basket_items) > 0
        # First item should have payment amount
        assert basket_items[0]["price"] == str(mock_payment.amount / 100)

    def test_build_checkout_request_with_custom_basket_items(self, iyzico_adapter, mock_payment):
        """Test _build_checkout_request uses provided basket_items."""
        buyer_info = BuyerInfo(
            email="test@example.com",
            name="Test",
            surname="User",
            phone="+905551234567",
        )

        custom_basket = [
            {
                "id": "item1",
                "name": "Custom Item",
                "category1": "Electronics",
                "itemType": "PHYSICAL",
                "price": "100.00",
            }
        ]

        # Method returns tuple: (order_data, buyer_dict, address_dict, basket_items)
        _, _, _, basket_items = iyzico_adapter._build_checkout_request(
            mock_payment, "TRY", buyer_info, basket_items=custom_basket
        )

        # Should use the custom basket items
        assert basket_items == custom_basket

    def test_handle_webhook_exception_handling(self, iyzico_adapter):
        """Test handle_webhook exception path with error_code extraction."""
        # Patch confirm_payment to raise an exception
        with patch.object(iyzico_adapter, "confirm_payment") as mock_confirm:
            error = Exception("Connection timeout")
            error.error_code = "TIMEOUT_ERROR"
            mock_confirm.side_effect = error

            result = iyzico_adapter.handle_webhook({"token": "test_token"})

            assert result.success is False
            assert "Connection timeout" in result.error_message
            assert result.error_code == "TIMEOUT_ERROR"
