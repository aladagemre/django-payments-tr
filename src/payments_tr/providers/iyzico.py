"""
iyzico payment provider.

This provider wraps django-iyzico to provide a consistent interface
compatible with the payments-tr provider abstraction.

Requires: pip install django-payments-tr[iyzico]
"""

from __future__ import annotations

import logging
from typing import Any

from payments_tr.providers.base import (
    BuyerInfo,
    PaymentLike,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
)

logger = logging.getLogger(__name__)


class IyzicoProvider(PaymentProvider):
    """
    iyzico payment provider.

    This provider uses django-iyzico for the underlying implementation,
    providing a consistent interface for the payments-tr abstraction layer.

    Features:
        - Checkout form initialization (redirect-based flow)
        - 3D Secure payments
        - Installment payments
        - Refunds (full and partial)
        - Webhook/callback handling

    Example:
        >>> from payments_tr import get_payment_provider
        >>> provider = get_payment_provider("iyzico")
        >>> result = provider.create_payment(
        ...     payment,
        ...     callback_url="https://example.com/callback",
        ...     buyer_info={"email": "user@example.com"}
        ... )
        >>> if result.success:
        ...     redirect(result.checkout_url)
    """

    provider_name = "iyzico"

    def __init__(self) -> None:
        """Initialize the iyzico provider."""
        try:
            from django_iyzico import IyzicoClient  # type: ignore[attr-defined]

            self._client = IyzicoClient()
        except ImportError as e:
            raise ImportError(
                "django-iyzico is required for the iyzico provider. "
                "Install it with: pip install django-payments-tr[iyzico]"
            ) from e

    def create_payment(
        self,
        payment: PaymentLike,
        *,
        currency: str = "TRY",
        callback_url: str | None = None,
        buyer_info: BuyerInfo | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PaymentResult:
        """
        Create an iyzico checkout form session.

        This creates a checkout form token that redirects the user
        to iyzico's hosted payment page.

        Args:
            payment: Payment object with id, amount, currency
            currency: Currency code (default: TRY)
            callback_url: URL where iyzico redirects after payment (required)
            buyer_info: Buyer information (required by iyzico)
            **kwargs: Additional options:
                - installments: List of installment options (e.g., [1, 2, 3, 6])
                - basket_items: Custom basket items list
                - locale: Locale for checkout (default: "tr")

        Returns:
            PaymentResult with token and checkout_url
        """
        if not callback_url:
            return PaymentResult(
                success=False,
                error_message="callback_url is required for iyzico payments",
                error_code="MISSING_CALLBACK_URL",
            )

        # Convert buyer_info to BuyerInfo if dict
        if isinstance(buyer_info, dict):
            buyer_info = BuyerInfo.from_dict(buyer_info)
        elif buyer_info is None:
            # Try to extract from payment object
            buyer_info = self._extract_buyer_info(payment)

        try:
            # Build request data for django-iyzico
            order_data, buyer_dict, billing_address, basket_items = self._build_checkout_request(
                payment=payment,
                currency=currency,
                buyer_info=buyer_info,
                **kwargs,
            )

            installments = kwargs.get("installments", [1, 2, 3, 6, 9, 12])

            # Create checkout form via django-iyzico
            # Note: django-iyzico raises PaymentError on failure
            response = self._client.create_checkout_form(
                order_data=order_data,
                buyer=buyer_dict,
                billing_address=billing_address,
                basket_items=basket_items,
                callback_url=callback_url,
                enabled_installments=installments,
            )

            # If we get here, the response was successful
            token = response.token
            checkout_url = response.payment_page_url or response.checkout_form_content

            return PaymentResult(
                success=True,
                provider_payment_id=token,
                token=token,
                checkout_url=checkout_url,
                status="initialized",
                raw_response=response.to_dict(),
            )

        except Exception as e:
            # django-iyzico raises PaymentError on failure
            # Extract error details if available
            error_code = getattr(e, "error_code", None) or "IYZICO_ERROR"
            error_message = str(e)
            logger.error(f"iyzico checkout form creation failed: {error_message}")
            return PaymentResult(
                success=False,
                error_message=error_message,
                error_code=error_code,
            )

    def confirm_payment(self, provider_payment_id: str) -> PaymentResult:
        """
        Confirm an iyzico payment by retrieving the checkout form result.

        Args:
            provider_payment_id: The iyzico token from the checkout form

        Returns:
            PaymentResult with confirmation status
        """
        try:
            response = self._client.retrieve_checkout_form(provider_payment_id)

            # Response is a CheckoutFormResultResponse object
            if response.is_successful() and response.payment_status == "SUCCESS":
                return PaymentResult(
                    success=True,
                    provider_payment_id=response.payment_id,
                    status="succeeded",
                    raw_response=response.to_dict(),
                )
            else:
                error_message = response.error_message or "Payment not successful"
                return PaymentResult(
                    success=False,
                    error_message=error_message,
                    status=response.payment_status or "FAILURE",
                    raw_response=response.to_dict(),
                )

        except Exception as e:
            # Extract error details if available
            error_code = getattr(e, "error_code", None) or "IYZICO_ERROR"
            error_message = str(e)
            logger.error(f"iyzico error confirming payment: {error_message}")
            return PaymentResult(
                success=False,
                error_message=error_message,
                error_code=error_code,
            )

    def create_refund(
        self,
        payment: PaymentLike,
        amount: int | None = None,
        reason: str = "",
        **kwargs: Any,
    ) -> RefundResult:
        """
        Create an iyzico refund.

        Args:
            payment: Payment object (must have provider payment ID)
            amount: Amount to refund in kuruş, or None for full refund
            reason: Reason for refund
            **kwargs: Additional options:
                - provider_payment_id: Override payment ID from payment object
                - ip_address: IP address for refund request (required by iyzico)

        Returns:
            RefundResult with refund status
        """
        from decimal import Decimal

        # Get the iyzico payment ID from the payment object
        provider_payment_id = getattr(payment, "iyzico_payment_id", None)
        if not provider_payment_id:
            provider_payment_id = kwargs.get("provider_payment_id")

        if not provider_payment_id:
            return RefundResult(
                success=False,
                error_message="No iyzico payment ID found on payment object",
                error_code="MISSING_PAYMENT_ID",
            )

        # Get IP address for refund (required by iyzico)
        ip_address = kwargs.get("ip_address", "127.0.0.1")

        # Convert amount to Decimal for django-iyzico
        refund_amount = None
        if amount is not None:
            refund_amount = Decimal(str(amount)) / 100  # Convert kuruş to TRY

        try:
            # Note: django-iyzico raises PaymentError on failure
            response = self._client.refund_payment(
                payment_id=provider_payment_id,
                ip_address=ip_address,
                amount=refund_amount,
                reason=reason or None,
            )

            # If we get here, the refund was successful
            return RefundResult(
                success=True,
                provider_refund_id=response.refund_id,
                amount=amount or payment.amount,
                status="succeeded",
                raw_response=response.to_dict(),
            )

        except Exception as e:
            # django-iyzico raises PaymentError on failure
            # Extract error details if available
            error_code = getattr(e, "error_code", None) or "IYZICO_ERROR"
            error_message = str(e)
            logger.error(f"iyzico refund failed: {error_message}")
            return RefundResult(
                success=False,
                error_message=error_message,
                error_code=error_code,
            )

    def handle_webhook(
        self,
        payload: bytes | dict[str, Any],
        signature: str | None = None,
        **kwargs: Any,
    ) -> WebhookResult:
        """
        Handle an iyzico callback/webhook.

        iyzico uses callback URLs rather than webhooks. The callback
        is received after the user completes payment on iyzico's page.

        Args:
            payload: Callback data (as bytes or parsed dict in kwargs)
            signature: Not used by iyzico (no signature verification)
            **kwargs: Additional data including 'token'

        Returns:
            WebhookResult with event details
        """
        try:
            import json

            # Parse the callback data
            if isinstance(payload, bytes):
                data: dict[str, Any] = json.loads(payload.decode("utf-8"))
            else:
                data = payload

            token = data.get("token") or kwargs.get("token")

            if not token:
                return WebhookResult(
                    success=False,
                    error_message="No token in callback",
                )

            # Retrieve the payment result using the token
            confirm_result = self.confirm_payment(token)

            if confirm_result.success:
                return WebhookResult(
                    success=True,
                    event_type="payment.success",
                    provider_payment_id=confirm_result.provider_payment_id,
                    status="succeeded",
                )
            return WebhookResult(
                success=False,
                event_type="payment.failed",
                error_message=confirm_result.error_message,
            )

        except Exception as e:
            # Extract error details if available
            error_code = getattr(e, "error_code", None) or "IYZICO_ERROR"
            error_message = str(e)
            logger.error(f"iyzico error handling callback: {error_message}")
            return WebhookResult(
                success=False,
                error_message=error_message,
                error_code=error_code,
            )

    def get_payment_status(self, provider_payment_id: str) -> str:
        """Get the current status of a payment from iyzico."""
        result = self.confirm_payment(provider_payment_id)
        if result.success:
            return "succeeded"
        return result.status or "unknown"

    def supports_checkout_form(self) -> bool:
        """iyzico supports embedded checkout form content."""
        return True

    def supports_redirect(self) -> bool:
        """iyzico primarily uses redirect-based checkout."""
        return True

    def supports_installments(self) -> bool:
        """iyzico supports installment payments."""
        return True

    def _build_checkout_request(
        self,
        payment: PaymentLike,
        currency: str,
        buyer_info: BuyerInfo,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        """Build the checkout form request data components."""
        locale = kwargs.get("locale", "tr")
        basket_items = kwargs.get("basket_items")

        if not basket_items:
            basket_items = self._build_default_basket(payment)

        buyer_dict = buyer_info.to_dict()

        # Build order data
        order_data = {
            "locale": locale,
            "conversationId": str(payment.id),
            "price": str(payment.amount / 100),  # Convert kuruş to TRY string
            "paidPrice": str(payment.amount / 100),
            "currency": currency.upper(),
            "basketId": str(payment.id),
            "paymentGroup": "PRODUCT",
        }

        # Build billing address
        billing_address = {
            "address": buyer_dict.get("registrationAddress", "Address"),
            "city": buyer_dict.get("city", "Istanbul"),
            "country": buyer_dict.get("country", "Turkey"),
            "zipCode": buyer_dict.get("zipCode", "34000"),
        }

        return order_data, buyer_dict, billing_address, basket_items

    def _build_default_basket(self, payment: PaymentLike) -> list[dict[str, Any]]:
        """Build default basket items from payment."""
        return [
            {
                "id": str(payment.id),
                "name": "Payment",
                "category1": "Service",
                "itemType": "VIRTUAL",
                "price": str(payment.amount / 100),  # Convert kuruş to TRY string
            }
        ]

    def _extract_buyer_info(self, payment: PaymentLike) -> BuyerInfo:
        """Try to extract buyer info from payment object."""
        # Try to get client/user from payment
        if hasattr(payment, "client"):
            client = payment.client
            user = getattr(client, "user", client)

            # Parse name safely
            full_name = getattr(user, "name", "").strip()
            name_parts = full_name.split() if full_name else []

            return BuyerInfo(
                id=str(getattr(client, "id", "")),
                email=getattr(user, "email", ""),
                name=getattr(
                    user,
                    "first_name",
                    name_parts[0] if name_parts else "Customer",
                ),
                surname=getattr(
                    user,
                    "last_name",
                    name_parts[-1] if len(name_parts) > 1 else "Customer",
                ),
                phone=getattr(client, "phone", ""),
            )
        return BuyerInfo(email="customer@example.com")
