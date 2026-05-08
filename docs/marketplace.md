# Marketplace (sub-merchant) payments

Iyzico's marketplace flow ("işyeri gelir paylaşımı") splits each basket
item between the platform and a sub-merchant — the seller. The platform
takes the difference between an item's `price` and its `subMerchantPrice`
as commission; the sub-merchant gets the rest, settled to their IBAN by
Iyzico on a schedule you configure with them.

`django-payments-tr` ships first-class support for marketplace flows from
v0.5.0 onward. This document walks through the end-to-end flow.

> **Scope.** v0.5.0 supports TRY-only marketplace payments (Iyzico's
> marketplace is TR-only in practice). Sub-merchant approval workflow
> (admin-side acceptance UI) is intentionally out of scope — consumers
> build their own. Same for payout reporting: Iyzico provides those on
> their dashboard / via separate API.

---

## 1. Register the sub-merchant

Use `SubMerchantClient` to register each seller with Iyzico **once**.
Iyzico returns a `subMerchantKey` that you store on the seller record
and reuse on every payment routed to them.

```python
from payments_tr.providers.iyzico import (
    SubMerchantClient,
    SubMerchantType,
)

client = SubMerchantClient()

resp = client.create(
    external_id="station-42",                  # your stable id
    sub_merchant_type=SubMerchantType.LIMITED_OR_JOINT_STOCK_COMPANY,
    legal_company_title="Acme Print AŞ",
    contact_name="Aslı",
    contact_surname="Yılmaz",
    email="acme@example.com",
    gsm_number="+905551234567",
    iban="TR330006100519786457841326",         # validated via validate_iban_tr
    tax_office="Beşiktaş",
    tax_number="1234567890",                   # validated via validate_vkn
    address="...",
)

if resp.is_successful:
    seller.iyzico_sub_merchant_key = resp.sub_merchant_key
    seller.iyzico_external_id = "station-42"
    seller.save()
else:
    log.error("Sub-merchant create failed: %s", resp.error_message)
```

The TR validators (`validate_iban_tr`, `validate_tckn`, `validate_vkn`)
run **before** the request goes out; bad checksums raise a
`ValidationError` with `error_code="INVALID_IBAN"` / `INVALID_TCKN` /
`INVALID_VKN`. Type-conditional required fields are also enforced:

- `PERSONAL` → `identity_number` required.
- `PRIVATE_COMPANY` / `LIMITED_OR_JOINT_STOCK_COMPANY` → both
  `tax_office` and `tax_number` required.

### Updating a sub-merchant

`SubMerchantClient.update()` sends only the fields you supply
(PATCH-style). Unknown kwargs are rejected with
`SUBMERCHANT_UNKNOWN_FIELD`, never silently dropped:

```python
client.update("smk-from-iyzico", iban="TR...new...", contact_name="Yeni")
```

### Looking up by external id

```python
resp = client.retrieve("station-42")
if resp.is_successful:
    seller.iyzico_sub_merchant_key = resp.sub_merchant_key
```

## 2. Store the key on a seller model

Use the `AbstractSubMerchantOwner` mixin if you want pre-built storage
fields and a `clean()` validator that runs the TR validators on save:

```python
from django.db import models
from payments_tr.providers.iyzico.models import AbstractSubMerchantOwner


class PrintStation(AbstractSubMerchantOwner):
    owner = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    class Meta:
        db_table = "print_stations"
```

> **No automatic migration.** The mixin is abstract; running
> `makemigrations` on your app picks up the new fields. This keeps the
> schema fully under your control.

The mixin adds:

| field | purpose |
|---|---|
| `iyzico_sub_merchant_key` | Iyzico-issued key, used as `basketItems[i].subMerchantKey` |
| `iyzico_sub_merchant_type` | choices: `PERSONAL`, `PRIVATE_COMPANY`, `LIMITED_OR_JOINT_STOCK_COMPANY` |
| `iyzico_external_id` | your stable id, used by `SubMerchantClient.retrieve` |
| `iyzico_iban` | TR IBAN (26 chars) |
| `iyzico_identity_number` | TCKN (PERSONAL only) |
| `iyzico_tax_office` | tax office name (company types) |
| `iyzico_tax_number` | VKN (company types) |
| `iyzico_legal_company_title` | as registered with Iyzico |

`PrintStation.has_iyzico_sub_merchant()` returns `True` once the key is
populated — handy for gating UI flows.

## 3. Create a marketplace payment

Build the basket so each item carries `subMerchantKey` and
`subMerchantPrice`, then opt in via `marketplace=True`:

