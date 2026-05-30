"""
Utility functions for django-iyzico.

Contains helper functions for payment processing, data validation, card masking,
and data transformation.
"""

import hashlib
import hmac
import ipaddress
import logging
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from .exceptions import ValidationError

logger = logging.getLogger(__name__)


# Comprehensive list of sensitive field names to mask/remove
SENSITIVE_CARD_FIELDS = frozenset({
    # Card numbers
    "cardNumber",
    "card_number",
    "number",
    "cardNo",
    "card_no",
    "pan",
    "PAN",
    "primaryAccountNumber",
    # Security codes
    "cvc",
    "cvv",
    "cvv2",
    "cvc2",
    "securityCode",
    "security_code",
    "cid",
    "CID",
    "cardSecurityCode",
    "card_security_code",
    # Expiry dates
    "expireMonth",
    "expire_month",
    "expiryMonth",
    "expiry_month",
    "expireYear",
    "expire_year",
    "expiryYear",
    "expiry_year",
    "expiry",
    "expirationDate",
    "expiration_date",
    "exp",
    # PIN and passwords
    "pin",
    "PIN",
    "password",
    "passwd",
    # Tokens (might need to keep for recurring payments, handle carefully)
    # 'cardToken' - NOT in this list as it may be needed
})

# Fields that are safe to keep (non-sensitive)
SAFE_CARD_FIELDS = frozenset({
    "cardType",
    "card_type",
    "cardFamily",
    "card_family",
    "cardAssociation",
    "card_association",
    "cardBankName",
    "card_bank_name",
    "cardBankCode",
    "card_bank_code",
    "cardHolderName",
    "holderName",
    "lastFourDigits",
    "last_four",
    "binNumber",
    "bin_number",
    "cardToken",
    "cardUserKey",  # Tokens are safe (references, not actual data)
})


def mask_card_data(payment_details: dict[str, Any]) -> dict[str, Any]:
    """
    Remove sensitive card data before storage (PCI DSS compliance).

    This function comprehensively masks all sensitive payment card data
    to ensure PCI DSS compliance. It handles various field naming conventions
    used by different payment systems.

    Keeps only:
    - Last 4 digits of card number
    - Cardholder name
    - Card metadata (type, family, association)
    - BIN number (first 6 digits - not sensitive)
    - Card tokens (secure references)

    Removes:
    - Full card number
    - CVC/CVV/Security codes
    - Full expiry dates
    - PIN numbers

    Args:
        payment_details: Dictionary containing card and payment information

    Returns:
        Dictionary with sensitive data removed/masked

    Example:
        >>> payment = {
        ...     'card': {
        ...         'cardNumber': '5528790000000008',
        ...         'cvc': '123',
        ...         'expireMonth': '12',
        ...         'expireYear': '2030'
        ...     }
        ... }
        >>> safe = mask_card_data(payment)
        >>> safe['card']['lastFourDigits']
        '0008'
        >>> 'cardNumber' in safe['card']
        False
        >>> 'cvc' in safe['card']
        False
    """
    if not isinstance(payment_details, dict):
        # Defensive: ``payment_details`` is typed as ``dict`` but historic
        # callers (and the ``parse_iyzico_response`` deserialiser) can pass
        # anything; keep the runtime guard.
        logger.warning(  # type: ignore[unreachable]
            "mask_card_data received non-dict input"
        )
        return {}

    # ``_mask_dict_recursive`` is typed as ``-> Any`` (it accepts any
    # nested value); when the input is a dict it returns a dict.
    safe_data: dict[str, Any] = _mask_dict_recursive(payment_details)

    # Handle the 'card' key specially
    if "card" in safe_data and isinstance(safe_data["card"], dict):
        card = payment_details.get("card", {})  # Get original card data

        # Extract card number from various possible field names
        card_number = ""
        for field in ["cardNumber", "card_number", "number", "pan"]:
            if field in card:
                card_number = str(card[field])
                break

        # Extract last 4 digits
        if len(card_number) >= 4:
            last_four = card_number[-4:]
        else:
            last_four = card_number if card_number.isdigit() else ""

        # Extract BIN (first 6 digits) - this is not sensitive
        bin_number = ""
        if len(card_number) >= 6:
            bin_number = card_number[:6]

        # Build safe card data
        safe_card = {
            "lastFourDigits": last_four,
            "binNumber": bin_number,
        }

        # Copy safe fields from original
        for field in SAFE_CARD_FIELDS:
            if field in card:
                safe_card[field] = card[field]

        # Get cardholder name from various possible fields
        holder_name = (
            card.get("cardHolderName")
            or card.get("holderName")
            or card.get("card_holder_name")
            or card.get("name")
            or ""
        )
        if holder_name:
            safe_card["cardHolderName"] = holder_name

        safe_data["card"] = safe_card

        # Log masking activity
        if last_four:
            logger.debug(f"Masked card data - BIN: {bin_number[:2]}****, Last 4: {last_four}")

    # Handle 'paymentCard' key (Iyzico SDK format)
    if "paymentCard" in safe_data:
        safe_data["paymentCard"] = _mask_dict_recursive(safe_data["paymentCard"])

    return safe_data


