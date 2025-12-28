"""
Stripe payment provider.

This provider wraps the Stripe SDK to provide a consistent interface
compatible with the payments-tr provider abstraction.

Requires: pip install django-payments-tr[stripe]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings

from payments_tr.providers.base import (
    BuyerInfo,
    PaymentLike,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
)

if TYPE_CHECKING:
    import stripe as stripe_module  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProvider):
    """
    Stripe payment provider.

    This provider uses the Stripe SDK directly, providing a consistent
    interface for the payments-tr abstraction layer.

    Features:
        - Payment Intent creation
        - Client-side confirmation (Stripe Elements / Payment Element)
        - Refunds (full and partial)
        - Webhook handling with signature verification

    Configuration (in Django settings):
        STRIPE_SECRET_KEY: Your Stripe secret key
        STRIPE_PUBLISHABLE_KEY: Your Stripe publishable key
        STRIPE_WEBHOOK_SECRET: Webhook signing secret

    Example:
        >>> from payments_tr import get_payment_provider
        >>> provider = get_payment_provider("stripe")
        >>> result = provider.create_payment(payment, currency="TRY")
        >>> if result.success:
        ...     # Send client_secret to frontend for Stripe.js
        ...     return {"client_secret": result.client_secret}
    """

    provider_name = "stripe"

    def __init__(self) -> None:
        """Initialize the Stripe provider."""
        try:
            import stripe

            self._stripe: stripe_module = stripe
        except ImportError as e:
            raise ImportError(
                "stripe is required for the Stripe provider. "
                "Install it with: pip install django-payments-tr[stripe]"
            ) from e

        self._stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
        self._webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

        if not self._stripe.api_key:
            logger.warning("STRIPE_SECRET_KEY not configured in settings")

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
        Create a Stripe Payment Intent.

        Args:
            payment: Payment object with id, amount, currency
            currency: Currency code (default: TRY)
            callback_url: Not used by Stripe (client-side confirmation)
            buyer_info: Optional buyer information for receipt
            **kwargs: Additional options:
                - payment_method_types: List of allowed methods (default: ["card"])
                - metadata: Additional metadata for the payment
                - description: Payment description
                - receipt_email: Email for receipt

        Returns:
            PaymentResult with client_secret for frontend confirmation
        """
        try:
            # Build metadata
            metadata = kwargs.get("metadata", {})
            metadata["payment_id"] = str(payment.id)

            # Get buyer email for receipt
            receipt_email = kwargs.get("receipt_email")
            if not receipt_email and isinstance(buyer_info, dict):
                receipt_email = buyer_info.get("email")
            elif not receipt_email and isinstance(buyer_info, BuyerInfo):
                receipt_email = buyer_info.email

            # Create Payment Intent
            intent = self._stripe.PaymentIntent.create(
                amount=payment.amount,
                currency=currency.lower(),
                payment_method_types=kwargs.get("payment_method_types", ["card"]),
                metadata=metadata,
                description=kwargs.get("description", f"Payment {payment.id}"),
                receipt_email=receipt_email,
            )

            return PaymentResult(
                success=True,
                provider_payment_id=intent.id,
                client_secret=intent.client_secret,
                status=intent.status,
                raw_response=dict(intent),
            )

        except self._stripe.error.StripeError as e:
            logger.error(f"Stripe error creating payment intent: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
                error_code=getattr(e, "code", "STRIPE_ERROR"),
            )
        except Exception as e:
            logger.exception(f"Error creating Stripe payment intent: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
                error_code="STRIPE_ERROR",
            )

    def confirm_payment(self, provider_payment_id: str) -> PaymentResult:
        """
        Retrieve and confirm a Stripe Payment Intent status.

        Args:
            provider_payment_id: The Stripe Payment Intent ID (pi_xxx)

        Returns:
            PaymentResult with current status
        """
        try:
            intent = self._stripe.PaymentIntent.retrieve(provider_payment_id)

            success = intent.status in ("succeeded", "processing")
            return PaymentResult(
                success=success,
                provider_payment_id=intent.id,
                status=intent.status,
                raw_response=dict(intent),
            )

        except self._stripe.error.StripeError as e:
            logger.error(f"Stripe error confirming payment: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
                error_code=getattr(e, "code", "STRIPE_ERROR"),
            )
        except Exception as e:
            logger.exception(f"Error confirming Stripe payment: {e}")
            return PaymentResult(
                success=False,
                error_message=str(e),
            )

    def create_refund(
        self,
        payment: PaymentLike,
        amount: int | None = None,
        reason: str = "",
        **kwargs: Any,
    ) -> RefundResult:
        """
        Create a Stripe refund.

        Args:
            payment: Payment object (must have Stripe payment intent ID)
            amount: Amount to refund in smallest unit, or None for full refund
            reason: Reason for refund (customer_requested, duplicate, fraudulent)
            **kwargs: Additional options:
                - provider_payment_id: Override payment intent ID

        Returns:
            RefundResult with refund status
        """
        # Get the Stripe payment intent ID
        provider_payment_id = getattr(payment, "stripe_payment_intent_id", None)
        if not provider_payment_id:
            provider_payment_id = kwargs.get("provider_payment_id")

        if not provider_payment_id:
            return RefundResult(
                success=False,
                error_message="No Stripe payment intent ID found on payment object",
                error_code="MISSING_PAYMENT_ID",
            )

        try:
            refund_params: dict[str, Any] = {
                "payment_intent": provider_payment_id,
            }

            if amount is not None:
                refund_params["amount"] = amount

            # Map reason to Stripe's accepted values
            if reason:
                reason_map = {
                    "customer_requested": "requested_by_customer",
                    "duplicate": "duplicate",
                    "fraudulent": "fraudulent",
                }
                refund_params["reason"] = reason_map.get(reason.lower(), "requested_by_customer")

            refund = self._stripe.Refund.create(**refund_params)

            return RefundResult(
                success=True,
                provider_refund_id=refund.id,
                amount=refund.amount,
                status=refund.status,
                raw_response=dict(refund),
            )

        except self._stripe.error.StripeError as e:
            logger.error(f"Stripe error creating refund: {e}")
            return RefundResult(
                success=False,
                error_message=str(e),
                error_code=getattr(e, "code", "STRIPE_ERROR"),
            )
        except Exception as e:
            logger.exception(f"Error creating Stripe refund: {e}")
            return RefundResult(
                success=False,
                error_message=str(e),
            )

    def handle_webhook(
        self,
        payload: bytes,
        signature: str | None = None,
        **kwargs: Any,
    ) -> WebhookResult:
        """
        Handle a Stripe webhook event.

        Args:
            payload: Raw webhook payload (bytes)
            signature: Stripe-Signature header value
            **kwargs: Additional data

        Returns:
            WebhookResult with event details
        """
        if not signature:
            return WebhookResult(
                success=False,
                error_message="Missing Stripe signature",
            )

        try:
            event = self._stripe.Webhook.construct_event(
                payload,
                signature,
                self._webhook_secret,
            )

            event_type = event["type"]
            data = event["data"]["object"]

            # Extract payment ID from metadata
            payment_id = None
            if "metadata" in data and "payment_id" in data["metadata"]:
                try:
                    payment_id = int(data["metadata"]["payment_id"])
                except (ValueError, TypeError):
                    payment_id = data["metadata"]["payment_id"]

            return WebhookResult(
                success=True,
                event_type=event_type,
                payment_id=payment_id,
                provider_payment_id=data.get("id"),
                status=data.get("status", ""),
            )

        except self._stripe.error.SignatureVerificationError as e:
            logger.warning(f"Invalid Stripe webhook signature: {e}")
            return WebhookResult(
                success=False,
                error_message="Invalid signature",
            )
        except Exception as e:
            logger.exception(f"Error handling Stripe webhook: {e}")
            return WebhookResult(
                success=False,
                error_message=str(e),
                should_retry=True,
            )

    def get_payment_status(self, provider_payment_id: str) -> str:
        """Get the current status of a payment from Stripe."""
        result = self.confirm_payment(provider_payment_id)
        return result.status or "unknown"

    def supports_checkout_form(self) -> bool:
        """Stripe supports embedded Payment Element."""
        return True

    def supports_redirect(self) -> bool:
        """Stripe can redirect for 3D Secure."""
        return True

    def supports_subscriptions(self) -> bool:
        """Stripe supports subscriptions."""
        return True