```python
from payments_tr import get_payment_provider

provider = get_payment_provider("iyzico")

# Single-seller order (BulutPrint shape — many basket items, one seller).
basket_items = [
    {
        "id": str(f.id),
        "name": f.original_filename[:100],
        "category1": "Baskı Hizmeti",
        "itemType": "PHYSICAL",
        "price": str(f.subtotal),
        "subMerchantKey": order.station.iyzico_sub_merchant_key,
        "subMerchantPrice": str(f.station_earnings),  # platform commission deducted
    }
    for f in order.files.all()
]

result = provider.create_payment(
    payment,
    callback_url="https://example.com/payments/callback/",
    buyer_info={"email": "customer@example.com", ...},
    basket_items=basket_items,
    marketplace=True,
)
if result.success:
    redirect(result.checkout_url)
```

`marketplace=True` enforces:

1. **Every** item carries both `subMerchantKey` and `subMerchantPrice`.
2. The default synthetic single-item basket fallback is **rejected** —
   we refuse to invent a `subMerchantKey`.
3. Per-item: `subMerchantPrice <= price`.
4. Cross-item: `sum(subMerchantPrice) <= paidPrice` (otherwise platform
   commission is negative).

If you want to mix marketplace and platform-only items in one order
(Iyzico allows this — it keeps full revenue on the unrouted items),
omit `marketplace=True`. The per-item and sum invariants still apply
to whichever items are marketplace-routed:

```python
# basket_items contains a mix; this validates the marketplace items
# but accepts the non-marketplace ones.
result = provider.create_payment(
    payment,
    callback_url="...",
    buyer_info=...,
    basket_items=basket_items,
)
```

## 4. Handle the callback

Marketplace payments use the same callback flow as regular checkout
form payments — the `confirm_payment` API call retrieves the result
server-side. Always pass `expected_amount` and `expected_currency` for
TOCTOU defence (introduced in v0.4.0):

```python
def callback_view(request):
    token = request.POST["token"]
    result = provider.confirm_payment(
        token,
        expected_amount=payment.amount,    # kuruş
        expected_currency=payment.currency,
    )
    if result.success:
        # Marketplace payments include itemTransactions[] in raw_response,
        # one entry per basket item with the per-item paymentTransactionId
        # that you'll need for partial / item-level refunds.
        for item_tx in result.raw_response.get("itemTransactions", []):
            BasketItemPayment.objects.create(
                file_id=item_tx["itemId"],
                payment_transaction_id=item_tx["paymentTransactionId"],
                sub_merchant_price=item_tx.get("subMerchantPrice"),
                ...,
            )
        payment.mark_succeeded()
```

## 5. Refund a marketplace payment

To refund a single item's revenue (the seller's share, not the
platform's commission), reference that item's `paymentTransactionId`:

```python
result = provider.create_refund(
    payment,
    amount=item.sub_merchant_price * 100,   # kuruş
    payment_transaction_id=item.payment_transaction_id,
    ip_address=request.META["REMOTE_ADDR"],
    reason="Customer requested refund of file 3",
)
```

If you omit `payment_transaction_id` the call falls back to the
order-level payment id — same byte-for-byte behaviour as v0.4.0
non-marketplace refunds.

`RefundResponse.payment_transaction_id` exposes the same id Iyzico
echoes back, so you can record exactly which item was refunded.

---

## Quick reference: error codes

| code | when |
|---|---|
| `MARKETPLACE_FIELDS_INCOMPLETE` | one of `subMerchantKey` / `subMerchantPrice` missing on an item |
| `MARKETPLACE_EMPTY_SUBMERCHANT_KEY` | whitespace-only `subMerchantKey` |
| `MARKETPLACE_NEGATIVE_SUBMERCHANT_PRICE` | `subMerchantPrice < 0` |
| `MARKETPLACE_ITEM_PRICE_MISSING` | marketplace item has no `price` |
| `MARKETPLACE_SUBMERCHANT_EXCEEDS_ITEM_PRICE` | per-item invariant broken |
| `MARKETPLACE_SUBMERCHANT_SUM_EXCEEDS_PAID_PRICE` | cross-item invariant broken |
| `MARKETPLACE_ITEM_MISSING_SUBMERCHANT` | strict mode + a non-marketplace item |
| `MARKETPLACE_REQUIRES_BASKET_ITEMS` | `marketplace=True` without basket items |
| `INVALID_IBAN` / `INVALID_TCKN` / `INVALID_VKN` | TR validator failed |
| `SUBMERCHANT_MISSING_TCKN` | PERSONAL type without `identity_number` |
| `SUBMERCHANT_MISSING_TAX_OFFICE` / `SUBMERCHANT_MISSING_VKN` | company without tax fields |
| `SUBMERCHANT_UNKNOWN_FIELD` | `update()` got a kwarg it didn't recognise |