def _mask_dict_recursive(data: Any) -> Any:
    """
    Recursively mask sensitive fields in a dictionary.

    Args:
        data: Dictionary or other value to mask.

    Returns:
        Masked data with sensitive fields replaced with '***REDACTED***'.
    """
    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in SENSITIVE_CARD_FIELDS:
                # Replace sensitive data
                result[key] = "***REDACTED***"
            elif isinstance(value, dict):
                result[key] = _mask_dict_recursive(value)
            elif isinstance(value, list):
                result[key] = [_mask_dict_recursive(item) for item in value]
            else:
                result[key] = value
        return result
    elif isinstance(data, list):
        return [_mask_dict_recursive(item) for item in data]
    else:
        return data


# Currency-specific validation limits
# These prevent potentially fraudulent or erroneous transactions
CURRENCY_LIMITS: dict[str, dict[str, Decimal]] = {
    "TRY": {
        "min": Decimal("0.01"),
        "max": Decimal("1000000.00"),  # 1 million TRY
    },
    "USD": {
        "min": Decimal("0.01"),
        "max": Decimal("50000.00"),  # 50k USD
    },
    "EUR": {
        "min": Decimal("0.01"),
        "max": Decimal("50000.00"),  # 50k EUR
    },
    "GBP": {
        "min": Decimal("0.01"),
        "max": Decimal("50000.00"),  # 50k GBP
    },
    # Default limits for other currencies
    "DEFAULT": {
        "min": Decimal("0.01"),
        "max": Decimal("100000.00"),  # 100k default
    },
}


def validate_amount(
    amount: Any,
    currency: str = "TRY",
    custom_max: Decimal | None = None,
) -> Decimal:
    """
    Validate and convert payment amount to Decimal with currency-specific limits.

    This function ensures amounts are within acceptable ranges to prevent:
    - Accidental high-value transactions
    - Potential fraud attempts
    - Micro-transaction spam

    Args:
        amount: Amount to validate (can be str, int, float, Decimal)
        currency: Currency code (default: TRY)
        custom_max: Optional custom maximum amount (overrides currency default)

    Returns:
        Validated Decimal amount

    Raises:
        ValidationError: If amount is invalid, too low, or too high

    Example:
        >>> validate_amount("100.50")
        Decimal('100.50')
        >>> validate_amount(0)
        Traceback (most recent call last):
        ...
        ValidationError: Amount must be greater than zero
        >>> validate_amount("999999999")
        Traceback (most recent call last):
        ...
        ValidationError: Amount exceeds maximum allowed for TRY
    """
    try:
        decimal_amount = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValidationError(
            f"Invalid amount format: {amount}",
            error_code="INVALID_AMOUNT_FORMAT",
        ) from e

    # Validate amount is positive
    if decimal_amount <= 0:
        raise ValidationError(
            "Amount must be greater than zero",
            error_code="INVALID_AMOUNT",
        )

    # Validate decimal places (max 2 for most currencies).
    # ``exponent`` is ``int`` for finite numbers and a literal ``"n"``,
    # ``"N"`` or ``"F"`` for NaN / Infinity; we already guarded against
    # those via ``Decimal(str(...))`` above (raises ``InvalidOperation``).
    exponent = decimal_amount.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationError(
            "Amount cannot have more than 2 decimal places",
            error_code="INVALID_AMOUNT_PRECISION",
        )

    # Get currency-specific limits
    currency_upper = currency.upper()
    limits = CURRENCY_LIMITS.get(currency_upper, CURRENCY_LIMITS["DEFAULT"])
    min_amount = limits["min"]
    max_amount = custom_max if custom_max is not None else limits["max"]

    # Check minimum amount
    if decimal_amount < min_amount:
        raise ValidationError(
            f"Amount must be at least {min_amount} {currency_upper}",
            error_code="AMOUNT_TOO_LOW",
        )

    # Check maximum amount
    if decimal_amount > max_amount:
        raise ValidationError(
            f"Amount exceeds maximum allowed for {currency_upper} ({max_amount}). "
            f"If this is intentional, contact support for approval.",
            error_code="AMOUNT_TOO_HIGH",
        )

    # Log validation for high-value transactions (for monitoring)
    warning_threshold = max_amount * Decimal("0.5")  # 50% of max
    if decimal_amount > warning_threshold:
        logger.info(
            f"High-value amount validation: {decimal_amount} {currency_upper} "
            f"(above 50% of {max_amount} limit)"
        )

    logger.debug(f"Validated amount: {decimal_amount} {currency_upper}")
    return decimal_amount


