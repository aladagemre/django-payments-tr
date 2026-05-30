"""
Django views for django-iyzico.

Handles webhooks, 3D Secure callbacks, and payment processing views.
"""

import json
import logging

from django.core.cache.backends.base import BaseCache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from ..base import PaymentResult
from .client import IyzicoClient
from .exceptions import ThreeDSecureError
from .settings import iyzico_settings
from .signals import threeds_completed, threeds_failed, webhook_received
from .utils import (
    fingerprint_token,
    get_client_ip,
    is_ip_allowed,
    sanitize_log_data,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

# Rate limiting constants
THREEDS_CALLBACK_RATE_LIMIT = 30  # requests per minute per IP
THREEDS_CALLBACK_RATE_WINDOW = 60  # seconds
WEBHOOK_RATE_LIMIT = 100  # requests per minute per IP
WEBHOOK_RATE_WINDOW = 60  # seconds


def _rate_limit_exceeded(cache: BaseCache, key: str, limit: int, window: int) -> bool:
    """
    Atomically count one hit against a fixed window and report if over limit.

    A read-modify-write (get -> compare -> set) races under concurrency: many
    simultaneous requests read the same pre-increment value and all pass, so
    the effective limit is far higher than configured (M-04). ``cache.add``
    (set-if-absent) plus ``cache.incr`` (atomic on Redis/Memcached) closes
    that window. Returns True when this request should be rejected.
    """
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        # Key expired between add and incr; re-establish the window.
        cache.add(key, 0, window)
        count = cache.incr(key)
    return bool(count > limit)


def _validate_redirect_url(url: str | None, request: HttpRequest) -> str | None:
    """
    Validate that redirect URL is safe (relative or same host).

    Security: Rejects external URLs and handles wildcard ALLOWED_HOSTS safely
    to prevent open redirect attacks.

    Args:
        url: URL to validate
        request: HTTP request for host comparison

    Returns:
        Safe URL or None if URL is invalid/external
    """
    from urllib.parse import urlparse

    if not url:
        return None

    parsed = urlparse(url)

    # Allow relative URLs (no scheme or netloc)
    if not parsed.scheme and not parsed.netloc:
        return url

    # Check if host matches request host or is in ALLOWED_HOSTS
    from django.conf import settings as django_settings

    allowed_hosts = getattr(django_settings, "ALLOWED_HOSTS", [])
    request_host = request.get_host().split(":")[0]  # Remove port if present

    # SECURITY: If ALLOWED_HOSTS contains wildcard '*', reject absolute URL redirects
    # to prevent open redirect attacks (only allow relative URLs in this case)
    if "*" in allowed_hosts:
        logger.warning(
            "ALLOWED_HOSTS contains wildcard '*' - rejecting absolute URL redirect "
            f"to prevent open redirect vulnerability: {url}"
        )
        return None

    if parsed.netloc:
        netloc_host = parsed.netloc.split(":")[0]  # Remove port if present

        # Allow if matches request host
        if netloc_host == request_host:
            return url

        # Allow if in ALLOWED_HOSTS (excluding wildcards)
        if netloc_host in allowed_hosts and netloc_host != "*":
            return url

        # Allow subdomain wildcard match (e.g., '.example.com' matches 'sub.example.com')
        for allowed in allowed_hosts:
            if allowed.startswith(".") and netloc_host.endswith(allowed):
                return url

    # Reject external URLs
    logger.warning(f"Rejected redirect to external URL: {url}")
    return None


# get_client_ip is now imported from utils for centralized IP extraction


@csrf_exempt
@require_http_methods(["GET", "POST"])
def threeds_callback_view(request: HttpRequest) -> HttpResponse:
    """
    Handle 3D Secure callback from Iyzico.

    This view is called by Iyzico after the user completes 3D Secure authentication.
    The callback can be either GET or POST depending on Iyzico's configuration.

    URL: /iyzico/callback/

    Query Parameters (GET):
        token: Payment token from Iyzico

    Form Data (POST):
        paymentId: Payment token from Iyzico (alternative to token)

    Returns:
        Redirect to success or error page

    Note:
        This view is CSRF exempt because it's called by an external service (Iyzico).
        Users should implement their own success/failure redirect URLs.

    Security:
        - Rate limited to 30 requests per minute per IP
        - Uses consistent error messages to prevent token enumeration
    """
    from django.core.cache import cache

    # Rate limiting - prevent brute force attacks
    client_ip = get_client_ip(request)
    rate_key = f"threeds_callback_rate_{client_ip}"

    if _rate_limit_exceeded(
        cache, rate_key, THREEDS_CALLBACK_RATE_LIMIT, THREEDS_CALLBACK_RATE_WINDOW
    ):
        logger.warning(f"3DS callback rate limit exceeded for IP {client_ip}")
        return _handle_3ds_error(
            request,
            "Too many requests. Please try again later.",
            error_code="RATE_LIMIT_EXCEEDED",
        )

    # Get token from either GET or POST
    token = request.GET.get("token") or request.POST.get("paymentId")

    # Use consistent error message to prevent token enumeration
    generic_error_message = "Payment processing failed. Please try again."

    if not token:
        logger.error("3DS callback received without token")
        return _handle_3ds_error(
            request,
            generic_error_message,
            error_code="PAYMENT_FAILED",
        )

    logger.info(f"3DS callback received - token={fingerprint_token(token)}")

    try:
        # Complete 3D Secure payment
        client = IyzicoClient()
        response = client.complete_3ds_payment(token)

        if response.is_successful():
            logger.info(
                f"3DS payment completed successfully - "
                f"payment_id={response.payment_id}, "
                f"conversation_id={response.conversation_id}"
            )

            # Trigger signal for successful payment
            threeds_completed.send(
                sender=None,
                payment_id=response.payment_id,
                conversation_id=response.conversation_id,
                response=response.to_dict(),
                request=request,
            )

            # Redirect to success page
            return _handle_3ds_success(request, response)

        else:
            logger.warning(
                f"3DS payment failed - "
                f"error_code={response.error_code}, "
                f"error_message={response.error_message}, "
                f"conversation_id={response.conversation_id}"
            )

            # Trigger signal for failed payment (internal handlers get full details)
            threeds_failed.send(
                sender=None,
                conversation_id=response.conversation_id,
                error_code=response.error_code,
                error_message=response.error_message,
                request=request,
            )

            # Redirect to error page with generic message (prevents token enumeration)
            return _handle_3ds_error(
                request,
                generic_error_message,
                error_code="PAYMENT_FAILED",
                conversation_id=response.conversation_id,
            )

    except ThreeDSecureError as e:
        logger.error(f"3DS completion error: {str(e)}", exc_info=True)

        # Trigger signal for failed payment (internal handlers get full details)
        threeds_failed.send(
            sender=None,
            conversation_id=None,
            error_code=e.error_code,
            error_message=str(e),
            request=request,
        )

        # User gets generic message (prevents token enumeration)
        return _handle_3ds_error(
            request,
            generic_error_message,
            error_code="PAYMENT_FAILED",
        )

    except Exception as e:
        logger.error(f"Unexpected error in 3DS callback: {str(e)}", exc_info=True)

        # Trigger signal for failed payment (internal handlers get full details)
        threeds_failed.send(
            sender=None,
            conversation_id=None,
            error_code="UNEXPECTED_ERROR",
            error_message=str(e),
            request=request,
        )

        # User gets generic message (prevents token enumeration)
        return _handle_3ds_error(
            request,
            generic_error_message,
            error_code="PAYMENT_FAILED",
        )


def _confirm_webhook_token(token: str) -> PaymentResult:
    """
    Re-derive authoritative payment state from iyzico for a webhook token.

    The shipped webhook view must not trust the attacker-suppliable
    ``paymentId``/``status`` in the request body. When a checkout-form
    notification carries a ``token``, we call iyzico server-side to confirm
    the real result. Returns the provider's ``PaymentResult`` on success, or
    ``None`` if confirmation could not be performed.
    """
    from payments_tr.providers.registry import get_payment_provider

    provider = get_payment_provider("iyzico")
    return provider.confirm_payment(token)


@csrf_exempt
@require_POST
def webhook_view(request: HttpRequest) -> JsonResponse:
    """
    Handle webhook notifications from Iyzico.

    This view receives POST requests from Iyzico for various payment events.
    Supports optional signature validation and IP whitelisting.

    URL: /iyzico/webhook/

    Request Headers:
        X-IYZ-SIGNATURE-V3: iyzico webhook signature (verified against the
            merchant secret key when present). The legacy ``X-Iyzico-Signature``
            header is also accepted for backwards compatibility.

    Request Body (JSON):
        {
            "iyziEventType": "event_type",
            "paymentId": "payment_id",
            "conversationId": "conversation_id",
            ...
        }

    Returns:
        JSON response with status 200 (always, to prevent retry spam)

    Note:
        - This view is CSRF exempt (external webhook)
        - Always returns 200 OK to prevent webhook retry spam
        - Actual processing should be done asynchronously via signals
        - Users should connect to the webhook_received signal to handle events

    Security:
        - Signature validation (X-IYZ-SIGNATURE-V3) against the merchant
          IYZICO_SECRET_KEY whenever a signature header is present
        - Server-side confirmation of the payment ``token`` before emitting
          the ``webhook_received`` signal (never trusts the body's paymentId)
        - IP whitelisting via IYZICO_WEBHOOK_ALLOWED_IPS (required in
          production)
        - Rate limiting to prevent abuse
    """
    from django.core.cache import cache

    logger.info("Webhook received")

    # Get client IP
    client_ip = get_client_ip(request)
    logger.debug(f"Webhook from IP: {client_ip}")

    # Rate limiting - prevent abuse
    rate_key = f"webhook_rate_{client_ip}"

    if _rate_limit_exceeded(cache, rate_key, WEBHOOK_RATE_LIMIT, WEBHOOK_RATE_WINDOW):
        logger.warning(f"Webhook rate limit exceeded for IP {client_ip}")
        # Return 200 to prevent webhook retry storms from payment provider
        # Error is indicated in the response body for logging/debugging
        return JsonResponse(
            {"status": "error", "message": "Rate limit exceeded"},
            status=200,
        )

    # Verify IP whitelist and webhook signature.
    #
    # iyzico signs webhooks (header ``X-IYZ-SIGNATURE-V3``) with the merchant
    # secret key, not a separate webhook secret. ``IYZICO_SECRET_KEY`` is
    # always configured (it is required to talk to iyzico at all), so the
    # signature path is keyed off it. The legacy ``IYZICO_WEBHOOK_SECRET`` is
    # only used to *gate whether* signature verification is enforced, for
    # backwards compatibility with existing deployments.
    allowed_ips = iyzico_settings.webhook_allowed_ips
    secret_key = iyzico_settings.secret_key

    from django.conf import settings as django_settings

    is_debug = getattr(django_settings, "DEBUG", False)

    # SECURITY: In production, require the IP whitelist. Combined with
    # server-side confirmation below, this prevents forged "paid" webhooks.
    if not is_debug:
        if not allowed_ips:
            logger.error(
                "SECURITY ERROR: Webhook security not properly configured! "
                "IYZICO_WEBHOOK_ALLOWED_IPS not configured. "
                "The IP allowlist is required in production. "
                "Rejecting webhook to prevent unauthorized access."
            )
            return JsonResponse(
                {"status": "error", "message": "Webhook security not configured"},
                status=403,
            )
    else:
        # Debug mode warnings
        if not allowed_ips:
            logger.warning(
                "Webhook IP whitelist not configured. Allowing all IPs in DEBUG mode. "
                "Configure IYZICO_WEBHOOK_ALLOWED_IPS for production."
            )

    # Verify IP whitelist (if configured)
    if allowed_ips and not is_ip_allowed(client_ip, allowed_ips):
        logger.warning(f"Webhook rejected - IP {client_ip} not in whitelist")
        return JsonResponse(
            {"status": "error", "message": "IP not allowed"},
            status=403,
        )

    try:
        # Parse webhook data
        try:
            webhook_data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid webhook JSON: {str(e)}")
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON"},
                status=200,  # Still return 200 to avoid retry
            )

        # Verify webhook signature against the parsed body using iyzico's
        # real X-IYZ-SIGNATURE-V3 scheme (keyed by the merchant secret key).
        # The legacy ``X-Iyzico-Signature`` header is also accepted so older
        # senders keep working.
        signature = request.META.get("HTTP_X_IYZ_SIGNATURE_V3", "") or request.META.get(
            "HTTP_X_IYZICO_SIGNATURE", ""
        )
        signature_verified = False
        if signature:
            if verify_webhook_signature(webhook_data, signature, secret_key):
                signature_verified = True
            else:
                logger.warning("Webhook rejected - invalid signature")
                return JsonResponse(
                    {"status": "error", "message": "Invalid signature"},
                    status=403,
                )

        # Extract raw, attacker-suppliable event information. These values are
        # NOT trusted until confirmed below.
        event_type = webhook_data.get("iyziEventType")
        raw_payment_id = webhook_data.get("paymentId")
        conversation_id = webhook_data.get("conversationId")
        token = webhook_data.get("token")

        logger.info(
            f"Webhook event - type={event_type}, "
            f"payment_id={raw_payment_id}, "
            f"conversation_id={conversation_id}, "
            f"signature_verified={signature_verified}"
        )

        # Log full webhook data — sanitized to drop card data and PII.
        logger.debug("Webhook data: %s", sanitize_log_data(webhook_data))

        # SECURITY (H-02): never trust the body's paymentId/status verbatim.
        # When the notification carries a checkout-form ``token``, re-derive
        # the authoritative payment state from iyzico server-side before
        # emitting the signal. The signal exposes ``confirmed`` so handlers
        # know whether ``payment_id``/``status`` are server-verified.
        payment_id = raw_payment_id
        status = webhook_data.get("status")
        confirmed = False
        if token:
            try:
                provider_result = _confirm_webhook_token(token)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Webhook token confirmation failed: %s", exc)
                provider_result = None

            if provider_result is not None:
                confirmed = True
                payment_id = provider_result.provider_payment_id or raw_payment_id
                status = "succeeded" if provider_result.success else "failed"
            else:
                logger.warning(
                    "Webhook token could not be confirmed server-side; "
                    "emitting unconfirmed signal. Consumers MUST re-confirm "
                    "before treating the payment as paid."
                )

        # Trigger signal for webhook processing.
        # ``confirmed=True`` means payment_id/status were re-derived from
        # iyzico server-side. When False, consumers MUST confirm the payment
        # themselves (and pass expected_amount/expected_currency) before
        # acting on it; the raw body values are not authenticated.
        webhook_received.send(
            sender=None,
            event_type=event_type,
            payment_id=payment_id,
            conversation_id=conversation_id,
            status=status,
            confirmed=confirmed,
            signature_verified=signature_verified,
            data=webhook_data,
            request=request,
        )

        # Return success immediately
        # Actual processing should be done asynchronously via signal handlers
        return JsonResponse(
            {"status": "success", "message": "Webhook received"},
            status=200,
        )

    except Exception as e:
        # Log error but still return 200 to avoid webhook retry spam
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)

        return JsonResponse(
            {"status": "error", "message": "Internal error"},
            status=200,  # Still 200 to avoid retry
        )


