"""
Tests for marketplace (sub-merchant) routing on Iyzico checkout-form requests.

Covers:
- Per-item validation of subMerchantKey / subMerchantPrice.
- Mixed baskets (some items marketplace, some not) — accepted unless
  ``marketplace=True`` is set.
- Cross-item invariants (sum of subMerchantPrice <= paidPrice).
- Provider-level ``marketplace=True`` opt-in including the rejected
  default-basket fallback.

The Iyzico SDK is mocked at ``iyzipay.CheckoutFormInitialize`` for the
client-level tests, mirroring the existing ``test_client.py`` style.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from payments_tr.providers.iyzico.client import (
    IyzicoClient,
    validate_marketplace_basket,
)
from payments_tr.providers.iyzico.exceptions import ValidationError
from payments_tr.providers.iyzico.provider import IyzicoProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def order_data():
    """Three-item order at 90.00 TRY total."""
    return {
        "conversationId": "test-conv-mkt-1",
        "price": "90.00",
        "paidPrice": "90.00",
        "currency": "TRY",
        "basketId": "B-mkt-1",
    }


@pytest.fixture
def buyer():
    return {
        "id": "BY-mkt-1",
        "name": "Aslı",
        "surname": "Yılmaz",
        "email": "asli@example.com",
        "identityNumber": "11111111111",
        "registrationAddress": "Test Address",
        "city": "Istanbul",
        "country": "Turkey",
        "gsmNumber": "+905551234567",
    }


@pytest.fixture
def billing_address():
    return {
        "address": "Address line 1",
        "city": "Istanbul",
        "country": "Turkey",
        "zipCode": "34000",
    }


@pytest.fixture
def marketplace_basket():
    """3-item basket, all marketplace-routed, total price 90, sub total 81."""
    return [
        {
            "id": "f1",
            "name": "File 1",
            "category1": "Print",
            "itemType": "PHYSICAL",
            "price": "30.00",
            "subMerchantKey": "smk-A",
            "subMerchantPrice": "27.00",
        },
        {
            "id": "f2",
            "name": "File 2",
            "category1": "Print",
            "itemType": "PHYSICAL",
            "price": "30.00",
            "subMerchantKey": "smk-A",
            "subMerchantPrice": "27.00",
        },
        {
            "id": "f3",
            "name": "File 3",
            "category1": "Print",
            "itemType": "PHYSICAL",
            "price": "30.00",
            "subMerchantKey": "smk-A",
            "subMerchantPrice": "27.00",
        },
    ]


@pytest.fixture
def mock_checkout_form():
    """Patch CheckoutFormInitialize and return success."""
    with patch("payments_tr.providers.iyzico.client.iyzipay.CheckoutFormInitialize") as cls:
        instance = Mock()
        instance.create.return_value = {
            "status": "success",
            "token": "checkout-token-mkt",
            "checkoutFormContent": "<div/>",
            "paymentPageUrl": "https://example/checkout",
            "conversationId": "test-conv-mkt-1",
        }
        cls.return_value = instance
        yield cls, instance


# ---------------------------------------------------------------------------
# validate_marketplace_basket — pure function unit tests
# ---------------------------------------------------------------------------


class TestValidateMarketplaceBasket:
    def test_empty_basket_is_noop(self):
        validate_marketplace_basket([], "10.00")

    def test_no_marketplace_fields_is_noop(self):
        validate_marketplace_basket([{"id": "x", "price": "10.00"}], "10.00")

    def test_happy_path_three_items(self, marketplace_basket):
        # All within bounds; sum 81 <= 90.
        validate_marketplace_basket(marketplace_basket, "90.00")

    def test_strict_rejects_mixed_basket(self, marketplace_basket):
        mixed = marketplace_basket + [{"id": "f4", "price": "10.00"}]
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(mixed, "100.00", strict=True)
        assert exc.value.error_code == "MARKETPLACE_ITEM_MISSING_SUBMERCHANT"

    def test_non_strict_accepts_mixed_basket(self, marketplace_basket):
        # Mixed basket allowed when strict=False; sum is still validated.
        mixed = marketplace_basket + [{"id": "f4", "price": "10.00"}]
        validate_marketplace_basket(mixed, "100.00")

    def test_sub_merchant_price_exceeds_item_price(self, marketplace_basket):
        marketplace_basket[0]["subMerchantPrice"] = "31.00"  # > 30 item price
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(marketplace_basket, "90.00")
        assert exc.value.error_code == "MARKETPLACE_SUBMERCHANT_EXCEEDS_ITEM_PRICE"

    def test_sub_merchant_price_sum_exceeds_paid_price(self, marketplace_basket):
        # Each subMerchantPrice = 27 (sum 81). Bump paidPrice down to 80.
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(marketplace_basket, "80.00")
        assert exc.value.error_code == "MARKETPLACE_SUBMERCHANT_SUM_EXCEEDS_PAID_PRICE"

    def test_key_present_without_price(self):
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [{"id": "f1", "price": "10.00", "subMerchantKey": "smk"}],
                "10.00",
            )
        assert exc.value.error_code == "MARKETPLACE_FIELDS_INCOMPLETE"

    def test_price_present_without_key(self):
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [{"id": "f1", "price": "10.00", "subMerchantPrice": "5.00"}],
                "10.00",
            )
        assert exc.value.error_code == "MARKETPLACE_FIELDS_INCOMPLETE"

    def test_empty_string_sub_merchant_key_rejected(self):
        # Empty string is treated as "no marketplace fields" — see
        # implementation note. So this becomes a missing-pair error in
        # non-strict mode (price set, key missing) rather than a separate
        # empty-key code.
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [
                    {
                        "id": "f1",
                        "price": "10.00",
                        "subMerchantKey": "",
                        "subMerchantPrice": "5.00",
                    }
                ],
                "10.00",
            )
        assert exc.value.error_code == "MARKETPLACE_FIELDS_INCOMPLETE"

    def test_whitespace_only_key_rejected(self):
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [
                    {
                        "id": "f1",
                        "price": "10.00",
                        "subMerchantKey": "   ",
                        "subMerchantPrice": "5.00",
                    }
                ],
                "10.00",
            )
        assert exc.value.error_code == "MARKETPLACE_EMPTY_SUBMERCHANT_KEY"

    def test_negative_sub_merchant_price(self):
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [
                    {
                        "id": "f1",
                        "price": "10.00",
                        "subMerchantKey": "smk",
                        "subMerchantPrice": "-1.00",
                    }
                ],
                "10.00",
            )
        assert exc.value.error_code == "MARKETPLACE_NEGATIVE_SUBMERCHANT_PRICE"

    def test_marketplace_item_missing_price(self):
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [
                    {
                        "id": "f1",
                        "subMerchantKey": "smk",
                        "subMerchantPrice": "5.00",
                    }
                ],
                "10.00",
            )
        assert exc.value.error_code == "MARKETPLACE_ITEM_PRICE_MISSING"

    def test_invalid_paid_price_value(self):
        with pytest.raises(ValidationError) as exc:
            validate_marketplace_basket(
                [{"id": "f1", "price": "10.00"}],
                "not-a-number",
            )
        assert exc.value.error_code == "INVALID_MARKETPLACE_PRICE"

    @pytest.mark.parametrize(
        "paid,sub_each,n_items,should_pass",
        [
            ("100.00", "33.00", 3, True),  # 99 <= 100
            ("100.00", "33.34", 3, False),  # 100.02 > 100
            ("100.00", "100.00", 1, True),  # zero commission allowed
            ("100.00", "0.00", 1, True),  # platform keeps all (still routed)
        ],
    )
    def test_sum_boundary(self, paid, sub_each, n_items, should_pass):
        items = [
            {
                "id": f"f{i}",
                "price": "100.00",
                "subMerchantKey": "smk",
                "subMerchantPrice": sub_each,
            }
            for i in range(n_items)
        ]
        if should_pass:
            validate_marketplace_basket(items, paid)
        else:
            with pytest.raises(ValidationError):
                validate_marketplace_basket(items, paid)


# ---------------------------------------------------------------------------
# IyzicoClient.create_checkout_form — integration with marketplace validation
# ---------------------------------------------------------------------------


class TestCheckoutFormMarketplace:
    def test_marketplace_basket_passes_through_to_sdk(
        self,
        mock_checkout_form,
        order_data,
        buyer,
        billing_address,
        marketplace_basket,
    ):
        _, instance = mock_checkout_form
        client = IyzicoClient()
        client.create_checkout_form(
            order_data=order_data,
            buyer=buyer,
            billing_address=billing_address,
            basket_items=marketplace_basket,
            callback_url="https://example/cb",
        )
        sent = instance.create.call_args[0][0]
        # Iyzico SDK is a passthrough — sub-merchant fields must survive.
        for original, transmitted in zip(marketplace_basket, sent["basketItems"], strict=True):
            assert transmitted["subMerchantKey"] == original["subMerchantKey"]
            assert transmitted["subMerchantPrice"] == original["subMerchantPrice"]

    def test_strict_mode_rejects_mixed_basket(
        self,
        mock_checkout_form,
        order_data,
        buyer,
        billing_address,
        marketplace_basket,
    ):
        marketplace_basket[1].pop("subMerchantKey")
        marketplace_basket[1].pop("subMerchantPrice")
        client = IyzicoClient()
        with pytest.raises(ValidationError) as exc:
            client.create_checkout_form(
                order_data=order_data,
                buyer=buyer,
                billing_address=billing_address,
                basket_items=marketplace_basket,
                callback_url="https://example/cb",
                marketplace=True,
            )
        assert exc.value.error_code == "MARKETPLACE_ITEM_MISSING_SUBMERCHANT"

    def test_non_strict_mode_accepts_mixed_basket(
        self,
        mock_checkout_form,
        order_data,
        buyer,
        billing_address,
        marketplace_basket,
    ):
        marketplace_basket[1].pop("subMerchantKey")
        marketplace_basket[1].pop("subMerchantPrice")
        client = IyzicoClient()
        response = client.create_checkout_form(
            order_data=order_data,
            buyer=buyer,
            billing_address=billing_address,
            basket_items=marketplace_basket,
            callback_url="https://example/cb",
        )
        assert response.is_successful() is True

    def test_strict_mode_with_no_basket_raises(self, order_data, buyer, billing_address):
        client = IyzicoClient()
        with pytest.raises(ValidationError) as exc:
            client.create_checkout_form(
                order_data=order_data,
                buyer=buyer,
                billing_address=billing_address,
                callback_url="https://example/cb",
                marketplace=True,
            )
        assert exc.value.error_code == "MARKETPLACE_REQUIRES_BASKET_ITEMS"

    def test_validation_error_does_not_call_sdk(
        self,
        mock_checkout_form,
        order_data,
        buyer,
        billing_address,
        marketplace_basket,
    ):
        # Sum > paidPrice: shouldn't even attempt the network call.
        order_data["paidPrice"] = "10.00"
        _, instance = mock_checkout_form
        client = IyzicoClient()
        with pytest.raises(ValidationError):
            client.create_checkout_form(
                order_data=order_data,
                buyer=buyer,
                billing_address=billing_address,
                basket_items=marketplace_basket,
                callback_url="https://example/cb",
            )
        instance.create.assert_not_called()


# ---------------------------------------------------------------------------
# IyzicoProvider.create_payment — marketplace=True opt-in
# ---------------------------------------------------------------------------


class _FakePayment:
    """Minimal PaymentLike for provider tests."""

    def __init__(self, pid: str = "pay-1", amount: int = 9000):
        self.id: int | str = pid
        self.amount = amount  # kuruş
        self.currency = "TRY"


class TestProviderMarketplace:
    def test_supports_marketplace(self):
        assert IyzicoProvider().supports_marketplace() is True

    def test_marketplace_true_rejects_default_basket(self):
        provider = IyzicoProvider()
        # Don't supply basket_items — provider should refuse to synthesise.
        result = provider.create_payment(
            _FakePayment(),
            callback_url="https://example/cb",
            buyer_info={"email": "a@b.com"},
            marketplace=True,
        )
        assert result.success is False
        assert result.error_code == "MARKETPLACE_REQUIRES_BASKET_ITEMS"

    def test_marketplace_true_with_valid_basket(self, mock_checkout_form, marketplace_basket):
        provider = IyzicoProvider()
        result = provider.create_payment(
            _FakePayment(amount=9000),
            callback_url="https://example/cb",
            buyer_info={"email": "a@b.com"},
            basket_items=marketplace_basket,
            marketplace=True,
        )
        assert result.success is True
        assert result.token == "checkout-token-mkt"

    def test_marketplace_true_strict_rejects_mixed_basket(
        self, mock_checkout_form, marketplace_basket
    ):
        marketplace_basket[1].pop("subMerchantKey")
        marketplace_basket[1].pop("subMerchantPrice")
        provider = IyzicoProvider()
        result = provider.create_payment(
            _FakePayment(amount=9000),
            callback_url="https://example/cb",
            buyer_info={"email": "a@b.com"},
            basket_items=marketplace_basket,
            marketplace=True,
        )
        assert result.success is False
        assert result.error_code == "MARKETPLACE_ITEM_MISSING_SUBMERCHANT"

    def test_marketplace_default_false_keeps_v0_4_0_behaviour(self, mock_checkout_form):
        # No basket, no marketplace — provider builds default basket and
        # the call succeeds, byte-for-byte the same as v0.4.0.
        provider = IyzicoProvider()
        result = provider.create_payment(
            _FakePayment(amount=9000),
            callback_url="https://example/cb",
            buyer_info={"email": "a@b.com"},
        )
        assert result.success is True
        _, instance = mock_checkout_form
        sent = instance.create.call_args[0][0]
        assert len(sent["basketItems"]) == 1
        # Default basket items don't carry sub-merchant fields.
        assert "subMerchantKey" not in sent["basketItems"][0]