def get_currency_limits(currency: str) -> dict[str, Decimal]:
    """
    Get the validation limits for a specific currency.

    Args:
        currency: Currency code (e.g., 'TRY', 'USD', 'EUR')

    Returns:
        Dictionary with 'min' and 'max' Decimal values

    Example:
        >>> limits = get_currency_limits('USD')
        >>> limits['max']
        Decimal('50000.00')
    """
    currency_upper = currency.upper()
    return CURRENCY_LIMITS.get(currency_upper, CURRENCY_LIMITS["DEFAULT"]).copy()


def validate_payment_data(payment_data: dict[str, Any]) -> None:
    """
    Validate payment request data before sending to Iyzico.

    Args:
        payment_data: Payment data dictionary

    Raises:
        ValidationError: If validation fails

    Example:
        >>> data = {'price': '100', 'paidPrice': '100', 'currency': 'TRY'}
        >>> validate_payment_data(data)
        >>> # No exception means validation passed
    """
    if not isinstance(payment_data, dict):
        raise ValidationError(
            "Payment data must be a dictionary",
            error_code="INVALID_DATA_TYPE",
        )

    # Required fields
    required_fields = ["price", "paidPrice", "currency"]
    missing_fields = [f for f in required_fields if f not in payment_data]

    if missing_fields:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing_fields)}",
            error_code="MISSING_REQUIRED_FIELDS",
        )

    # Validate amounts
    try:
        price = validate_amount(payment_data["price"], payment_data["currency"])
        paid_price = validate_amount(payment_data["paidPrice"], payment_data["currency"])

        # paidPrice should typically be >= price (can be higher with installments)
        if paid_price < price:
            logger.warning(f"Paid price ({paid_price}) is less than price ({price})")

    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(
            f"Amount validation failed: {str(e)}",
            error_code="AMOUNT_VALIDATION_ERROR",
        ) from e

    logger.debug("Payment data validation passed")


def format_price(amount: Any) -> str:
    """
    Format amount for Iyzico API (string with 2 decimal places).

    Args:
        amount: Amount to format

    Returns:
        Formatted price string

    Example:
        >>> format_price(100)
        '100.00'
        >>> format_price(Decimal('99.9'))
        '99.90'
        >>> format_price('150.5')
        '150.50'
    """
    try:
        decimal_amount = Decimal(str(amount))
        # Format with exactly 2 decimal places
        return f"{decimal_amount:.2f}"
    except (InvalidOperation, ValueError, TypeError):
        logger.error(f"Failed to format price: {amount}")
        return "0.00"


def fingerprint_token(token: str | None, length: int = 12) -> str:
    """
    Return a non-reversible, collision-resistant fingerprint of a token.

    Logs and traces should reference tokens by SHA-256 fingerprint, not
    by prefix. Even six characters of a real iyzico token are correlatable
    bearer-credential leakage if log files are retained or shipped to a
    SIEM, and prefixes from the same token correlate across log lines
    that may also carry conversation IDs / buyer emails — enabling
    re-identification.

    Args:
        token: The token to fingerprint. ``None`` / empty returns a
            sentinel rather than raising.
        length: Hex characters of the SHA-256 digest to return. 12 is
            collision-safe up to ~16M tokens.

    Returns:
        Hex string ``"sha256:<n hex chars>"``, or ``"<empty>"`` if the
        token is missing.
    """
    if not token:
        return "<empty>"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:length]}"