def _handle_3ds_success(request: HttpRequest, response) -> HttpResponse:
    """
    Handle successful 3DS payment redirect.

    Users can customize this behavior by:
    1. Setting IYZICO_SUCCESS_URL in Django settings
    2. Passing success_url in session
    3. Overriding this function

    Args:
        request: HTTP request
        response: Payment response from Iyzico

    Returns:
        HttpResponse (redirect or rendered page)
    """
    from django.conf import settings

    # Try to get success URL from various sources, with validation
    session_url = _validate_redirect_url(request.session.get("iyzico_success_url"), request)
    settings_url = _validate_redirect_url(getattr(settings, "IYZICO_SUCCESS_URL", None), request)

    success_url = session_url or settings_url or "/payment/success/"

    # Clean up session - remove URL redirects and previous payment data
    # (consistent with error handler)
    payment_session_keys = [
        "iyzico_success_url",
        "iyzico_error_url",
        "last_payment_id",
        "last_payment_status",
        "last_payment_error",
        "last_payment_error_code",
        "last_payment_conversation_id",
    ]
    for key in payment_session_keys:
        request.session.pop(key, None)

    # Add payment info to session for success page
    request.session["last_payment_id"] = response.payment_id
    request.session["last_payment_status"] = "success"

    logger.debug(f"Redirecting to success URL: {success_url}")
    return redirect(success_url)


