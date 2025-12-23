"""
Abstract base class and data structures for payment providers.

This module defines the interface that all payment providers must implement,
ensuring consistent behavior across different payment gateways.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PaymentLike(Protocol):
    """
    Protocol for payment objects.

    Any object with these attributes can be used with payment providers.
    This allows flexibility in how projects define their Payment models.
    """

    id: int | str
    amount: int  # Amount in smallest currency unit (e.g., kuruş)
    currency: str


@runtime_checkable
class PaymentWithClient(Protocol):
    """Extended payment protocol with client information."""

    id: int | str
    amount: int
    currency: str

    @property
    def client(self) -> Any:
        """Client/customer associated with the payment."""
        ...


@dataclass(frozen=True, slots=True)
class PaymentResult:
    """
    Result of a payment creation or confirmation operation.

    This is an immutable dataclass that represents the outcome of
    interacting with a payment provider.

    Attributes:
        success: Whether the operation was successful
        provider_payment_id: The provider's unique payment/transaction ID
        client_secret: Secret for client-side confirmation (Stripe)
        checkout_url: URL to redirect user for payment (iyzico)
        token: Token for checkout form (iyzico)
        status: Current payment status string
        error_message: Error message if operation failed
        error_code: Provider-specific error code
        raw_response: Full response from provider for debugging
    """

    success: bool
    provider_payment_id: str | None = None
    client_secret: str | None = None
    checkout_url: str | None = None
    token: str | None = None
    status: str = ""
    error_message: str | None = None
    error_code: str | None = None
    raw_response: dict[str, Any] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "provider_payment_id": self.provider_payment_id,
            "client_secret": self.client_secret,
            "checkout_url": self.checkout_url,
            "token": self.token,
            "status": self.status,
            "error_message": self.error_message,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class RefundResult:
    """
    Result of a refund operation.

    Attributes:
        success: Whether the refund was successful
        provider_refund_id: The provider's unique refund ID
        amount: Refunded amount in smallest currency unit
        status: Current refund status
        error_message: Error message if refund failed
        error_code: Provider-specific error code
        raw_response: Full response from provider for debugging
    """

    success: bool
    provider_refund_id: str | None = None
    amount: int | None = None
    status: str = ""
    error_message: str | None = None
    error_code: str | None = None
    raw_response: dict[str, Any] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "provider_refund_id": self.provider_refund_id,
            "amount": self.amount,
            "status": self.status,
            "error_message": self.error_message,
            "error_code": self.error_code,
        }


@dataclass(frozen=True, slots=True)
class WebhookResult:
    """
    Result of webhook/callback processing.

    Attributes:
        success: Whether the webhook was processed successfully
        event_type: Type of event (e.g., 'payment.succeeded', 'refund.created')
        payment_id: Associated payment ID from your system
        provider_payment_id: Provider's payment ID
        status: Resulting payment status
        error_message: Error message if processing failed
        error_code: Error code if processing failed
        should_retry: Whether the webhook should be retried
    """

    success: bool
    event_type: str = ""
    payment_id: int | str | None = None
    provider_payment_id: str | None = None
    status: str = ""
    error_message: str | None = None
    error_code: str | None = None
    should_retry: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "event_type": self.event_type,
            "payment_id": self.payment_id,
            "provider_payment_id": self.provider_payment_id,
            "status": self.status,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "should_retry": self.should_retry,
        }


@dataclass
class BuyerInfo:
    """
    Buyer/customer information for payment processing.

    This is particularly important for iyzico which requires detailed buyer info.

    Attributes:
        id: Unique buyer identifier
        email: Buyer's email address
        name: First name
        surname: Last name
        phone: Phone number (with country code)
        identity_number: National ID (TC Kimlik No for Turkey)
        address: Full address
        city: City name
        country: Country name
        zip_code: Postal code
        ip: Buyer's IP address
    """

    email: str
    name: str = ""
    surname: str = ""
    id: str = ""
    phone: str = ""
    identity_number: str = ""
    address: str = ""
    city: str = ""
    country: str = "Turkey"
    zip_code: str = ""
    ip: str = "127.0.0.1"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for provider APIs."""
        return {
            "id": self.id or self.email,
            "email": self.email,
            "name": self.name or "Customer",
            "surname": self.surname or "Customer",
            "gsmNumber": self.phone or "+905000000000",
            "identityNumber": self.identity_number or "11111111111",
            "registrationAddress": self.address or self.country,
            "ip": self.ip,
            "city": self.city or "Istanbul",
            "country": self.country,
            "zipCode": self.zip_code or "34000",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BuyerInfo:
        """Create BuyerInfo from a dictionary."""
        return cls(
            id=str(data.get("id", "")),
            email=data.get("email", ""),
            name=data.get("name", data.get("first_name", "")),
            surname=data.get("surname", data.get("last_name", "")),
            phone=data.get("phone", data.get("gsmNumber", "")),
            identity_number=data.get("identity_number", data.get("identityNumber", "")),
            address=data.get("address", data.get("registrationAddress", "")),
            city=data.get("city", ""),
            country=data.get("country", "Turkey"),
            zip_code=data.get("zip_code", data.get("zipCode", "")),
            ip=data.get("ip", "127.0.0.1"),
        )


class PaymentProvider(ABC):
    """
    Abstract base class for payment providers.

    All payment gateway integrations should implement this interface.
    This ensures consistent behavior across different providers like
    iyzico, Stripe, PayTR, etc.

    Example:
        >>> provider = get_payment_provider()  # Returns configured provider
        >>> result = provider.create_payment(payment, callback_url="https://...")
        >>> if result.success:
        ...     redirect_to(result.checkout_url)
    """

    # Provider identifier (e.g., "iyzico", "stripe")
    provider_name: str = ""

    @abstractmethod
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
        Create a payment with the provider.

        This initiates the payment process. Depending on the provider, this may:
        - Create a payment intent (Stripe)
        - Initialize a checkout form (iyzico)
        - Generate a payment link

        Args:
            payment: Payment object with id, amount, currency
            currency: Currency code (default: TRY)
            callback_url: URL for provider callbacks/redirects
            buyer_info: Buyer information for the payment
            **kwargs: Provider-specific options

        Returns:
            PaymentResult with provider-specific details (token, checkout_url, etc.)

        Example:
            >>> result = provider.create_payment(
            ...     payment,
            ...     callback_url="https://example.com/callback",
            ...     buyer_info={"email": "user@example.com", "name": "John"}
            ... )
        """
        pass

    @abstractmethod
    def confirm_payment(self, provider_payment_id: str) -> PaymentResult:
        """
        Confirm/retrieve a payment status.

        Use this to verify a payment was successful after callback or
        to check the current status of a payment.

        Args:
            provider_payment_id: The provider's payment/transaction ID or token

        Returns:
            PaymentResult with confirmation status

        Example:
            >>> result = provider.confirm_payment("tok_abc123")
            >>> if result.success and result.status == "succeeded":
            ...     mark_order_as_paid()
        """
        pass

    @abstractmethod
    def create_refund(
        self,
        payment: PaymentLike,
        amount: int | None = None,
        reason: str = "",
        **kwargs: Any,
    ) -> RefundResult:
        """
        Create a refund for a payment.

        Args:
            payment: The original payment to refund
            amount: Amount to refund in smallest currency unit, or None for full refund
            reason: Reason for the refund
            **kwargs: Provider-specific options

        Returns:
            RefundResult with refund details

        Example:
            >>> result = provider.create_refund(payment, amount=5000, reason="Customer request")
        """
        pass

    @abstractmethod
    def handle_webhook(
        self,
        payload: bytes,
        signature: str | None = None,
        **kwargs: Any,
    ) -> WebhookResult:
        """
        Handle a webhook/callback from the provider.

        This processes incoming notifications from the payment provider
        about payment status changes.

        Args:
            payload: Raw webhook payload (bytes)
            signature: Webhook signature for verification
            **kwargs: Additional data (e.g., headers, query params)

        Returns:
            WebhookResult with event processing status

        Example:
            >>> result = provider.handle_webhook(request.body, request.headers.get("signature"))
        """
        pass

    @abstractmethod
    def get_payment_status(self, provider_payment_id: str) -> str:
        """
        Get the current status of a payment from the provider.

        Args:
            provider_payment_id: The provider's payment/transaction ID

        Returns:
            Status string (e.g., 'pending', 'succeeded', 'failed', 'refunded')
        """
        pass

    def supports_checkout_form(self) -> bool:
        """
        Whether the provider supports an embedded checkout form.

        Returns:
            True if provider supports embedded checkout (e.g., Stripe Elements)
        """
        return False

    def supports_redirect(self) -> bool:
        """
        Whether the provider uses redirect-based checkout.

        Returns:
            True if provider redirects to external page (e.g., iyzico checkout)
        """
        return False

    def supports_subscriptions(self) -> bool:
        """
        Whether the provider supports recurring/subscription payments.

        Returns:
            True if provider supports subscriptions
        """
        return False

    def supports_installments(self) -> bool:
        """
        Whether the provider supports installment payments.

        Returns:
            True if provider supports installments (common in Turkey)
        """
        return False