def kurus_to_try_string(amount_kurus: int) -> str:
    """
    Convert an integer kuruş amount to an Iyzico-API-formatted TRY string.

    Money MUST go through Decimal — never float — because the result is
    signed by Iyzico's HMAC. ``payment.amount / 100`` (float division)
    can introduce binary-float drift that produces an off-by-one-cent
    signature mismatch.

    Args:
        amount_kurus: Integer amount in kuruş (1/100 of TRY).

    Returns:
        Two-decimal TRY string suitable for Iyzico ``price``/``paidPrice``.

    Example:
        >>> kurus_to_try_string(2999)
        '29.99'
        >>> kurus_to_try_string(1)
        '0.01'
        >>> kurus_to_try_string(10000)
        '100.00'
    """
    return format_price(Decimal(int(amount_kurus)) / Decimal(100))


def generate_conversation_id(prefix: str = "") -> str:
    """
    Generate unique conversation ID for Iyzico request.

    Args:
        prefix: Optional prefix for the conversation ID

    Returns:
        Unique conversation ID

    Example:
        >>> cid = generate_conversation_id("order")
        >>> cid.startswith("order-")
        True
        >>> len(cid) > 10
        True
    """
    unique_id = str(uuid.uuid4())
    if prefix:
        return f"{prefix}-{unique_id}"
    return unique_id


