"""
Iyzico sub-merchant lifecycle client.

Wraps the official ``iyzipay.SubMerchant`` SDK class with the same Django-
friendly conventions as :class:`IyzicoClient`:

- Dataclass response objects (:class:`SubMerchantResponse`).
- Translation of transport failures into :class:`PaymentError`.
- Reuse of the package's TR validators
  (:func:`validate_iban_tr`, :func:`validate_tckn`, :func:`validate_vkn`)
  for IBAN/TCKN/VKN inputs — failures surface as
  :class:`ValidationError` with a human-readable message.

The marketplace flow ("işyeri gelir paylaşımı") requires registering each
seller as a sub-merchant before a payment can route revenue to them. Three
operations are supported: ``create``, ``update`` and ``retrieve``. There is
no ``delete`` endpoint in Iyzico's marketplace API — disabled sellers
should simply stop being passed as ``subMerchantKey`` in basket items.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import iyzipay

from payments_tr.validation.turkish import (
    ValidationError as _TurkishValidationError,
)
from payments_tr.validation.turkish import (
    validate_iban_tr,
    validate_tckn,
    validate_vkn,
)

from .exceptions import PaymentError, ValidationError
from .settings import iyzico_settings
from .utils import parse_iyzico_response, sanitize_log_data

logger = logging.getLogger(__name__)


class SubMerchantType(str, Enum):
    """
    Iyzico sub-merchant legal types.

    Each type has different required fields:

    - :attr:`PERSONAL`: requires ``identity_number`` (TCKN).
    - :attr:`PRIVATE_COMPANY` and :attr:`LIMITED_OR_JOINT_STOCK_COMPANY`:
      require ``tax_office`` and ``tax_number`` (VKN).
    """

    PERSONAL = "PERSONAL"
    PRIVATE_COMPANY = "PRIVATE_COMPANY"
    LIMITED_OR_JOINT_STOCK_COMPANY = "LIMITED_OR_JOINT_STOCK_COMPANY"


@dataclass(frozen=True, slots=True)
class SubMerchantResponse:
    """
    Result of a sub-merchant lifecycle call.

    Attributes:
        is_successful: Whether Iyzico reported ``status == "success"``.
        sub_merchant_key: The Iyzico-issued key for this seller (set on
            ``create`` success and on subsequent ``retrieve`` / ``update``
            responses).
        error_code: Iyzico-issued error code on failure.
        error_message: Iyzico-issued human-readable message on failure.
        raw: Parsed response dict from the SDK, after sanitisation.
    """

    is_successful: bool
    sub_merchant_key: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


# Fields whose values must pass a TR-specific validator. Mapping of
# kwarg name → (validator, field-label) used for both ``create`` and
# ``update``. Kept module-level so it stays a single source of truth.
_TR_FIELD_VALIDATORS = {
    "iban": (validate_iban_tr, "IBAN"),
    "identity_number": (validate_tckn, "TCKN"),
    "tax_number": (validate_vkn, "VKN"),
}


def _validate_tr_field(name: str, value: str) -> None:
    """Run the TR validator for ``name`` and surface a clean error."""
    validator, label = _TR_FIELD_VALIDATORS[name]
    try:
        validator(value, raise_exception=True)
    except _TurkishValidationError as e:
        raise ValidationError(
            f"Invalid {label}: {e.message}",
            error_code=f"INVALID_{label}",
        ) from e


def _validate_type_specific_required_fields(
    sub_merchant_type: SubMerchantType,
    *,
    identity_number: str | None,
    tax_office: str | None,
    tax_number: str | None,
) -> None:
    """
    Enforce the type-conditional required fields documented by Iyzico.

    PERSONAL sub-merchants must supply a TCKN (``identity_number``);
    company types must supply both a tax office and a VKN
    (``tax_number``). The fields are not symmetric — PERSONAL does not
    require ``tax_number`` even though Iyzico will accept one. We follow
    the documented requirement, not the looser API behaviour.
    """
    if sub_merchant_type == SubMerchantType.PERSONAL:
        if not identity_number:
            raise ValidationError(
                "PERSONAL sub-merchants require identity_number (TCKN)",
                error_code="SUBMERCHANT_MISSING_TCKN",
            )
    else:  # PRIVATE_COMPANY / LIMITED_OR_JOINT_STOCK_COMPANY
        if not tax_office:
            raise ValidationError(
                f"{sub_merchant_type.value} sub-merchants require tax_office",
                error_code="SUBMERCHANT_MISSING_TAX_OFFICE",
            )
        if not tax_number:
            raise ValidationError(
                f"{sub_merchant_type.value} sub-merchants require tax_number (VKN)",
                error_code="SUBMERCHANT_MISSING_VKN",
            )


# Mapping from Python kwarg names to the camelCase keys Iyzico expects.
# Used in ``update()`` to pass through only the fields the caller chose.
_UPDATE_FIELD_MAP = {
    "sub_merchant_type": "subMerchantType",
    "legal_company_title": "legalCompanyTitle",
    "contact_name": "contactName",
    "contact_surname": "contactSurname",
    "email": "email",
    "gsm_number": "gsmNumber",
    "iban": "iban",
    "identity_number": "identityNumber",
    "tax_office": "taxOffice",
    "tax_number": "taxNumber",
    "address": "address",
    "currency": "currency",
    "name": "name",
}


class SubMerchantClient:
    """
    Lifecycle client for Iyzico sub-merchants (marketplace sellers).

    Mirrors the existing :class:`IyzicoClient` style: takes optional
    ``settings`` for testing, raises :class:`PaymentError` on transport
    failure, and returns frozen dataclass responses.

    Example:
        >>> from payments_tr.providers.iyzico.submerchant import (
        ...     SubMerchantClient,
        ...     SubMerchantType,
        ... )
        >>> client = SubMerchantClient()
        >>> resp = client.create(
        ...     external_id="seller-42",
        ...     sub_merchant_type=SubMerchantType.LIMITED_OR_JOINT_STOCK_COMPANY,
        ...     legal_company_title="Acme Print AŞ",
        ...     contact_name="Aslı",
        ...     contact_surname="Yılmaz",
        ...     email="acme@example.com",
        ...     gsm_number="+905551234567",
        ...     iban="TR330006100519786457841326",
        ...     tax_office="Beşiktaş",
        ...     tax_number="1234567890",
        ... )
        >>> if resp.is_successful:
        ...     seller.iyzico_sub_merchant_key = resp.sub_merchant_key
    """

    def __init__(self, settings: Any = None) -> None:
        """
        Initialise client.

        Args:
            settings: Optional ``IyzicoSettings`` instance. When ``None``
                the global :data:`iyzico_settings` is used.
        """
        self.settings = settings or iyzico_settings
        self._options: dict[str, str] | None = None
        logger.debug("SubMerchantClient initialised")

    def get_options(self) -> dict[str, str]:
        """Return cached Iyzico API options (api_key/secret_key/base_url)."""
        if self._options is None:
            self._options = self.settings.get_options()
        return self._options

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    def create(
        self,
        external_id: str,
        sub_merchant_type: SubMerchantType,
        legal_company_title: str,
        contact_name: str,
        contact_surname: str,
        email: str,
        gsm_number: str,
        iban: str,
        identity_number: str | None = None,
        tax_office: str | None = None,
        tax_number: str | None = None,
        address: str = "",
        currency: str = "TRY",
        name: str | None = None,
    ) -> SubMerchantResponse:
        """
        Register a new sub-merchant.

        Args:
            external_id: Stable identifier from the caller's system —
                used by :meth:`retrieve` and as the conversation ID.
            sub_merchant_type: Legal type (PERSONAL / PRIVATE_COMPANY /
                LIMITED_OR_JOINT_STOCK_COMPANY).
            legal_company_title: Company / trader legal title.
            contact_name: Contact first name.
            contact_surname: Contact surname.
            email: Contact email.
            gsm_number: Contact GSM, ideally in ``+90...`` form.
            iban: Turkish IBAN — validated via
                :func:`validate_iban_tr`.
            identity_number: TCKN (required for PERSONAL) — validated
                via :func:`validate_tckn`.
            tax_office: Tax office name (required for company types).
            tax_number: VKN (required for company types) — validated
                via :func:`validate_vkn`.
            address: Postal address.
            currency: Settlement currency. v0.5.0 supports TRY only;
                callers may pass another value but Iyzico's marketplace
                flow is TR-only in practice.
            name: Optional ``name`` field (Iyzico schema). Defaults to
                ``legal_company_title`` if not specified.

        Returns:
            :class:`SubMerchantResponse` with ``sub_merchant_key`` populated
            on success.

        Raises:
            ValidationError: For missing/invalid fields.
            PaymentError: On transport failure.
        """
        if not external_id:
            raise ValidationError(
                "external_id is required for sub-merchant create",
                error_code="SUBMERCHANT_MISSING_EXTERNAL_ID",
            )
        if not isinstance(sub_merchant_type, SubMerchantType):
            raise ValidationError(
                "sub_merchant_type must be a SubMerchantType enum value",
                error_code="SUBMERCHANT_INVALID_TYPE",
            )

        _validate_type_specific_required_fields(
            sub_merchant_type,
            identity_number=identity_number,
            tax_office=tax_office,
            tax_number=tax_number,
        )

        # IBAN is always required and always TR-shaped in v0.5.0.
        _validate_tr_field("iban", iban)
        if identity_number:
            _validate_tr_field("identity_number", identity_number)
        if tax_number:
            _validate_tr_field("tax_number", tax_number)

        request_data: dict[str, Any] = {
            "locale": self.settings.locale,
            "conversationId": f"submerchant-create-{external_id}",
            "subMerchantExternalId": external_id,
            "subMerchantType": sub_merchant_type.value,
            "address": address,
            "contactName": contact_name,
            "contactSurname": contact_surname,
            "email": email,
            "gsmNumber": gsm_number,
            "name": name or legal_company_title,
            "iban": iban,
            "currency": currency,
            "legalCompanyTitle": legal_company_title,
        }
        if identity_number:
            request_data["identityNumber"] = identity_number
        if tax_office:
            request_data["taxOffice"] = tax_office
        if tax_number:
            request_data["taxNumber"] = tax_number

        logger.info(
            "Creating sub-merchant external_id=%s type=%s",
            external_id,
            sub_merchant_type.value,
        )
        logger.debug("Sub-merchant create payload: %s", sanitize_log_data(request_data))

        try:
            sub_merchant = iyzipay.SubMerchant()
            raw_response = sub_merchant.create(request_data, self.get_options())
        except Exception as e:
            logger.error("Sub-merchant create transport error: %s", e, exc_info=True)
            raise PaymentError(
                f"Sub-merchant create failed: {e}",
                error_code="SUBMERCHANT_CREATE_TRANSPORT_ERROR",
            ) from e

        return self._wrap_response(raw_response, op="create")

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(self, sub_merchant_key: str, **fields: Any) -> SubMerchantResponse:
        """
        Update fields on an existing sub-merchant.

        Only the fields supplied in ``**fields`` are sent to Iyzico — this
        keeps PATCH semantics on what is otherwise an upsert-shaped REST
        endpoint. Recognised kwargs are the snake_case form of the
        :meth:`create` parameters; unknown kwargs raise
        :class:`ValidationError` rather than being silently dropped.

        TR validators run on any of ``iban``, ``identity_number``,
        ``tax_number`` that are supplied.
        """
        if not sub_merchant_key:
            raise ValidationError(
                "sub_merchant_key is required for sub-merchant update",
                error_code="SUBMERCHANT_MISSING_KEY",
            )
        if not fields:
            raise ValidationError(
                "update() requires at least one field to change",
                error_code="SUBMERCHANT_UPDATE_NO_FIELDS",
            )

        unknown = set(fields).difference(_UPDATE_FIELD_MAP)
        if unknown:
            raise ValidationError(
                f"Unknown sub-merchant update field(s): {sorted(unknown)}",
                error_code="SUBMERCHANT_UNKNOWN_FIELD",
            )

        # Coerce SubMerchantType → str for transport.
        if "sub_merchant_type" in fields and isinstance(
            fields["sub_merchant_type"], SubMerchantType
        ):
            fields["sub_merchant_type"] = fields["sub_merchant_type"].value

        # Run TR validators on supplied fields only.
        for tr_field in _TR_FIELD_VALIDATORS:
            if tr_field in fields and fields[tr_field]:
                _validate_tr_field(tr_field, fields[tr_field])

        request_data: dict[str, Any] = {
            "locale": self.settings.locale,
            "conversationId": f"submerchant-update-{sub_merchant_key}",
            "subMerchantKey": sub_merchant_key,
        }
        for snake, value in fields.items():
            request_data[_UPDATE_FIELD_MAP[snake]] = value

        logger.info("Updating sub-merchant %s with fields=%s", sub_merchant_key, list(fields))
        logger.debug("Sub-merchant update payload: %s", sanitize_log_data(request_data))

        try:
            sub_merchant = iyzipay.SubMerchant()
            raw_response = sub_merchant.update(request_data, self.get_options())
        except Exception as e:
            logger.error("Sub-merchant update transport error: %s", e, exc_info=True)
            raise PaymentError(
                f"Sub-merchant update failed: {e}",
                error_code="SUBMERCHANT_UPDATE_TRANSPORT_ERROR",
            ) from e

        return self._wrap_response(raw_response, op="update")

    # ------------------------------------------------------------------
    # retrieve
    # ------------------------------------------------------------------

    def retrieve(self, external_id: str) -> SubMerchantResponse:
        """
        Retrieve a sub-merchant by the caller-side ``external_id``.

        Iyzico's retrieve endpoint keys off the merchant's external id,
        not the Iyzico-issued ``subMerchantKey`` — this matches the
        official SDK behaviour and is what callers expect when looking up
        a seller they registered under their own ID.
        """
        if not external_id:
            raise ValidationError(
                "external_id is required for sub-merchant retrieve",
                error_code="SUBMERCHANT_MISSING_EXTERNAL_ID",
            )

        request_data = {
            "locale": self.settings.locale,
            "conversationId": f"submerchant-retrieve-{external_id}",
            "subMerchantExternalId": external_id,
        }
        logger.info("Retrieving sub-merchant external_id=%s", external_id)

        try:
            sub_merchant = iyzipay.SubMerchant()
            raw_response = sub_merchant.retrieve(request_data, self.get_options())
        except Exception as e:
            logger.error("Sub-merchant retrieve transport error: %s", e, exc_info=True)
            raise PaymentError(
                f"Sub-merchant retrieve failed: {e}",
                error_code="SUBMERCHANT_RETRIEVE_TRANSPORT_ERROR",
            ) from e

        return self._wrap_response(raw_response, op="retrieve")

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_response(raw_response: Any, *, op: str) -> SubMerchantResponse:
        """Parse a raw SDK response into a :class:`SubMerchantResponse`."""
        parsed = parse_iyzico_response(raw_response)
        is_successful = parsed.get("status") == "success"
        sub_merchant_key = parsed.get("subMerchantKey")
        error_code = parsed.get("errorCode")
        error_message = parsed.get("errorMessage")

        if is_successful:
            logger.info(
                "Sub-merchant %s succeeded (key=%s)",
                op,
                sub_merchant_key,
            )
        else:
            logger.warning(
                "Sub-merchant %s failed - error_code=%s error_message=%s",
                op,
                error_code,
                error_message,
            )

        return SubMerchantResponse(
            is_successful=is_successful,
            sub_merchant_key=sub_merchant_key,
            error_code=error_code,
            error_message=error_message,
            raw=parsed,
        )
