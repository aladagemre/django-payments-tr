"""
Backfill NULL ``PaymentMethod.card_user_key`` rows with an empty string and
make the field non-nullable.

In practice every stored card has a user key — Iyzico won't issue a card token
without one — so the existing ``null=True`` was protecting against a state
that never occurs but forced ``# type: ignore[arg-type]`` annotations at
every call site (``IyzicoClient.delete_card`` / ``charge_with_token`` both
require ``str``). This migration aligns the schema with how the field is
actually used.
"""

from django.db import migrations, models


def _backfill_null_card_user_keys(apps, schema_editor):  # noqa: ARG001
    PaymentMethod = apps.get_model("payments_tr_iyzico", "PaymentMethod")
    PaymentMethod.objects.filter(card_user_key__isnull=True).update(card_user_key="")


class Migration(migrations.Migration):
    dependencies = [
        ("payments_tr_iyzico", "0002_rename_indexes"),
    ]

    operations = [
        migrations.RunPython(
            _backfill_null_card_user_keys,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="paymentmethod",
            name="card_user_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Iyzico user key for card storage",
                max_length=255,
            ),
        ),
    ]
