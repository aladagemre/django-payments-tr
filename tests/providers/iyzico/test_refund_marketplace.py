"""
Tests for marketplace refund attribution.

Marketplace payments expose an item-level ``paymentTransactionId`` for each
basket item. Refunding a marketplace order must reference that
transaction id (so only the relevant sub-merchant's share is reversed),
not the order-level payment id (which would reverse the platform's
slice). These tests verify both the client wiring and the
``IyzicoProvider.create_refund`` plumbing.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from payments_tr.providers.iyzico.client import IyzicoClient, RefundResponse
from payments_tr.providers.iyzico.provider import IyzicoProvider


@pytest.fixture
def mock_refund_class():
    with patch("payments_tr.providers.iyzico.client.iyzipay.Refund") as cls:
        instance = Mock()
        instance.create.return_value = {
            "status": "success",
            "paymentId": "order-pay-1",
            "paymentTransactionId": "item-tx-1",
            "price": "27.00",
            "currency": "TRY",
        }
        cls.return_value = instance
        yield cls, instance


class _FakePayment:
    def __init__(self, pid: str = "order-pay-1", amount: int = 9000):
        self.id: int | str = pid
        self.amount = amount
        self.currency = "TRY"
        self.iyzico_payment_id = pid


class TestRefundResponsePaymentTransactionId:
    def test_property_present(self):
        resp = RefundResponse(
            {
                "status": "success",
                "paymentId": "order-pay-1",
                "paymentTransactionId": "item-tx-1",
            }
        )
        # Both refund_id and payment_transaction_id resolve to the same
        # SDK key — we expose two names because callers reason about
        # them differently (refund_id = the refund record itself; payment_
        # transaction_id = the basket item that was refunded).
        assert resp.payment_transaction_id == "item-tx-1"
        assert resp.refund_id == "item-tx-1"

    def test_property_is_none_when_missing(self):
        resp = RefundResponse({"status": "success"})
        assert resp.payment_transaction_id is None


class TestClientRefundPaymentTransactionId:
    def test_prefers_payment_transaction_id_when_provided(self, mock_refund_class):
        _, instance = mock_refund_class
        client = IyzicoClient()
        client.refund_payment(
            payment_id="order-pay-1",
            ip_address="127.0.0.1",
            payment_transaction_id="item-tx-1",
        )
        sent = instance.create.call_args[0][0]
        assert sent["paymentTransactionId"] == "item-tx-1"

    def test_falls_back_to_payment_id_when_not_provided(self, mock_refund_class):
        _, instance = mock_refund_class
        client = IyzicoClient()
        client.refund_payment(payment_id="order-pay-1", ip_address="127.0.0.1")
        sent = instance.create.call_args[0][0]
        # v0.4.0 byte-compat: paymentTransactionId carries the payment_id
        # when no item-level id was given.
        assert sent["paymentTransactionId"] == "order-pay-1"


class TestProviderRefundMarketplaceWiring:
    def test_provider_passes_payment_transaction_id_through(self, mock_refund_class):
        provider = IyzicoProvider()
        result = provider.create_refund(
            _FakePayment(),
            payment_transaction_id="item-tx-1",
            ip_address="127.0.0.1",
        )
        assert result.success is True

        _, instance = mock_refund_class
        sent = instance.create.call_args[0][0]
        assert sent["paymentTransactionId"] == "item-tx-1"

    def test_provider_without_payment_transaction_id_uses_payment_id(self, mock_refund_class):
        provider = IyzicoProvider()
        provider.create_refund(_FakePayment(), ip_address="127.0.0.1")
        _, instance = mock_refund_class
        sent = instance.create.call_args[0][0]
        assert sent["paymentTransactionId"] == "order-pay-1"

    def test_partial_marketplace_refund_amount_in_kurus(self, mock_refund_class):
        provider = IyzicoProvider()
        result = provider.create_refund(
            _FakePayment(),
            amount=2700,  # 27.00 TRY
            payment_transaction_id="item-tx-1",
            ip_address="127.0.0.1",
        )
        assert result.success is True

        _, instance = mock_refund_class
        sent = instance.create.call_args[0][0]
        # The refund attribution is at the item level...
        assert sent["paymentTransactionId"] == "item-tx-1"
        # ...and the amount is converted from kuruş to TRY for transport.
        assert sent["price"] == "27.00"
