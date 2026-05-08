"""
Tests for ``payments_tr.providers.iyzico.submerchant.SubMerchantClient``.

The Iyzico SDK is mocked at ``iyzipay.SubMerchant``, mirroring the
``iyzipay.Payment`` mocking style used in ``test_client.py``. We assert
both the validation surface (PERSONAL vs company required fields,
TCKN/IBAN/VKN checksum errors) and the request-building surface
(``update`` only sending changed fields, ``retrieve`` keying off
``external_id``).
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from payments_tr.providers.iyzico.exceptions import PaymentError, ValidationError
from payments_tr.providers.iyzico.submerchant import (
    SubMerchantClient,
    SubMerchantResponse,
    SubMerchantType,
)

# Known-valid TR identifiers (sourced from the public test vectors used
# in ``test_validation.py``).
VALID_TCKN = "10000000146"
VALID_IBAN = "TR330006100519786457841326"
VALID_VKN = "1234567890"


@pytest.fixture
def mock_submerchant_class():
    with patch("payments_tr.providers.iyzico.submerchant.iyzipay.SubMerchant") as cls:
        instance = Mock()
        instance.create.return_value = {
            "status": "success",
            "subMerchantKey": "smk-from-iyzico",
            "conversationId": "submerchant-create-seller-1",
        }
        instance.update.return_value = {
            "status": "success",
            "subMerchantKey": "smk-from-iyzico",
            "conversationId": "submerchant-update-smk-from-iyzico",
        }
        instance.retrieve.return_value = {
            "status": "success",
            "subMerchantKey": "smk-from-iyzico",
            "subMerchantExternalId": "seller-1",
            "name": "Acme Print",
        }
        cls.return_value = instance
        yield cls, instance


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------


class TestSubMerchantCreate:
    def test_personal_happy_path(self, mock_submerchant_class):
        client = SubMerchantClient()
        resp = client.create(
            external_id="seller-1",
            sub_merchant_type=SubMerchantType.PERSONAL,
            legal_company_title="Aslı Yılmaz",
            contact_name="Aslı",
            contact_surname="Yılmaz",
            email="asli@example.com",
            gsm_number="+905551234567",
            iban=VALID_IBAN,
            identity_number=VALID_TCKN,
        )
        assert resp.is_successful is True
        assert resp.sub_merchant_key == "smk-from-iyzico"
        assert isinstance(resp, SubMerchantResponse)

        _, instance = mock_submerchant_class
        sent = instance.create.call_args[0][0]
        assert sent["subMerchantType"] == "PERSONAL"
        assert sent["identityNumber"] == VALID_TCKN
        # Company-only fields should NOT have been sent.
        assert "taxOffice" not in sent
        assert "taxNumber" not in sent

    def test_company_happy_path(self, mock_submerchant_class):
        client = SubMerchantClient()
        resp = client.create(
            external_id="seller-2",
            sub_merchant_type=SubMerchantType.LIMITED_OR_JOINT_STOCK_COMPANY,
            legal_company_title="Acme Print AŞ",
            contact_name="Aslı",
            contact_surname="Yılmaz",
            email="acme@example.com",
            gsm_number="+905551234567",
            iban=VALID_IBAN,
            tax_office="Beşiktaş",
            tax_number=VALID_VKN,
        )
        assert resp.is_successful is True
        _, instance = mock_submerchant_class
        sent = instance.create.call_args[0][0]
        assert sent["subMerchantType"] == "LIMITED_OR_JOINT_STOCK_COMPANY"
        assert sent["taxOffice"] == "Beşiktaş"
        assert sent["taxNumber"] == VALID_VKN
        assert "identityNumber" not in sent

    def test_personal_without_identity_number_raises(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.create(
                external_id="seller-1",
                sub_merchant_type=SubMerchantType.PERSONAL,
                legal_company_title="Aslı",
                contact_name="Aslı",
                contact_surname="Yılmaz",
                email="a@b.com",
                gsm_number="+905551234567",
                iban=VALID_IBAN,
            )
        assert exc.value.error_code == "SUBMERCHANT_MISSING_TCKN"

    def test_company_without_tax_office_raises(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.create(
                external_id="seller-1",
                sub_merchant_type=SubMerchantType.PRIVATE_COMPANY,
                legal_company_title="Acme",
                contact_name="Aslı",
                contact_surname="Yılmaz",
                email="a@b.com",
                gsm_number="+905551234567",
                iban=VALID_IBAN,
                tax_number=VALID_VKN,
            )
        assert exc.value.error_code == "SUBMERCHANT_MISSING_TAX_OFFICE"

    def test_company_without_tax_number_raises(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.create(
                external_id="seller-1",
                sub_merchant_type=SubMerchantType.PRIVATE_COMPANY,
                legal_company_title="Acme",
                contact_name="Aslı",
                contact_surname="Yılmaz",
                email="a@b.com",
                gsm_number="+905551234567",
                iban=VALID_IBAN,
                tax_office="Beşiktaş",
            )
        assert exc.value.error_code == "SUBMERCHANT_MISSING_VKN"

    @pytest.mark.parametrize(
        "field,value,expected_code",
        [
            ("iban", "TR000000000000000000000000", "INVALID_IBAN"),
            ("identity_number", "12345678901", "INVALID_TCKN"),  # bad checksum
            ("tax_number", "1234567899", "INVALID_VKN"),  # bad checksum
        ],
    )
    def test_invalid_tr_identifiers(self, mock_submerchant_class, field, value, expected_code):
        client = SubMerchantClient()
        kwargs = {
            "external_id": "seller-1",
            "sub_merchant_type": (
                SubMerchantType.PERSONAL
                if field == "identity_number"
                else SubMerchantType.PRIVATE_COMPANY
            ),
            "legal_company_title": "Title",
            "contact_name": "X",
            "contact_surname": "Y",
            "email": "a@b.com",
            "gsm_number": "+905551234567",
            "iban": VALID_IBAN,
            "identity_number": VALID_TCKN,
            "tax_office": "Beşiktaş",
            "tax_number": VALID_VKN,
        }
        kwargs[field] = value
        with pytest.raises(ValidationError) as exc:
            client.create(**kwargs)
        assert exc.value.error_code == expected_code

    def test_missing_external_id(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.create(
                external_id="",
                sub_merchant_type=SubMerchantType.PERSONAL,
                legal_company_title="X",
                contact_name="X",
                contact_surname="Y",
                email="a@b.com",
                gsm_number="+905551234567",
                iban=VALID_IBAN,
                identity_number=VALID_TCKN,
            )
        assert exc.value.error_code == "SUBMERCHANT_MISSING_EXTERNAL_ID"

    def test_invalid_type_arg(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.create(
                external_id="seller-1",
                sub_merchant_type="PERSONAL",  # type: ignore[arg-type]
                legal_company_title="X",
                contact_name="X",
                contact_surname="Y",
                email="a@b.com",
                gsm_number="+905551234567",
                iban=VALID_IBAN,
                identity_number=VALID_TCKN,
            )
        assert exc.value.error_code == "SUBMERCHANT_INVALID_TYPE"

    def test_transport_failure_wraps_in_payment_error(self):
        with patch("payments_tr.providers.iyzico.submerchant.iyzipay.SubMerchant") as cls:
            instance = Mock()
            instance.create.side_effect = RuntimeError("network down")
            cls.return_value = instance

            client = SubMerchantClient()
            with pytest.raises(PaymentError) as exc:
                client.create(
                    external_id="seller-1",
                    sub_merchant_type=SubMerchantType.PERSONAL,
                    legal_company_title="X",
                    contact_name="X",
                    contact_surname="Y",
                    email="a@b.com",
                    gsm_number="+905551234567",
                    iban=VALID_IBAN,
                    identity_number=VALID_TCKN,
                )
            assert exc.value.error_code == "SUBMERCHANT_CREATE_TRANSPORT_ERROR"

    def test_failure_response_returned_not_raised(self):
        with patch("payments_tr.providers.iyzico.submerchant.iyzipay.SubMerchant") as cls:
            instance = Mock()
            instance.create.return_value = {
                "status": "failure",
                "errorCode": "9999",
                "errorMessage": "Already exists",
            }
            cls.return_value = instance

            client = SubMerchantClient()
            resp = client.create(
                external_id="seller-1",
                sub_merchant_type=SubMerchantType.PERSONAL,
                legal_company_title="X",
                contact_name="X",
                contact_surname="Y",
                email="a@b.com",
                gsm_number="+905551234567",
                iban=VALID_IBAN,
                identity_number=VALID_TCKN,
            )
            # Application-level failures stay in-band — caller can read
            # error_code without try/except. Mirrors RefundResponse.
            assert resp.is_successful is False
            assert resp.error_code == "9999"
            assert resp.sub_merchant_key is None


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


class TestSubMerchantUpdate:
    def test_only_supplied_fields_are_sent(self, mock_submerchant_class):
        client = SubMerchantClient()
        resp = client.update("smk-from-iyzico", iban=VALID_IBAN)
        assert resp.is_successful is True

        _, instance = mock_submerchant_class
        sent = instance.update.call_args[0][0]
        # Required overhead fields are always present:
        assert sent["subMerchantKey"] == "smk-from-iyzico"
        assert sent["iban"] == VALID_IBAN
        # NOT sent — caller didn't supply them:
        assert "contactName" not in sent
        assert "taxNumber" not in sent
        assert "subMerchantType" not in sent

    def test_unknown_field_rejected(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.update("smk", foo="bar")
        assert exc.value.error_code == "SUBMERCHANT_UNKNOWN_FIELD"

    def test_no_fields_rejected(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.update("smk")
        assert exc.value.error_code == "SUBMERCHANT_UPDATE_NO_FIELDS"

    def test_missing_key_rejected(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.update("", iban=VALID_IBAN)
        assert exc.value.error_code == "SUBMERCHANT_MISSING_KEY"

    def test_invalid_iban_in_update_validated(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.update("smk", iban="TR0000")
        assert exc.value.error_code == "INVALID_IBAN"

    def test_sub_merchant_type_enum_coerced_to_str(self, mock_submerchant_class):
        client = SubMerchantClient()
        client.update("smk", sub_merchant_type=SubMerchantType.PRIVATE_COMPANY)

        _, instance = mock_submerchant_class
        sent = instance.update.call_args[0][0]
        assert sent["subMerchantType"] == "PRIVATE_COMPANY"


# ---------------------------------------------------------------------------
# retrieve()
# ---------------------------------------------------------------------------


class TestSubMerchantRetrieve:
    def test_retrieve_keys_off_external_id(self, mock_submerchant_class):
        client = SubMerchantClient()
        resp = client.retrieve("seller-1")
        assert resp.is_successful is True
        assert resp.sub_merchant_key == "smk-from-iyzico"

        _, instance = mock_submerchant_class
        sent = instance.retrieve.call_args[0][0]
        assert sent["subMerchantExternalId"] == "seller-1"

    def test_retrieve_missing_external_id(self, mock_submerchant_class):
        client = SubMerchantClient()
        with pytest.raises(ValidationError) as exc:
            client.retrieve("")
        assert exc.value.error_code == "SUBMERCHANT_MISSING_EXTERNAL_ID"

    def test_retrieve_transport_failure(self):
        with patch("payments_tr.providers.iyzico.submerchant.iyzipay.SubMerchant") as cls:
            instance = Mock()
            instance.retrieve.side_effect = ConnectionError("dns broke")
            cls.return_value = instance

            client = SubMerchantClient()
            with pytest.raises(PaymentError) as exc:
                client.retrieve("seller-1")
            assert exc.value.error_code == "SUBMERCHANT_RETRIEVE_TRANSPORT_ERROR"


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestSubMerchantType:
    def test_enum_values(self):
        assert SubMerchantType.PERSONAL.value == "PERSONAL"
        assert SubMerchantType.PRIVATE_COMPANY.value == "PRIVATE_COMPANY"
        assert (
            SubMerchantType.LIMITED_OR_JOINT_STOCK_COMPANY.value == "LIMITED_OR_JOINT_STOCK_COMPANY"
        )

    def test_string_compat(self):
        # str-Enum subclass — useful for callers building dicts directly.
        assert SubMerchantType.PERSONAL == "PERSONAL"


class TestSubMerchantResponseDataclass:
    def test_default_raw_is_dict(self):
        # Frozen dataclass with default_factory dict for ``raw``.
        resp = SubMerchantResponse(is_successful=True)
        assert resp.raw == {}
        assert resp.sub_merchant_key is None
        assert resp.error_code is None
