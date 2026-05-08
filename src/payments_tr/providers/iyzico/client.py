"""
Iyzico API client wrapper for Django.

This module provides a Django-friendly wrapper around the official iyzipay SDK,
handling configuration, error translation, and response normalization.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import iyzipay

from .exceptions import CardError, PaymentError, ThreeDSecureError, ValidationError
from .settings import iyzico_settings
from .utils import (
    extract_card_info,
    fingerprint_token,
    format_address_data,
    format_buyer_data,
    format_price,
    parse_iyzico_response,
    sanitize_log_data,
    validate_payment_data,
)

logger = logging.getLogger(__name__)


def _to_decimal(value: Any, *, field: str, item_index: int | None = None) -> Decimal:
    """
    Convert an Iyzico price-like value to ``Decimal``.

    Iyzico accepts both ``str`` and numeric forms in basket items. We normalise
    to ``Decimal`` so marketplace sum/per-item comparisons can't drift on
    floating-point arithmetic. ``ValidationError`` is raised on bad inputs to
    keep the call site free of try/except clutter.
    """
    where = f"basketItems[{item_index}].{field}" if item_index is not None else field
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as e:
        raise ValidationError(
            f"Invalid {where} value: {value!r}",
            error_code="INVALID_MARKETPLACE_PRICE",
        ) from e


def validate_marketplace_basket(
    basket_items: list[dict[str, Any]],
    paid_price: Any,
    *,
    strict: bool = False,
) -> None:
    """
    Validate marketplace (sub-merchant) routing on a checkout-form basket.

    Iyzico's marketplace flow ("işyeri gelir paylaşımı") splits each basket
    item between the platform and a sub-merchant via ``subMerchantKey`` /
    ``subMerchantPrice``. The two fields are required together on every item
    that is marketplace-routed; ``subMerchantPrice`` must not exceed the item
    ``price``; and the sum of all ``subMerchantPrice`` values must not exceed
    the order's ``paidPrice`` (otherwise the platform commission is negative).

    Args:
        basket_items: Basket items as posted to Iyzico. May contain a mix of
            marketplace-routed and platform-only items unless ``strict``.
        paid_price: Order-level ``paidPrice`` (string, Decimal, int, float).
        strict: When ``True`` (provider ``marketplace=True`` mode), every
            item MUST carry both marketplace fields. When ``False`` (default,
            client-level) a mixed basket is accepted — Iyzico keeps full
            revenue on the non-marketplace items.

    Raises:
        ValidationError: If any of the marketplace invariants are violated.
    """
    if not basket_items:
        return

    paid_price_decimal = _to_decimal(paid_price, field="paidPrice")
    sub_merchant_total = Decimal("0")
    seen_marketplace = False

    for index, item in enumerate(basket_items):
        sub_merchant_key = item.get("subMerchantKey")
        sub_merchant_price = item.get("subMerchantPrice")

        # Treat the empty string the same as missing — the bare iyzipay SDK
        # forwards it as "" and the gateway silently treats the item as
        # platform-only. We make that explicit so callers don't get a
        # surprise revenue share of zero on a typo'd seller key.
        has_key = sub_merchant_key is not None and sub_merchant_key != ""
        has_price = sub_merchant_price is not None and sub_merchant_price != ""

        if not has_key and not has_price:
            if strict:
                raise ValidationError(
                    f"basketItems[{index}] is missing subMerchantKey/"
                    "subMerchantPrice (marketplace=True requires every item "
                    "to be sub-merchant routed)",
                    error_code="MARKETPLACE_ITEM_MISSING_SUBMERCHANT",
                )
            continue

        if not has_key or not has_price:
            raise ValidationError(
                f"basketItems[{index}] must specify both subMerchantKey and "
                "subMerchantPrice together; received "
                f"key={'set' if has_key else 'missing'}, "
                f"price={'set' if has_price else 'missing'}",
                error_code="MARKETPLACE_FIELDS_INCOMPLETE",
            )

        # Empty/whitespace key — reject explicitly. The bare SDK silently
        # no-ops; we want a loud failure.
        if not str(sub_merchant_key).strip():
            raise ValidationError(
                f"basketItems[{index}].subMerchantKey is empty",
                error_code="MARKETPLACE_EMPTY_SUBMERCHANT_KEY",
            )

        seen_marketplace = True
        sub_merchant_value = _to_decimal(
            sub_merchant_price, field="subMerchantPrice", item_index=index
        )
        if sub_merchant_value < 0:
            raise ValidationError(
                f"basketItems[{index}].subMerchantPrice cannot be negative",
                error_code="MARKETPLACE_NEGATIVE_SUBMERCHANT_PRICE",
            )

        item_price = item.get("price")
        if item_price is None:
            raise ValidationError(
                f"basketItems[{index}].price is required for marketplace items",
                error_code="MARKETPLACE_ITEM_PRICE_MISSING",
            )
        item_price_decimal = _to_decimal(item_price, field="price", item_index=index)

        if sub_merchant_value > item_price_decimal:
            raise ValidationError(
                f"basketItems[{index}].subMerchantPrice ({sub_merchant_value}) "
                f"exceeds item price ({item_price_decimal})",
                error_code="MARKETPLACE_SUBMERCHANT_EXCEEDS_ITEM_PRICE",
            )

        sub_merchant_total += sub_merchant_value

    # Sum guard only matters once at least one item is marketplace-routed.
    if seen_marketplace and sub_merchant_total > paid_price_decimal:
        raise ValidationError(
            f"Sum of subMerchantPrice ({sub_merchant_total}) exceeds order "
            f"paidPrice ({paid_price_decimal}); platform commission would be "
            "negative",
            error_code="MARKETPLACE_SUBMERCHANT_SUM_EXCEEDS_PAID_PRICE",
        )


class BaseIyzicoResponse:
    """
    Base class for Iyzico API responses.

    Provides common functionality for parsing and accessing response data.
    Subclasses should extend this with response-type-specific properties.
    """

    def __init__(self, raw_response: Any):
        """
        Initialize response.

        Args:
            raw_response: Raw response from iyzipay SDK
        """
        self.raw_response = parse_iyzico_response(raw_response)
        self._status = self.raw_response.get("status")
        self._error_code = self.raw_response.get("errorCode")
        self._error_message = self.raw_response.get("errorMessage")

    def is_successful(self) -> bool:
        """Check if operation was successful."""
        return self._status == "success"

    @property
    def status(self) -> str:
        """Get response status."""
        return self._status or "failure"

    @property
    def error_code(self) -> str | None:
        """Get error code if operation failed."""
        return self._error_code

    @property
    def error_message(self) -> str | None:
        """Get error message if operation failed."""
        return self._error_message

    @property
    def error_group(self) -> str | None:
        """Get error group if operation failed."""
        return self.raw_response.get("errorGroup")

    @property
    def conversation_id(self) -> str | None:
        """Get conversation ID."""
        return self.raw_response.get("conversationId")

    @property
    def price(self) -> Decimal | None:
        """Get price/amount."""
        price_str = self.raw_response.get("price")
        if price_str:
            return Decimal(str(price_str))
        return None

    @property
    def currency(self) -> str | None:
        """Get currency code."""
        return self.raw_response.get("currency")

    def to_dict(self) -> dict[str, Any]:
        """Convert response to dictionary."""
        return self.raw_response


class PaymentResponse(BaseIyzicoResponse):
    """
    Wrapper for Iyzico payment response.

    Provides a consistent interface for accessing payment response data.
    Inherits common properties from BaseIyzicoResponse.
    """

    @property
    def payment_id(self) -> str | None:
        """Get Iyzico payment ID."""
        return self.raw_response.get("paymentId")

    @property
    def paid_price(self) -> Decimal | None:
        """Get paid price (may differ from price with installments)."""
        paid_price_str = self.raw_response.get("paidPrice")
        if paid_price_str:
            return Decimal(str(paid_price_str))
        return None

    @property
    def installment(self) -> int:
        """Get installment count."""
        return int(self.raw_response.get("installment", 1))

    @property
    def card_info(self) -> dict[str, str]:
        """Get safe card information."""
        return extract_card_info(self.raw_response)

    @property
    def buyer_email(self) -> str | None:
        """Get buyer email."""
        return self.raw_response.get("buyerEmail")

    @property
    def buyer_name(self) -> str | None:
        """Get buyer name."""
        return self.raw_response.get("buyerName")

    @property
    def buyer_surname(self) -> str | None:
        """Get buyer surname."""
        return self.raw_response.get("buyerSurname")

    def __str__(self) -> str:
        """String representation."""
        return f"PaymentResponse(status={self.status}, payment_id={self.payment_id})"

    def __repr__(self) -> str:
        """Developer representation."""
        return f"PaymentResponse({self.raw_response})"


class ThreeDSResponse(PaymentResponse):
    """
    Wrapper for 3D Secure payment response.

    Extends PaymentResponse with 3DS-specific fields.
    """

    @property
    def three_ds_html_content(self) -> str | None:
        """Get 3D Secure HTML content for rendering."""
        return self.raw_response.get("threeDSHtmlContent")

    @property
    def token(self) -> str | None:
        """Get payment token for 3D Secure callback."""
        return self.raw_response.get("token")


class RefundResponse(BaseIyzicoResponse):
    """
    Wrapper for Iyzico refund response.

    Provides a consistent interface for accessing refund response data.
    Inherits common properties from BaseIyzicoResponse.
    """

    @property
    def payment_id(self) -> str | None:
        """Get Iyzico payment ID."""
        return self.raw_response.get("paymentId")

    @property
    def refund_id(self) -> str | None:
        """Get Iyzico refund ID."""
        return self.raw_response.get("paymentTransactionId")

    @property
    def payment_transaction_id(self) -> str | None:
        """
        Get the item-level transaction ID this refund applied to.

        Marketplace refunds attribute the refund to a specific basket item's
        ``paymentTransactionId`` (which corresponds to one sub-merchant's
        share). This property exposes that identifier for callers that need
        to track per-item refund flow; for non-marketplace refunds Iyzico
        echoes the same ``paymentTransactionId`` that ``refund_id`` returns.
        """
        return self.raw_response.get("paymentTransactionId")

    def __str__(self) -> str:
        """String representation."""
        return (
            f"RefundResponse(status={self.status}, "
            f"payment_id={self.payment_id}, "
            f"refund_id={self.refund_id})"
        )

    def __repr__(self) -> str:
        """Developer representation."""
        return f"RefundResponse({self.raw_response})"


class CheckoutFormResponse(BaseIyzicoResponse):
    """
    Wrapper for Iyzico Checkout Form initialization response.

    Used when creating a checkout form that redirects users to iyzico's
    hosted payment page.
    """

    @property
    def token(self) -> str | None:
        """Get checkout form token."""
        return self.raw_response.get("token")

    @property
    def checkout_form_content(self) -> str | None:
        """Get checkout form HTML/JavaScript content for embedding."""
        return self.raw_response.get("checkoutFormContent")

    @property
    def payment_page_url(self) -> str | None:
        """Get direct URL to iyzico payment page."""
        return self.raw_response.get("paymentPageUrl")

    @property
    def token_expire_time(self) -> int | None:
        """Get token expiration time in seconds."""
        return self.raw_response.get("tokenExpireTime")

    def __str__(self) -> str:
        """String representation."""
        return f"CheckoutFormResponse(status={self.status}, token={fingerprint_token(self.token)})"

    def __repr__(self) -> str:
        """Developer representation."""
        return f"CheckoutFormResponse({self.raw_response})"


class CheckoutFormResultResponse(PaymentResponse):
    """
    Wrapper for Iyzico Checkout Form result retrieval response.

    Extends PaymentResponse with checkout-specific fields.
    Used after the user completes payment on iyzico's hosted page.
    """

    @property
    def token(self) -> str | None:
        """Get checkout form token."""
        return self.raw_response.get("token")

    @property
    def payment_status(self) -> str | None:
        """Get payment status from checkout form."""
        return self.raw_response.get("paymentStatus")

    @property
    def fraud_status(self) -> int | None:
        """Get fraud check status."""
        return self.raw_response.get("fraudStatus")

    @property
    def basket_id(self) -> str | None:
        """Get basket ID."""
        return self.raw_response.get("basketId")

    def __str__(self) -> str:
        """String representation."""
        return (
            f"CheckoutFormResultResponse(status={self.status}, "
            f"payment_id={self.payment_id}, "
            f"payment_status={self.payment_status})"
        )

    def __repr__(self) -> str:
        """Developer representation."""
        return f"CheckoutFormResultResponse({self.raw_response})"


class IyzicoClient:
    """
    Main client for interacting with Iyzico API.

    Wraps the official iyzipay SDK with Django-specific features:
    - Automatic settings loading from Django settings
    - Error translation to custom exceptions
    - Response normalization
    - Comprehensive logging
    - Type hints throughout
    """

    def __init__(self, settings=None):
        """
        Initialize Iyzico client.

        Args:
            settings: Optional IyzicoSettings instance. If None, uses global settings.
        """
        self.settings = settings or iyzico_settings
        self._options = None
        logger.debug("IyzicoClient initialized")

    def get_options(self) -> dict[str, str]:
        """
        Get Iyzico API options.

        Returns:
            Dictionary with api_key, secret_key, and base_url

        Note:
            Options are cached after first call for performance.
        """
        if self._options is None:
            self._options = self.settings.get_options()
            logger.debug(f"Loaded Iyzico options (base_url={self._options['base_url']})")
        return self._options

    def create_payment(
        self,
        order_data: dict[str, Any],
        payment_card: dict[str, Any],
        buyer: dict[str, Any],
        billing_address: dict[str, Any],
        shipping_address: dict[str, Any] | None = None,
        basket_items: list[dict[str, Any]] | None = None,
    ) -> PaymentResponse:
        """
        Create a direct payment (non-3D Secure).

        Args:
            order_data: Order information (price, paidPrice, currency, etc.)
            payment_card: Card information (cardHolderName, cardNumber, etc.)
            buyer: Buyer information (name, email, address, etc.)
            billing_address: Billing address information
            shipping_address: Shipping address (optional, defaults to billing)
            basket_items: Basket items (optional)

        Returns:
            PaymentResponse with payment result

        Raises:
            ValidationError: If input data is invalid
            PaymentError: If payment fails
            CardError: If card is invalid

        Example:
            >>> client = IyzicoClient()
            >>> response = client.create_payment(
            ...     order_data={'price': '100.00', 'paidPrice': '100.00', ...},
            ...     payment_card={'cardNumber': '5528790000000008', ...},
            ...     buyer={'name': 'John', 'surname': 'Doe', ...},
            ...     billing_address={'address': '...', 'city': 'Istanbul', ...}
            ... )
            >>> if response.is_successful():
            ...     print(f"Payment ID: {response.payment_id}")
        """
        # Validate order data
        validate_payment_data(order_data)

        # Format addresses
        if shipping_address is None:
            shipping_address = billing_address

        # Get buyer name for address contact
        buyer_full_name = f"{buyer.get('name', '')} {buyer.get('surname', '')}".strip()

        # Build request data
        request_data = {
            "locale": order_data.get("locale", self.settings.locale),
            "conversationId": order_data.get("conversationId"),
            "price": format_price(order_data["price"]),
            "paidPrice": format_price(order_data["paidPrice"]),
            "currency": order_data.get("currency", self.settings.currency),
            "installment": order_data.get("installment", 1),
            "basketId": order_data.get("basketId"),
            "paymentChannel": order_data.get("paymentChannel", "WEB"),
            "paymentGroup": order_data.get("paymentGroup", "PRODUCT"),
            "paymentCard": payment_card,
            "buyer": format_buyer_data(buyer),
            "shippingAddress": format_address_data(shipping_address, buyer_full_name),
            "billingAddress": format_address_data(billing_address, buyer_full_name),
        }

        # Add basket items if provided
        if basket_items:
            request_data["basketItems"] = basket_items

        # Log request (sanitized)
        logger.info(
            f"Creating payment - conversation_id={request_data['conversationId']}, "
            f"amount={request_data['price']} {request_data['currency']}"
        )
        logger.debug(f"Payment request: {sanitize_log_data(request_data)}")

        try:
            # Call Iyzico API
            payment = iyzipay.Payment()
            raw_response = payment.create(request_data, self.get_options())

            # Parse and wrap response
            response = PaymentResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(
                    f"Payment successful - payment_id={response.payment_id}, "
                    f"conversation_id={response.conversation_id}"
                )
            else:
                logger.warning(
                    f"Payment failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}, "
                    f"conversation_id={response.conversation_id}"
                )

                # Translate to appropriate exception
                self._handle_payment_error(response)

            return response

        except (ValidationError, PaymentError, CardError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Payment creation failed: {str(e)}", exc_info=True)
            raise PaymentError(
                f"Payment creation failed: {str(e)}",
                error_code="PAYMENT_CREATION_ERROR",
            ) from e

    def create_3ds_payment(
        self,
        order_data: dict[str, Any],
        payment_card: dict[str, Any],
        buyer: dict[str, Any],
        billing_address: dict[str, Any],
        shipping_address: dict[str, Any] | None = None,
        basket_items: list[dict[str, Any]] | None = None,
        callback_url: str | None = None,
    ) -> ThreeDSResponse:
        """
        Initialize 3D Secure payment flow.

        Args:
            order_data: Order information
            payment_card: Card information
            buyer: Buyer information
            billing_address: Billing address
            shipping_address: Shipping address (optional)
            basket_items: Basket items (optional)
            callback_url: 3DS callback URL (optional, uses settings default)

        Returns:
            ThreeDSResponse with HTML content to display to user

        Raises:
            ValidationError: If input data is invalid
            ThreeDSecureError: If 3DS initialization fails

        Example:
            >>> client = IyzicoClient()
            >>> response = client.create_3ds_payment(
            ...     order_data={...},
            ...     payment_card={...},
            ...     buyer={...},
            ...     billing_address={...},
            ...     callback_url='https://mysite.com/payment/callback/'
            ... )
            >>> if response.is_successful():
            ...     html = response.three_ds_html_content
            ...     # Display HTML to user for 3DS authentication
        """
        # Validate order data
        validate_payment_data(order_data)

        # Get callback URL
        if callback_url is None:
            callback_url = self.settings.callback_url

        # Format addresses
        if shipping_address is None:
            shipping_address = billing_address

        buyer_full_name = f"{buyer.get('name', '')} {buyer.get('surname', '')}".strip()

        # Build request data
        request_data = {
            "locale": order_data.get("locale", self.settings.locale),
            "conversationId": order_data.get("conversationId"),
            "price": format_price(order_data["price"]),
            "paidPrice": format_price(order_data["paidPrice"]),
            "currency": order_data.get("currency", self.settings.currency),
            "installment": order_data.get("installment", 1),
            "basketId": order_data.get("basketId"),
            "paymentChannel": order_data.get("paymentChannel", "WEB"),
            "paymentGroup": order_data.get("paymentGroup", "PRODUCT"),
            "paymentCard": payment_card,
            "buyer": format_buyer_data(buyer),
            "shippingAddress": format_address_data(shipping_address, buyer_full_name),
            "billingAddress": format_address_data(billing_address, buyer_full_name),
            "callbackUrl": callback_url,
        }

        # Add basket items if provided
        if basket_items:
            request_data["basketItems"] = basket_items

        # Log request
        logger.info(
            f"Initiating 3DS payment - conversation_id={request_data['conversationId']}, "
            f"amount={request_data['price']} {request_data['currency']}"
        )
        logger.debug(f"3DS request: {sanitize_log_data(request_data)}")

        try:
            # Call Iyzico 3DS API
            three_ds_payment = iyzipay.ThreedsInitialize()
            raw_response = three_ds_payment.create(request_data, self.get_options())

            # Parse and wrap response
            response = ThreeDSResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(f"3DS initialized - conversation_id={response.conversation_id}")
            else:
                logger.warning(
                    f"3DS initialization failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}"
                )

                raise ThreeDSecureError(
                    response.error_message or "3D Secure initialization failed",
                    error_code=response.error_code,
                    error_group=response.error_group,
                )

            return response

        except ThreeDSecureError:
            raise
        except Exception as e:
            logger.error(f"3DS initialization failed: {str(e)}", exc_info=True)
            raise ThreeDSecureError(
                f"3D Secure initialization failed: {str(e)}",
                error_code="THREEDS_INIT_ERROR",
            ) from e

    def complete_3ds_payment(self, token: str) -> PaymentResponse:
        """
        Complete 3D Secure payment after user authentication.

        This is called in the callback handler after the user completes
        3D Secure authentication.

        Args:
            token: Payment token from 3DS callback

        Returns:
            PaymentResponse with final payment result

        Raises:
            ThreeDSecureError: If payment completion fails
            ValidationError: If token is invalid

        Example:
            >>> client = IyzicoClient()
            >>> # In callback view:
            >>> token = request.GET.get('token')
            >>> response = client.complete_3ds_payment(token)
            >>> if response.is_successful():
            ...     # Payment completed successfully
            ...     pass
        """
        if not token:
            raise ValidationError(
                "Payment token is required",
                error_code="MISSING_TOKEN",
            )

        logger.info(f"Completing 3DS payment - token={fingerprint_token(token)}")

        try:
            # Call Iyzico 3DS completion API
            request_data = {"paymentId": token}
            three_ds_payment = iyzipay.ThreedsPayment()
            raw_response = three_ds_payment.create(request_data, self.get_options())

            # Parse and wrap response
            response = PaymentResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(
                    f"3DS payment completed - payment_id={response.payment_id}, "
                    f"conversation_id={response.conversation_id}"
                )
            else:
                logger.warning(
                    f"3DS payment failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}"
                )

                raise ThreeDSecureError(
                    response.error_message or "3D Secure payment failed",
                    error_code=response.error_code,
                    error_group=response.error_group,
                )

            return response

        except ThreeDSecureError:
            raise
        except Exception as e:
            logger.error(f"3DS payment completion failed: {str(e)}", exc_info=True)
            raise ThreeDSecureError(
                f"3D Secure payment completion failed: {str(e)}",
                error_code="THREEDS_COMPLETION_ERROR",
            ) from e

    def create_checkout_form(
        self,
        order_data: dict[str, Any],
        buyer: dict[str, Any],
        billing_address: dict[str, Any],
        shipping_address: dict[str, Any] | None = None,
        basket_items: list[dict[str, Any]] | None = None,
        callback_url: str | None = None,
        enabled_installments: list[int] | None = None,
        marketplace: bool = False,
    ) -> CheckoutFormResponse:
        """
        Create a checkout form for redirect-based payment.

        This creates a hosted payment page on iyzico where users enter their
        card details. No card data touches your server (PCI DSS compliant).

        Args:
            order_data: Order information (price, paidPrice, currency, basketId, etc.)
            buyer: Buyer information (name, email, address, etc.)
            billing_address: Billing address information
            shipping_address: Shipping address (optional, defaults to billing)
            basket_items: Basket items (optional)
            callback_url: URL where iyzico redirects after payment
            enabled_installments: List of installment options (e.g., [1, 2, 3, 6, 9, 12])
            marketplace: When ``True`` enables strict marketplace mode —
                every basket item must carry both ``subMerchantKey`` and
                ``subMerchantPrice``. When ``False`` (default), marketplace
                routing is detected per-item and validated only for those
                items; mixed baskets are accepted (Iyzico keeps full revenue
                on the platform-only items).

        Returns:
            CheckoutFormResponse with token and checkout form content/URL

        Raises:
            ValidationError: If input data is invalid
            PaymentError: If checkout form creation fails

        Example:
            >>> client = IyzicoClient()
            >>> response = client.create_checkout_form(
            ...     order_data={
            ...         'price': '100.00',
            ...         'paidPrice': '100.00',
            ...         'basketId': 'order-123',
            ...     },
            ...     buyer={
            ...         'id': 'user-1',
            ...         'name': 'John',
            ...         'surname': 'Doe',
            ...         'email': 'john@example.com',
            ...         'identityNumber': '11111111111',
            ...         'registrationAddress': 'Address',
            ...         'city': 'Istanbul',
            ...         'country': 'Turkey',
            ...         'ip': '192.168.1.1',
            ...     },
            ...     billing_address={...},
            ...     callback_url='https://mysite.com/payment/callback/',
            ... )
            >>> if response.is_successful():
            ...     # Option 1: Embed checkout form
            ...     html = response.checkout_form_content
            ...     # Option 2: Redirect to payment page
            ...     redirect_url = response.payment_page_url
        """
        # Validate order data
        validate_payment_data(order_data)

        # Get callback URL
        if callback_url is None:
            callback_url = self.settings.callback_url

        # Format addresses
        if shipping_address is None:
            shipping_address = billing_address

        buyer_full_name = f"{buyer.get('name', '')} {buyer.get('surname', '')}".strip()

        # Default installments if not specified
        if enabled_installments is None:
            enabled_installments = [1, 2, 3, 6, 9, 12]

        # Build request data
        request_data = {
            "locale": order_data.get("locale", self.settings.locale),
            "conversationId": order_data.get("conversationId"),
            "price": format_price(order_data["price"]),
            "paidPrice": format_price(order_data["paidPrice"]),
            "currency": order_data.get("currency", self.settings.currency),
            "basketId": order_data.get("basketId"),
            "paymentGroup": order_data.get("paymentGroup", "PRODUCT"),
            "callbackUrl": callback_url,
            "enabledInstallments": [str(i) for i in enabled_installments],
            "buyer": format_buyer_data(buyer),
            "shippingAddress": format_address_data(shipping_address, buyer_full_name),
            "billingAddress": format_address_data(billing_address, buyer_full_name),
        }

        # Add basket items if provided
        if basket_items:
            # Marketplace validation runs even when ``marketplace=False`` so
            # that any item carrying sub-merchant fields is still checked
            # for the per-item / sum invariants. Strict mode escalates the
            # check to "every item must be marketplace-routed".
            validate_marketplace_basket(basket_items, request_data["paidPrice"], strict=marketplace)
            request_data["basketItems"] = basket_items
        elif marketplace:
            # We deliberately refuse to fall back to a synthetic single-item
            # basket in marketplace mode — there is no sensible default
            # ``subMerchantKey`` to invent, and silently routing 100% of
            # revenue to the platform would violate the caller's intent.
            raise ValidationError(
                "marketplace=True requires explicit basket_items with "
                "sub-merchant fields; the default single-item fallback is "
                "rejected to prevent accidental platform-only routing.",
                error_code="MARKETPLACE_REQUIRES_BASKET_ITEMS",
            )

        # Log request
        logger.info(
            f"Creating checkout form - conversation_id={request_data.get('conversationId')}, "
            f"amount={request_data['price']} {request_data['currency']}"
        )
        logger.debug(f"Checkout form request: {sanitize_log_data(request_data)}")

        try:
            # Call Iyzico Checkout Form Initialize API
            checkout_form = iyzipay.CheckoutFormInitialize()
            raw_response = checkout_form.create(request_data, self.get_options())

            # Parse and wrap response
            response = CheckoutFormResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(
                    f"Checkout form created - token={fingerprint_token(response.token)}, "
                    f"conversation_id={response.conversation_id}"
                )
            else:
                logger.warning(
                    f"Checkout form creation failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}"
                )

                raise PaymentError(
                    response.error_message or "Checkout form creation failed",
                    error_code=response.error_code,
                    error_group=response.error_group,
                )

            return response

        except PaymentError:
            raise
        except Exception as e:
            logger.error(f"Checkout form creation failed: {str(e)}", exc_info=True)
            raise PaymentError(
                f"Checkout form creation failed: {str(e)}",
                error_code="CHECKOUT_FORM_ERROR",
            ) from e

    def retrieve_checkout_form(self, token: str) -> CheckoutFormResultResponse:
        """
        Retrieve checkout form result after user completes payment.

        This is called in the callback handler after the user completes
        payment on iyzico's hosted page.

        Args:
            token: Checkout form token from callback

        Returns:
            CheckoutFormResultResponse with payment result

        Raises:
            PaymentError: If retrieval fails
            ValidationError: If token is missing

        Example:
            >>> client = IyzicoClient()
            >>> # In callback view:
            >>> token = request.POST.get('token')
            >>> response = client.retrieve_checkout_form(token)
            >>> if response.is_successful() and response.payment_status == 'SUCCESS':
            ...     # Payment completed successfully
            ...     payment_id = response.payment_id
        """
        if not token:
            raise ValidationError(
                "Checkout form token is required",
                error_code="MISSING_TOKEN",
            )

        logger.info(f"Retrieving checkout form result - token={fingerprint_token(token)}")

        try:
            # Call Iyzico Checkout Form Retrieve API
            request_data = {"token": token}
            checkout_form = iyzipay.CheckoutForm()
            raw_response = checkout_form.retrieve(request_data, self.get_options())

            # Parse and wrap response
            response = CheckoutFormResultResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(
                    f"Checkout form result retrieved - payment_id={response.payment_id}, "
                    f"payment_status={response.payment_status}, "
                    f"conversation_id={response.conversation_id}"
                )
            else:
                logger.warning(
                    f"Checkout form retrieval failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}"
                )

            return response

        except Exception as e:
            logger.error(f"Checkout form retrieval failed: {str(e)}", exc_info=True)
            raise PaymentError(
                f"Checkout form retrieval failed: {str(e)}",
                error_code="CHECKOUT_FORM_RETRIEVE_ERROR",
            ) from e

    def refund_payment(
        self,
        payment_id: str,
        ip_address: str,
        amount: Decimal | None = None,
        reason: str | None = None,
        payment_transaction_id: str | None = None,
    ) -> RefundResponse:
        """
        Refund a payment through Iyzico.

        Args:
            payment_id: Iyzico payment ID to refund. For non-marketplace
                payments this is the only identifier needed.
            ip_address: IP address initiating the refund (required for audit)
            amount: Amount to refund (None for full refund)
            reason: Optional refund reason
            payment_transaction_id: Item-level transaction ID. Required for
                attributing a marketplace refund to the correct
                sub-merchant share (refunds the seller's portion, not the
                platform commission). When provided, Iyzico is called with
                this value as ``paymentTransactionId``; otherwise we fall
                back to ``payment_id`` for backward compatibility with
                non-marketplace flows.

        Returns:
            RefundResponse object

        Raises:
            PaymentError: If refund fails
            ValidationError: If payment_id is missing

        Example:
            >>> client = IyzicoClient()
            >>> # Full refund
            >>> response = client.refund_payment("payment-123", ip_address="192.168.1.1")
            >>> if response.is_successful():
            ...     print(f"Refund ID: {response.refund_id}")
            >>> # Partial refund
            >>> response = client.refund_payment(
            ...     "payment-123",
            ...     ip_address="192.168.1.1",
            ...     amount=Decimal("50.00"),
            ...     reason="Customer requested partial refund"
            ... )
        """
        if not payment_id:
            raise ValidationError(
                "Payment ID is required for refund",
                error_code="MISSING_PAYMENT_ID",
            )

        if not ip_address:
            raise ValidationError(
                "IP address is required for refund operations",
                error_code="MISSING_IP_ADDRESS",
            )

        # Validate IP address format
        import ipaddress as ip_lib

        try:
            ip_lib.ip_address(ip_address)
        except ValueError as e:
            raise ValidationError(
                f"Invalid IP address format: {ip_address}",
                error_code="INVALID_IP_ADDRESS",
            ) from e

        # Build request data — prefer item-level transaction id when given
        # (marketplace flows), otherwise fall back to the order-level id
        # for backward compatibility with non-marketplace payments.
        refund_target = payment_transaction_id or payment_id
        request_data = {
            "paymentTransactionId": refund_target,
            "ip": ip_address,
        }

        # Add amount for partial refund
        if amount is not None:
            request_data["price"] = format_price(amount)
            logger.info(
                f"Initiating partial refund - payment_id={payment_id}, "
                f"transaction_id={payment_transaction_id or '(same as payment_id)'}, "
                f"amount={amount}"
            )
        else:
            logger.info(
                f"Initiating full refund - payment_id={payment_id}, "
                f"transaction_id={payment_transaction_id or '(same as payment_id)'}"
            )

        # Add reason if provided
        if reason:
            request_data["description"] = reason
            logger.debug(f"Refund reason: {reason}")

        try:
            # Call Iyzico Refund API
            refund = iyzipay.Refund()
            raw_response = refund.create(request_data, self.get_options())

            # Parse and wrap response
            response = RefundResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(
                    f"Refund successful - refund_id={response.refund_id}, "
                    f"payment_id={response.payment_id}, "
                    f"amount={response.price}"
                )
            else:
                logger.warning(
                    f"Refund failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}, "
                    f"payment_id={payment_id}"
                )

                raise PaymentError(
                    response.error_message or "Refund failed",
                    error_code=response.error_code,
                    error_group=response.error_group,
                )

            return response

        except PaymentError:
            raise
        except Exception as e:
            logger.error(f"Refund request failed: {str(e)}", exc_info=True)
            raise PaymentError(
                f"Refund request failed: {str(e)}",
                error_code="REFUND_ERROR",
            ) from e

    def register_card(
        self,
        card_info: dict[str, Any],
        buyer: dict[str, Any],
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Register a card with Iyzico for future payments.

        Stores card securely with Iyzico and returns tokens for recurring payments.
        NEVER stores actual card numbers - only Iyzico tokens are returned.

        Args:
            card_info: Card information (cardHolderName, cardNumber, expireMonth, expireYear, cvc)
            buyer: Buyer information (name, surname, email, identityNumber, etc.)
            external_id: Optional external user ID for card storage

        Returns:
            Dict with card_token, card_user_key, and card details

        Raises:
            CardError: If card registration fails
            ValidationError: If input data is invalid

        Example:
            >>> client = IyzicoClient()
            >>> result = client.register_card(
            ...     card_info={
            ...         'cardHolderName': 'John Doe',
            ...         'cardNumber': '5528790000000008',
            ...         'expireMonth': '12',
            ...         'expireYear': '2030',
            ...         'cvc': '123',
            ...     },
            ...     buyer={
            ...         'id': str(user.id),
            ...         'name': 'John',
            ...         'surname': 'Doe',
            ...         'email': 'john@example.com',
            ...         'identityNumber': '11111111111',
            ...         'registrationAddress': 'Address',
            ...         'city': 'Istanbul',
            ...         'country': 'Turkey',
            ...         'ip': request.META.get('REMOTE_ADDR'),
            ...     },
            ... )
            >>> # Store returned tokens in database
            >>> card_token = result['card_token']
            >>> card_user_key = result['card_user_key']
        """
        # Build request data
        request_data = {
            "locale": self.settings.locale,
            "conversationId": external_id or f"card-reg-{buyer.get('id', 'unknown')}",
            "email": buyer.get("email"),
            "externalId": external_id or buyer.get("id"),
            "card": {
                "cardAlias": card_info.get("cardAlias", "My Card"),
                "cardHolderName": card_info["cardHolderName"],
                "cardNumber": card_info["cardNumber"],
                "expireMonth": card_info["expireMonth"],
                "expireYear": card_info["expireYear"],
            },
        }

        logger.info("Registering card for user")

        try:
            # Call Iyzico Card Storage API
            card = iyzipay.Card()
            raw_response = card.create(request_data, self.get_options())

            # Parse response
            response_dict = parse_iyzico_response(raw_response)
            status = response_dict.get("status")

            if status != "success":
                error_code = response_dict.get("errorCode")
                error_message = response_dict.get("errorMessage", "Card registration failed")

                logger.warning(
                    f"Card registration failed - error_code={error_code}, "
                    f"error_message={error_message}"
                )

                raise CardError(
                    error_message,
                    error_code=error_code,
                    error_group=response_dict.get("errorGroup"),
                )

            # Extract card token and details
            card_token = response_dict.get("cardToken")
            card_user_key = response_dict.get("cardUserKey")
            card_alias = response_dict.get("cardAlias")
            bin_number = response_dict.get("binNumber")
            last_four_digits = response_dict.get("lastFourDigits")
            card_type = response_dict.get("cardType")
            card_association = response_dict.get("cardAssociation")
            card_family = response_dict.get("cardFamily")
            card_bank_name = response_dict.get("cardBankName")
            card_bank_code = response_dict.get("cardBankCode")

            logger.info(
                f"Card registered successfully - last_four={last_four_digits}, "
                f"card_association={card_association}"
            )

            return {
                "card_token": card_token,
                "card_user_key": card_user_key,
                "card_alias": card_alias,
                "bin_number": bin_number,
                "last_four_digits": last_four_digits,
                "card_type": card_type,
                "card_association": card_association,
                "card_family": card_family,
                "card_bank_name": card_bank_name,
                "card_bank_code": card_bank_code,
                "card_holder_name": card_info["cardHolderName"],
                "expiry_month": card_info["expireMonth"],
                "expiry_year": card_info["expireYear"],
            }

        except CardError:
            raise
        except Exception as e:
            logger.error(f"Card registration failed: {str(e)}", exc_info=True)
            raise CardError(
                f"Card registration failed: {str(e)}",
                error_code="CARD_REGISTRATION_ERROR",
            ) from e

    def delete_card(
        self,
        card_token: str,
        card_user_key: str,
    ) -> bool:
        """
        Delete a stored card from Iyzico.

        Args:
            card_token: Iyzico card token to delete
            card_user_key: Iyzico user key associated with the card

        Returns:
            True if deletion was successful

        Raises:
            CardError: If card deletion fails
            ValidationError: If tokens are missing

        Example:
            >>> client = IyzicoClient()
            >>> client.delete_card(
            ...     card_token=payment_method.card_token,
            ...     card_user_key=payment_method.card_user_key,
            ... )
        """
        if not card_token:
            raise ValidationError(
                "Card token is required for deletion",
                error_code="MISSING_CARD_TOKEN",
            )

        if not card_user_key:
            raise ValidationError(
                "Card user key is required for deletion",
                error_code="MISSING_CARD_USER_KEY",
            )

        # Build request data
        request_data = {
            "locale": self.settings.locale,
            "cardToken": card_token,
            "cardUserKey": card_user_key,
        }

        logger.info("Deleting card from Iyzico")

        try:
            # Call Iyzico Card Deletion API
            card = iyzipay.Card()
            raw_response = card.delete(request_data, self.get_options())

            # Parse response
            response_dict = parse_iyzico_response(raw_response)
            status = response_dict.get("status")

            if status != "success":
                error_code = response_dict.get("errorCode")
                error_message = response_dict.get("errorMessage", "Card deletion failed")

                logger.warning(
                    f"Card deletion failed - error_code={error_code}, error_message={error_message}"
                )

                raise CardError(
                    error_message,
                    error_code=error_code,
                    error_group=response_dict.get("errorGroup"),
                )

            logger.info("Card deleted successfully from Iyzico")
            return True

        except CardError:
            raise
        except Exception as e:
            logger.error(f"Card deletion failed: {str(e)}", exc_info=True)
            raise CardError(
                f"Card deletion failed: {str(e)}",
                error_code="CARD_DELETION_ERROR",
            ) from e

    def create_payment_with_token(
        self,
        order_data: dict[str, Any],
        card_token: str,
        card_user_key: str,
        buyer: dict[str, Any],
        billing_address: dict[str, Any],
        shipping_address: dict[str, Any] | None = None,
        basket_items: list[dict[str, Any]] | None = None,
    ) -> PaymentResponse:
        """
        Create a payment using a stored card token (for recurring payments).

        Args:
            order_data: Order information (price, paidPrice, currency, etc.)
            card_token: Iyzico card token
            card_user_key: Iyzico user key
            buyer: Buyer information
            billing_address: Billing address information
            shipping_address: Shipping address (optional, defaults to billing)
            basket_items: Basket items (optional)

        Returns:
            PaymentResponse with payment result

        Raises:
            ValidationError: If input data is invalid
            PaymentError: If payment fails
            CardError: If card is invalid

        Example:
            >>> client = IyzicoClient()
            >>> payment_method = PaymentMethod.get_default_for_user(user)
            >>> response = client.create_payment_with_token(
            ...     order_data={'price': '100.00', 'paidPrice': '100.00', ...},
            ...     card_token=payment_method.card_token,
            ...     card_user_key=payment_method.card_user_key,
            ...     buyer={'name': 'John', 'surname': 'Doe', ...},
            ...     billing_address={'address': '...', 'city': 'Istanbul', ...}
            ... )
        """
        # Validate order data
        validate_payment_data(order_data)

        # Format addresses
        if shipping_address is None:
            shipping_address = billing_address

        buyer_full_name = f"{buyer.get('name', '')} {buyer.get('surname', '')}".strip()

        # Build request data (similar to create_payment but with card token)
        request_data = {
            "locale": order_data.get("locale", self.settings.locale),
            "conversationId": order_data.get("conversationId"),
            "price": format_price(order_data["price"]),
            "paidPrice": format_price(order_data["paidPrice"]),
            "currency": order_data.get("currency", self.settings.currency),
            "installment": order_data.get("installment", 1),
            "basketId": order_data.get("basketId"),
            "paymentChannel": order_data.get("paymentChannel", "WEB"),
            "paymentGroup": order_data.get("paymentGroup", "SUBSCRIPTION"),
            "paymentCard": {
                "cardToken": card_token,
                "cardUserKey": card_user_key,
            },
            "buyer": format_buyer_data(buyer),
            "shippingAddress": format_address_data(shipping_address, buyer_full_name),
            "billingAddress": format_address_data(billing_address, buyer_full_name),
        }

        # Add basket items if provided
        if basket_items:
            request_data["basketItems"] = basket_items

        # Log request (sanitized)
        logger.info(
            f"Creating payment with token - conversation_id={request_data['conversationId']}, "
            f"amount={request_data['price']} {request_data['currency']}"
        )
        logger.debug(f"Payment request: {sanitize_log_data(request_data)}")

        try:
            # Call Iyzico API
            payment = iyzipay.Payment()
            raw_response = payment.create(request_data, self.get_options())

            # Parse and wrap response
            response = PaymentResponse(raw_response)

            # Log response
            if response.is_successful():
                logger.info(
                    f"Token payment successful - payment_id={response.payment_id}, "
                    f"conversation_id={response.conversation_id}"
                )
            else:
                logger.warning(
                    f"Token payment failed - error_code={response.error_code}, "
                    f"error_message={response.error_message}, "
                    f"conversation_id={response.conversation_id}"
                )

                # Translate to appropriate exception
                self._handle_payment_error(response)

            return response

        except (ValidationError, PaymentError, CardError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Token payment creation failed: {str(e)}", exc_info=True)
            raise PaymentError(
                f"Token payment creation failed: {str(e)}",
                error_code="TOKEN_PAYMENT_ERROR",
            ) from e

    def _handle_payment_error(self, response: PaymentResponse) -> None:
        """
        Translate Iyzico error to appropriate exception.

        Args:
            response: Payment response with error

        Raises:
            CardError: For card-related errors
            PaymentError: For other payment errors
        """
        error_code = response.error_code or ""
        error_message = response.error_message or "Payment failed"

        # Card-related errors
        card_error_codes = [
            "5001",  # Card number invalid
            "5002",  # CVC invalid
            "5003",  # Expiry date invalid
            "5004",  # Card holder name invalid
            "5006",  # Card declined
            "5008",  # Insufficient funds
            "5015",  # Card blocked
        ]

        if any(code in error_code for code in card_error_codes):
            raise CardError(
                error_message,
                error_code=error_code,
                error_group=response.error_group,
            )

        # General payment error
        raise PaymentError(
            error_message,
            error_code=error_code,
            error_group=response.error_group,
        )
