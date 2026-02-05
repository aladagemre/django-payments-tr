"""
Migration to rename indexes to Django's auto-generated naming convention
and remove unused indexes from SubscriptionPayment.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("payments_tr_iyzico", "0001_initial"),
    ]

    operations = [
        # Remove SubscriptionPayment indexes that are no longer needed
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_provider_payment_id_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_provider_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_status_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_created_at_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_created_at_desc_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_buyer_email_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_provider_status_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_status_created_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_provider_payment_status_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_buyer_email_status_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_currency_status_created_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_conversation_id_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_token_idx",
        ),
        migrations.RemoveIndex(
            model_name="subscriptionpayment",
            name="iyzico_subpay_card_assoc_status_idx",
        ),
        # Rename PaymentMethod indexes to auto-generated names
        migrations.RenameIndex(
            model_name="paymentmethod",
            old_name="iyzico_pm_user_active_default_idx",
            new_name="iyzico_paym_user_id_91d79d_idx",
        ),
        migrations.RenameIndex(
            model_name="paymentmethod",
            old_name="iyzico_pm_card_token_idx",
            new_name="iyzico_paym_card_to_6f9cdb_idx",
        ),
        migrations.RenameIndex(
            model_name="paymentmethod",
            old_name="iyzico_pm_expiry_idx",
            new_name="iyzico_paym_expiry__e0c63d_idx",
        ),
        # Rename Subscription indexes to auto-generated names
        migrations.RenameIndex(
            model_name="subscription",
            old_name="iyzico_sub_user_status_idx",
            new_name="iyzico_subs_user_id_23b6ed_idx",
        ),
        migrations.RenameIndex(
            model_name="subscription",
            old_name="iyzico_sub_status_next_bill_idx",
            new_name="iyzico_subs_status_4a0f9c_idx",
        ),
        migrations.RenameIndex(
            model_name="subscription",
            old_name="iyzico_sub_plan_status_idx",
            new_name="iyzico_subs_plan_id_3b7c81_idx",
        ),
        migrations.RenameIndex(
            model_name="subscription",
            old_name="iyzico_sub_cancel_period_end_idx",
            new_name="iyzico_subs_cancel__bf9633_idx",
        ),
        # Rename SubscriptionPayment indexes to auto-generated names
        migrations.RenameIndex(
            model_name="subscriptionpayment",
            old_name="iyzico_subpay_subscription_status_idx",
            new_name="iyzico_subs_subscri_28f321_idx",
        ),
        migrations.RenameIndex(
            model_name="subscriptionpayment",
            old_name="iyzico_subpay_period_range_idx",
            new_name="iyzico_subs_period__b00936_idx",
        ),
        migrations.RenameIndex(
            model_name="subscriptionpayment",
            old_name="iyzico_subpay_attempt_retry_idx",
            new_name="iyzico_subs_attempt_d12219_idx",
        ),
        # Rename SubscriptionPlan indexes to auto-generated names
        migrations.RenameIndex(
            model_name="subscriptionplan",
            old_name="iyzico_plan_active_interval_idx",
            new_name="iyzico_subs_is_acti_cac30f_idx",
        ),
        migrations.RenameIndex(
            model_name="subscriptionplan",
            old_name="iyzico_plan_slug_idx",
            new_name="iyzico_subs_slug_88694b_idx",
        ),
    ]