def _handle_3ds_error(
    request: HttpRequest,
    error_message: str,
    error_code: str | None = None,
    conversation_id: str | None = None,
) -> HttpResponse:
    """
    Handle failed 3DS payment redirect.

    Users can customize this behavior by:
    1. Setting IYZICO_ERROR_URL in Django settings
    2. Passing error_url in session
    3. Overriding this function

    Args:
        request: HTTP request
        error_message: Error message
        error_code: Error code (optional)
        conversation_id: Conversation ID (optional)

    Returns:
        HttpResponse (redirect or rendered page)
    """
    from django.conf import settings

    # Try to get error URL from various sources, with validation
    session_url = _validate_redirect_url(request.session.get("iyzico_error_url"), request)
    settings_url = _validate_redirect_url(getattr(settings, "IYZICO_ERROR_URL", None), request)

    error_url = session_url or settings_url or "/payment/error/"

    # Clean up session - remove URL redirects and previous payment data
    payment_session_keys = [
        "iyzico_success_url",
        "iyzico_error_url",
        "last_payment_id",
        "last_payment_status",
        "last_payment_error",
        "last_payment_error_code",
        "last_payment_conversation_id",
    ]
    for key in payment_session_keys:
        request.session.pop(key, None)

    # Add error info to session for error page
    request.session["last_payment_status"] = "failed"
    request.session["last_payment_error"] = error_message
    if error_code:
        request.session["last_payment_error_code"] = error_code
    if conversation_id:
        request.session["last_payment_conversation_id"] = conversation_id

    logger.debug(f"Redirecting to error URL: {error_url}")
    return redirect(error_url)


# Optional: Helper view for testing webhooks in development
@csrf_exempt
@require_POST
def test_webhook_view(request: HttpRequest) -> JsonResponse:
    """
    Test webhook endpoint for development.

    This view can be used to manually trigger webhook events during development.

    URL: /iyzico/webhook/test/

    Note:
        This view should be disabled in production!
    """
    from django.conf import settings

    # Only allow in DEBUG mode
    if not getattr(settings, "DEBUG", False):
        return JsonResponse(
            {"status": "error", "message": "Not available in production"},
            status=403,
        )

    logger.info("Test webhook triggered")

    # Create test webhook data
    test_data = {
        "iyziEventType": "test_event",
        "paymentId": "test_payment_id",
        "conversationId": "test_conversation_id",
        "status": "success",
        "test": True,
    }

    # Trigger webhook signal
    webhook_received.send(
        sender=None,
        event_type=test_data["iyziEventType"],
        payment_id=test_data["paymentId"],
        conversation_id=test_data["conversationId"],
        data=test_data,
        request=request,
    )

    return JsonResponse(
        {"status": "success", "message": "Test webhook triggered"},
        status=200,
    )