def parse_iyzico_response(raw_response: Any) -> dict[str, Any]:
    """
    Parse Iyzico API response (handles both bytes and dict).

    The iyzipay SDK sometimes returns bytes, sometimes dict.
    This normalizes to dict.

    Args:
        raw_response: Response from iyzipay SDK

    Returns:
        Parsed response dictionary

    Example:
        >>> parse_iyzico_response({'status': 'success'})
        {'status': 'success'}
        >>> import json
        >>> parse_iyzico_response(json.dumps({'status': 'success'}).encode())
        {'status': 'success'}
    """
    if isinstance(raw_response, dict):
        return cast(dict[str, Any], raw_response)

    if isinstance(raw_response, bytes):
        import json

        try:
            return cast(dict[str, Any], json.loads(raw_response.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse bytes response: {e}")
            return {"error": "Failed to parse response", "status": "failure"}

    if isinstance(raw_response, str):
        import json

        try:
            return cast(dict[str, Any], json.loads(raw_response))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse string response: {e}")
            return {"error": "Failed to parse response", "status": "failure"}

    # Unknown type
    logger.error(f"Unknown response type: {type(raw_response)}")
    return {"error": "Unknown response type", "status": "failure"}


def extract_card_info(payment_response: dict[str, Any]) -> dict[str, str]:
    """
    Extract safe card information from Iyzico payment response.

    Args:
        payment_response: Response from Iyzico API

    Returns:
        Dictionary with safe card information

    Example:
        >>> response = {
        ...     'cardType': 'CREDIT_CARD',
        ...     'cardAssociation': 'MASTER_CARD',
        ...     'cardFamily': 'Bonus'
        ... }
        >>> info = extract_card_info(response)
        >>> info['cardType']
        'CREDIT_CARD'
    """
    if not isinstance(payment_response, dict):
        return {}  # type: ignore[unreachable]

    return {
        "cardType": payment_response.get("cardType", ""),
        "cardAssociation": payment_response.get("cardAssociation", ""),
        "cardFamily": payment_response.get("cardFamily", ""),
        "cardBankName": payment_response.get("cardBankName", ""),
        "cardBankCode": payment_response.get("cardBankCode", ""),
    }


def format_buyer_data(buyer: dict[str, Any]) -> dict[str, Any]:
    """
    Format buyer data for Iyzico API.

    Ensures all required fields are present and properly formatted.

    Args:
        buyer: Buyer information dictionary

    Returns:
        Formatted buyer data

    Raises:
        ValidationError: If required buyer fields are missing
    """
    required_fields = [
        "id",
        "name",
        "surname",
        "email",
        "identityNumber",
        "registrationAddress",
        "city",
        "country",
    ]

    missing_fields = [f for f in required_fields if not buyer.get(f)]
    if missing_fields:
        raise ValidationError(
            f"Missing required buyer fields: {', '.join(missing_fields)}",
            error_code="MISSING_BUYER_FIELDS",
        )

    # Format phone number (ensure it starts with +)
    gsm_number = buyer.get("gsmNumber", "")
    if gsm_number and not gsm_number.startswith("+"):
        gsm_number = f"+{gsm_number}"

    return {
        "id": str(buyer["id"]),
        "name": buyer["name"],
        "surname": buyer["surname"],
        "gsmNumber": gsm_number,
        "email": buyer["email"],
        "identityNumber": buyer["identityNumber"],
        "registrationAddress": buyer["registrationAddress"],
        "city": buyer["city"],
        "country": buyer["country"],
        "zipCode": buyer.get("zipCode", ""),
    }


def format_address_data(address: dict[str, Any], contact_name: str | None = None) -> dict[str, Any]:
    """
    Format address data for Iyzico API.

    Args:
        address: Address information dictionary
        contact_name: Contact name for the address

    Returns:
        Formatted address data

    Raises:
        ValidationError: If required address fields are missing
    """
    required_fields = ["address", "city", "country"]

    missing_fields = [f for f in required_fields if not address.get(f)]
    if missing_fields:
        raise ValidationError(
            f"Missing required address fields: {', '.join(missing_fields)}",
            error_code="MISSING_ADDRESS_FIELDS",
        )

    return {
        "contactName": contact_name or address.get("contactName", ""),
        "city": address["city"],
        "country": address["country"],
        "address": address["address"],
        "zipCode": address.get("zipCode", ""),
    }


_LOG_SENSITIVE_FIELDS: frozenset[str] = frozenset({
    # Card data
    "cardNumber",
    "card_number",
    "number",
    "cardNo",
    "card_no",
    "pan",
    "PAN",
    "cvc",
    "cvv",
    "cvv2",
    "cvc2",
    "securityCode",
    "security_code",
    "expireMonth",
    "expire_month",
    "expiryMonth",
    "expiry_month",
    "expireYear",
    "expire_year",
    "expiryYear",
    "expiry_year",
    # API credentials
    "api_key",
    "apiKey",
    "secret_key",
    "secretKey",
    "webhook_secret",
    "webhookSecret",
    "authorization",
    "Authorization",
    # Personally identifiable / quasi-identifying data (KVKK / GDPR).
    # TCKN (Turkish national ID) is special-category-adjacent and a known
    # fraud vector; phone, email, and address are direct identifiers.
    "identityNumber",
    "identity_number",
    "tckn",
    "TCKN",
    "gsmNumber",
    "gsm_number",
    "phone",
    "phoneNumber",
    "phone_number",
    "email",
    "buyerEmail",
    "buyer_email",
    "registrationAddress",
    "registration_address",
    "billingAddress",
    "billing_address",
    "shippingAddress",
    "shipping_address",
})


def sanitize_log_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize a dict for logging.

    Recursively masks card data, API credentials, and PII (TCKN, phone,
    email, address). The PII set was expanded in v0.4.0 to cover KVKK
    Article 12 / GDPR Article 32 expectations for log hygiene.

    Args:
        data: Data to sanitize. Non-dicts return ``{}``.

    Returns:
        Copy of ``data`` with sensitive values replaced by
        ``"***REDACTED***"``. Address dicts are replaced wholesale rather
        than walked, because nested address fields (street, postal code)
        are also identifying.
    """
    if not isinstance(data, dict):
        return {}  # type: ignore[unreachable]

    sanitized = data.copy()

    for field in _LOG_SENSITIVE_FIELDS:
        if field in sanitized:
            sanitized[field] = "***REDACTED***"

    # Recursively sanitize nested dicts
    for key, value in sanitized.items():
        if isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_log_data(item) if isinstance(item, dict) else item for item in value
            ]

    return sanitized


def build_iyzico_signature_string(data: dict[str, Any], secret_key: str) -> str:
    """
    Build the exact string iyzico signs for a webhook (X-IYZ-SIGNATURE-V3).

    iyzico's notification signature is **not** an HMAC over the raw JSON
    body. It is HMAC-SHA256 (hex) over an ordered *concatenation* (no
    separator) of specific event field values, where the merchant secret
    key is both the first element of the concatenation **and** the HMAC
    key. The field order depends on the notification type:

    - Payment (default/IYZICO format)::

        secretKey + iyziEventType + paymentId + paymentConversationId + status

    - Payment (HPP/checkout-form format, identified by a ``token`` field)::

        secretKey + iyziEventType + iyziPaymentId + token + paymentConversationId + status

    - Subscription (identified by ``subscriptionReferenceCode``)::

        merchantId + secretKey + eventType + subscriptionReferenceCode
            + orderReferenceCode + customerReferenceCode

    Missing fields are treated as empty strings, matching iyzico's
    behaviour of concatenating whatever values are present in the event.

    Reference: https://docs.iyzico.com/en/advanced/webhook

    Args:
        data: Parsed webhook JSON body.
        secret_key: Merchant secret key (``IYZICO_SECRET_KEY``).

    Returns:
        The string whose HMAC-SHA256 (keyed by ``secret_key``) iyzico
        sends in the ``X-IYZ-SIGNATURE-V3`` header.
    """

    def _s(key: str) -> str:
        value = data.get(key)
        return "" if value is None else str(value)

    # Subscription notifications.
    if data.get("subscriptionReferenceCode") is not None:
        return (
            _s("merchantId")
            + secret_key
            + _s("iyziEventType")
            + _s("subscriptionReferenceCode")
            + _s("orderReferenceCode")
            + _s("customerReferenceCode")
        )

    # Hosted-payment-page / checkout-form notifications carry a token.
    if data.get("token") is not None:
        return (
            secret_key
            + _s("iyziEventType")
            + _s("iyziPaymentId")
            + _s("token")
            + _s("paymentConversationId")
            + _s("status")
        )

    # Default direct payment notification.
    return (
        secret_key
        + _s("iyziEventType")
        + _s("paymentId")
        + _s("paymentConversationId")
        + _s("status")
    )


def compute_iyzico_webhook_signature(data: dict[str, Any], secret_key: str) -> str:
    """
    Compute the iyzico ``X-IYZ-SIGNATURE-V3`` value for a parsed webhook.

    See :func:`build_iyzico_signature_string` for the exact scheme.

    Args:
        data: Parsed webhook JSON body.
        secret_key: Merchant secret key (``IYZICO_SECRET_KEY``).

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    msg = build_iyzico_signature_string(data, secret_key).encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_iyzico_webhook_signature(
    data: dict[str, Any], signature: str, secret_key: str
) -> bool:
    """
    Verify an iyzico ``X-IYZ-SIGNATURE-V3`` webhook signature. Fail-closed.

    This implements iyzico's *actual* notification-signature algorithm
    (ordered field concatenation keyed by the merchant secret key — see
    :func:`build_iyzico_signature_string`), which is what genuine iyzico
    traffic uses. Earlier versions HMAC'd the raw JSON body keyed by a
    separate ``IYZICO_WEBHOOK_SECRET``; that scheme can never match a real
    iyzico signature.

    Args:
        data: Parsed webhook JSON body.
        signature: Value of the ``X-IYZ-SIGNATURE-V3`` request header.
        secret_key: Merchant secret key (``IYZICO_SECRET_KEY``). Must be
            non-empty; an empty key fails closed.

    Returns:
        ``True`` only if the computed signature matches ``signature``
        using a constant-time comparison.
    """
    if not secret_key:
        logger.error(
            "Webhook signature verification rejected: no secret key configured. "
            "Set IYZICO_SECRET_KEY to verify iyzico webhook signatures."
        )
        return False

    if not signature:
        logger.warning("Webhook signature missing")
        return False

    try:
        expected = compute_iyzico_webhook_signature(data, secret_key)
        is_valid = hmac.compare_digest(signature, expected)
        if not is_valid:
            logger.warning("Webhook signature mismatch")
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


def verify_webhook_signature(
    payload: bytes | dict[str, Any], signature: str, secret: str
) -> bool:
    """
    Verify an iyzico webhook signature (``X-IYZ-SIGNATURE-V3``). Fail-closed.

    .. warning::

        **Behaviour change (security fix).** Previous versions computed an
        HMAC-SHA256 over the *raw request body* keyed by a separate
        ``IYZICO_WEBHOOK_SECRET``. iyzico does not sign the raw body — it
        signs an ordered concatenation of specific event fields keyed by
        the merchant **secret key** (see
        :func:`build_iyzico_signature_string`). The old scheme could never
        match a genuine iyzico signature, so it either rejected every real
        webhook or was disabled, leaving the endpoint unauthenticated.

        This function now implements iyzico's real scheme. Pass the
        merchant ``IYZICO_SECRET_KEY`` as ``secret`` (the shipped
        ``webhook_view`` does this automatically) and read the signature
        from the ``X-IYZ-SIGNATURE-V3`` header.

    Returns ``False`` (not ``True``) when ``secret`` is empty — fail-closed.

    Args:
        payload: Raw request body (``bytes``) or an already-parsed dict.
        signature: Value of the ``X-IYZ-SIGNATURE-V3`` header.
        secret: Merchant secret key (``IYZICO_SECRET_KEY``). Must be
            non-empty.

    Returns:
        ``True`` only if the signature matches iyzico's computed value.
    """
    if not secret:
        logger.error(
            "Webhook signature verification rejected: no secret configured. "
            "Set IYZICO_SECRET_KEY to accept webhooks."
        )
        return False

    if not signature:
        logger.warning("Webhook signature missing")
        return False

    if isinstance(payload, dict):
        data = payload
    else:
        try:
            import json

            data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        except Exception as e:
            logger.error(f"Error parsing webhook payload for signature verification: {e}")
            return False

    return verify_iyzico_webhook_signature(data, signature, secret)


def is_ip_allowed(ip_address: str, allowed_ips: list[str]) -> bool:
    """
    Check if IP address is in whitelist.

    Supports both individual IPs and CIDR notation.

    Args:
        ip_address: IP address to check
        allowed_ips: List of allowed IP addresses/ranges

    Returns:
        True if IP is allowed, False otherwise

    Example:
        >>> is_ip_allowed("127.0.0.1", ["127.0.0.1", "192.168.1.0/24"])
        True
        >>> is_ip_allowed("10.0.0.1", ["127.0.0.1"])
        False
        >>> is_ip_allowed("192.168.1.50", ["192.168.1.0/24"])
        True
    """
    if not allowed_ips:
        # If no IP whitelist is configured, allow all
        logger.debug("No IP whitelist configured, allowing all IPs")
        return True

    try:
        ip = ipaddress.ip_address(ip_address)

        for allowed in allowed_ips:
            try:
                # Try as network (CIDR)
                if "/" in allowed:
                    network = ipaddress.ip_network(allowed, strict=False)
                    if ip in network:
                        logger.debug(f"IP {ip_address} allowed by network {allowed}")
                        return True
                # Try as individual IP
                else:
                    if ip == ipaddress.ip_address(allowed):
                        logger.debug(f"IP {ip_address} allowed")
                        return True
            except ValueError as e:
                logger.warning(f"Invalid IP/network in whitelist: {allowed} - {e}")
                continue

        logger.warning(f"IP {ip_address} not in whitelist")
        return False

    except ValueError as e:
        logger.error(f"Invalid IP address: {ip_address} - {e}")
        return False


def calculate_installment_amount(
    total_amount: Decimal,
    installments: int,
    interest_rate: Decimal = Decimal("0"),
) -> Decimal:
    """
    Calculate monthly installment amount.

    Args:
        total_amount: Total payment amount
        installments: Number of installments
        interest_rate: Interest rate per installment as percentage (default: 0)

    Returns:
        Monthly installment amount (rounded to 2 decimal places)

    Raises:
        ValidationError: If parameters are invalid

    Example:
        >>> calculate_installment_amount(Decimal("1000"), 1)
        Decimal('1000.00')
        >>> calculate_installment_amount(Decimal("1000"), 10)
        Decimal('100.00')
        >>> calculate_installment_amount(Decimal("1000"), 10, Decimal("2"))
        Decimal('120.00')
    """
    # Validate inputs
    if total_amount <= 0:
        raise ValidationError(
            "Total amount must be greater than zero",
            error_code="INVALID_AMOUNT",
        )

    if installments < 1:
        raise ValidationError(
            "Installments must be at least 1",
            error_code="INVALID_INSTALLMENTS",
        )

    if interest_rate < 0:
        raise ValidationError(
            "Interest rate cannot be negative",
            error_code="INVALID_INTEREST_RATE",
        )

    # Single payment (no installments)
    if installments == 1:
        return total_amount.quantize(Decimal("0.01"))

    # Calculate with interest
    if interest_rate > 0:
        # Convert percentage to decimal (e.g., 2% -> 0.02)
        rate_decimal = interest_rate / 100
        # Calculate total with interest: total + (total * rate * installments)
        total_with_interest = total_amount * (1 + rate_decimal * installments)
        monthly_amount = total_with_interest / installments
    else:
        # Without interest, simply divide
        monthly_amount = total_amount / installments

    return monthly_amount.quantize(Decimal("0.01"))


def generate_basket_id(prefix: str = "B") -> str:
    """
    Generate unique basket ID for transactions.

    Args:
        prefix: Prefix for basket ID (default: "B")

    Returns:
        Unique basket ID in format: {prefix}{timestamp}{uuid}

    Example:
        >>> basket_id = generate_basket_id("B")
        >>> basket_id.startswith("B")
        True
        >>> len(basket_id) > 10
        True
        >>> basket_id1 = generate_basket_id()
        >>> basket_id2 = generate_basket_id()
        >>> basket_id1 != basket_id2
        True
    """
    if not prefix:
        prefix = "B"

    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8].upper()

    return f"{prefix}{timestamp}{unique_id}"


def calculate_paid_price_with_installments(
    base_price: Decimal,
    installments: int,
    installment_rates: dict[int, Decimal] | None = None,
) -> Decimal:
    """
    Calculate total paid price including installment fees.

    Args:
        base_price: Base payment amount
        installments: Number of installments
        installment_rates: Dictionary mapping installments to interest rates
                          (e.g., {3: Decimal("1.5"), 6: Decimal("2.0")})

    Returns:
        Total paid price with installment fees

    Example:
        >>> rates = {3: Decimal("1.5"), 6: Decimal("2.0")}
        >>> calculate_paid_price_with_installments(Decimal("1000"), 1, rates)
        Decimal('1000.00')
        >>> calculate_paid_price_with_installments(Decimal("1000"), 3, rates)
        Decimal('1045.00')
        >>> calculate_paid_price_with_installments(Decimal("1000"), 6, rates)
        Decimal('1120.00')
    """
    if installments <= 1:
        return base_price.quantize(Decimal("0.01"))

    if not installment_rates or installments not in installment_rates:
        # No interest rate defined, return base price
        return base_price.quantize(Decimal("0.01"))

    # Get interest rate for this installment count
    rate = installment_rates[installments]

    # Calculate total: base_price * (1 + rate/100 * installments)
    total = base_price * (1 + (rate / 100) * installments)

    return total.quantize(Decimal("0.01"))


def get_client_ip(request: Any, trust_xff: bool | None = None) -> str:
    """
    Get client IP address from Django request.

    Uses REMOTE_ADDR by default (set by the WSGI server / reverse proxy),
    which is the only trustworthy source. X-Forwarded-For is only read
    when explicitly enabled via IYZICO_TRUST_X_FORWARDED_FOR, and even
    then the extracted IP is validated for format correctness.

    Args:
        request: Django HttpRequest object
        trust_xff: Whether to trust X-Forwarded-For header.
                   If None, uses iyzico_settings.trust_x_forwarded_for.
                   Set to False to always use REMOTE_ADDR (recommended).

    Returns:
        Client IP address string (empty string if not available)

    Security Note:
        X-Forwarded-For is user-controllable and trivially spoofed.
        Only set trust_xff=True if your application is behind a trusted
        reverse proxy (e.g., nginx, AWS ALB) that overwrites the header.
        For robust IP detection behind proxies, consider django-ipware
        with TRUSTED_PROXY_LIST configured.

    Example:
        >>> from payments_tr.providers.iyzico.utils import get_client_ip
        >>> ip = get_client_ip(request)
        >>> refund_response = payment.process_refund(ip_address=ip)
    """
    from .settings import iyzico_settings

    if trust_xff is None:
        trust_xff = iyzico_settings.trust_x_forwarded_for

    if trust_xff:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            # Take the first IP in the chain (client IP from trusted proxy)
            raw = x_forwarded_for.split(",")[0].strip()
            candidate_ip = _strip_port_and_brackets(raw)
            # Validate that extracted value is actually a valid IP address
            # to prevent injection of arbitrary strings via spoofed headers
            try:
                ipaddress.ip_address(candidate_ip)
                return candidate_ip
            except ValueError:
                logger.warning(
                    f"Invalid IP in X-Forwarded-For header: "
                    f"{candidate_ip[:50]}... - falling back to REMOTE_ADDR"
                )

    return cast(str, request.META.get("REMOTE_ADDR", ""))


def _strip_port_and_brackets(candidate: str) -> str:
    """
    Normalize an X-Forwarded-For entry into a bare IP address.

    Some proxies (AWS ALB, certain nginx configs) emit forms like
    ``203.0.113.5:54321`` or ``[2001:db8::1]:8080``. ``ipaddress.ip_address``
    rejects both, so we strip the optional bracketed-IPv6 wrapper and an
    appended ``:port`` (only when unambiguous — bare IPv6 contains many
    colons and must not be touched).

    Args:
        candidate: Raw token from the XFF header.

    Returns:
        Token with bracket/port noise removed; format validation is left
        to the caller.
    """
    if candidate.startswith("["):
        end = candidate.find("]")
        if end != -1:
            return candidate[1:end]
    # Single colon means IPv4:port (bare IPv6 always has multiple).
    if candidate.count(":") == 1:
        return candidate.rsplit(":", 1)[0]
    return candidate
