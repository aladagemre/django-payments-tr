"""
Tests for ``payments_tr.providers.iyzico.models.AbstractSubMerchantOwner``.

The mixin is an abstract Django model — we test ``clean()`` validation
behaviour without going through the database. This keeps the test fast
and avoids forcing a migration on consumers who don't use marketplace.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models

from payments_tr.providers.iyzico.models import AbstractSubMerchantOwner


class _Seller(AbstractSubMerchantOwner):
    """Concrete subclass — declared in test for isolation."""

    name = models.CharField(max_length=100)

    class Meta(AbstractSubMerchantOwner.Meta):
        abstract = True
        app_label = "tests"


# Known-valid TR identifiers (same vectors as test_submerchant_client.py).
VALID_TCKN = "10000000146"
VALID_IBAN = "TR330006100519786457841326"
VALID_VKN = "1234567890"


def _make(**fields):
    """Build a _Seller-like instance bypassing model setup."""
    seller = _Seller.__new__(_Seller)
    # Default all mixin CharFields to "" — Django's CharField default
    # before save().
    for f in (
        "iyzico_sub_merchant_key",
        "iyzico_sub_merchant_type",
        "iyzico_external_id",
        "iyzico_iban",
        "iyzico_identity_number",
        "iyzico_tax_office",
        "iyzico_tax_number",
        "iyzico_legal_company_title",
    ):
        setattr(seller, f, "")
    seller.name = "Acme"  # type: ignore[assignment]  # CharField descriptor at class level, str at instance
    for k, v in fields.items():
        setattr(seller, k, v)
    return seller


class TestAbstractSubMerchantOwnerClean:
    def test_blank_fields_are_valid(self):
        # An owner without any sub-merchant info should clean cleanly —
        # marketplace registration is optional.
        seller = _make()
        seller.clean()

    def test_personal_happy_path(self):
        seller = _make(
            iyzico_sub_merchant_type="PERSONAL",
            iyzico_iban=VALID_IBAN,
            iyzico_identity_number=VALID_TCKN,
        )
        seller.clean()

    def test_company_happy_path(self):
        seller = _make(
            iyzico_sub_merchant_type="LIMITED_OR_JOINT_STOCK_COMPANY",
            iyzico_iban=VALID_IBAN,
            iyzico_tax_office="Beşiktaş",
            iyzico_tax_number=VALID_VKN,
        )
        seller.clean()

    def test_personal_missing_tckn(self):
        seller = _make(
            iyzico_sub_merchant_type="PERSONAL",
            iyzico_iban=VALID_IBAN,
        )
        with pytest.raises(DjangoValidationError) as exc:
            seller.clean()
        assert "iyzico_identity_number" in exc.value.error_dict

    def test_company_missing_tax_office(self):
        seller = _make(
            iyzico_sub_merchant_type="PRIVATE_COMPANY",
            iyzico_iban=VALID_IBAN,
            iyzico_tax_number=VALID_VKN,
        )
        with pytest.raises(DjangoValidationError) as exc:
            seller.clean()
        assert "iyzico_tax_office" in exc.value.error_dict

    def test_company_missing_tax_number(self):
        seller = _make(
            iyzico_sub_merchant_type="PRIVATE_COMPANY",
            iyzico_iban=VALID_IBAN,
            iyzico_tax_office="Beşiktaş",
        )
        with pytest.raises(DjangoValidationError) as exc:
            seller.clean()
        assert "iyzico_tax_number" in exc.value.error_dict

    def test_invalid_iban(self):
        seller = _make(
            iyzico_sub_merchant_type="PERSONAL",
            iyzico_iban="TR0000",
            iyzico_identity_number=VALID_TCKN,
        )
        with pytest.raises(DjangoValidationError) as exc:
            seller.clean()
        assert "iyzico_iban" in exc.value.error_dict

    def test_invalid_tckn(self):
        seller = _make(
            iyzico_sub_merchant_type="PERSONAL",
            iyzico_iban=VALID_IBAN,
            iyzico_identity_number="12345678901",  # bad checksum
        )
        with pytest.raises(DjangoValidationError) as exc:
            seller.clean()
        assert "iyzico_identity_number" in exc.value.error_dict

    def test_invalid_vkn(self):
        seller = _make(
            iyzico_sub_merchant_type="PRIVATE_COMPANY",
            iyzico_iban=VALID_IBAN,
            iyzico_tax_office="Beşiktaş",
            iyzico_tax_number="1234567899",  # bad checksum
        )
        with pytest.raises(DjangoValidationError) as exc:
            seller.clean()
        assert "iyzico_tax_number" in exc.value.error_dict

    def test_has_iyzico_sub_merchant(self):
        assert _make().has_iyzico_sub_merchant() is False
        assert _make(iyzico_sub_merchant_key="smk-123").has_iyzico_sub_merchant() is True

    def test_choices_match_submerchant_type_enum(self):
        from payments_tr.providers.iyzico.submerchant import SubMerchantType

        choice_values = {c[0] for c in AbstractSubMerchantOwner.SUB_MERCHANT_TYPE_CHOICES}
        enum_values = {t.value for t in SubMerchantType}
        # Storage choices must mirror the wire-protocol enum, otherwise
        # callers can persist a value the API would reject.
        assert choice_values == enum_values
