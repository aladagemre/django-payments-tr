import decimal

import django
import django.db.models.deletion
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models

CHECKCONSTRAINT_PARAM = "condition" if django.VERSION >= (5, 1) else "check"


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentMethod",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "card_token",
                    models.CharField(
                        db_index=True,
                        help_text=(
                            "Iyzico card token for recurring payments. NEVER store full "
                            "card numbers."
                        ),
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "card_user_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Iyzico user key for card storage",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "card_last_four",
                    models.CharField(
                        help_text="Last 4 digits of card number",
                        max_length=4,
                    ),
                ),
                (
                    "card_brand",
                    models.CharField(
                        choices=[
                            ("VISA", "Visa"),
                            ("MASTER_CARD", "Mastercard"),
                            ("AMERICAN_EXPRESS", "American Express"),
                            ("TROY", "Troy"),
                            ("OTHER", "Other"),
                        ],
                        default="OTHER",
                        help_text="Card brand/association (Visa, Mastercard, etc.)",
                        max_length=50,
                    ),
                ),
                (
                    "card_type",
                    models.CharField(
                        blank=True,
                        help_text="Card type (CREDIT_CARD, DEBIT_CARD, etc.)",
                        max_length=50,
                        null=True,
                    ),
                ),
                (
                    "card_family",
                    models.CharField(
                        blank=True,
                        help_text="Card program/family (Bonus, Axess, Maximum, etc.)",
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "card_bank_name",
                    models.CharField(
                        blank=True,
                        help_text="Issuing bank name",
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "card_holder_name",
                    models.CharField(
                        blank=True,
                        help_text="Cardholder name (as on card)",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    "expiry_month",
                    models.CharField(
                        help_text="Expiry month (MM format)",
                        max_length=2,
                    ),
                ),
                (
                    "expiry_year",
                    models.CharField(
                        help_text="Expiry year (YYYY format)",
                        max_length=4,
                    ),
                ),
                (
                    "bin_number",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="First 6 digits of card (BIN) for installment queries",
                        max_length=6,
                        null=True,
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        db_index=True,
                        default=False,
                        help_text="Whether this is the default payment method",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Whether this payment method is active",
                    ),
                ),
                (
                    "is_verified",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this card has been verified via a successful transaction",
                    ),
                ),
                (
                    "nickname",
                    models.CharField(
                        blank=True,
                        help_text="User-defined nickname for the card",
                        max_length=100,
                        null=True,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional metadata (no sensitive data)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "last_used_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When this payment method was last used",
                        null=True,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User who owns this payment method",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="iyzico_payment_methods",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Payment Method",
                "verbose_name_plural": "Payment Methods",
                "db_table": "iyzico_payment_methods",
                "ordering": ["-is_default", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "is_active", "is_default"],
                        name="iyzico_pm_user_active_default_idx",
                    ),
                    models.Index(fields=["card_token"], name="iyzico_pm_card_token_idx"),
                    models.Index(
                        fields=["expiry_year", "expiry_month"], name="iyzico_pm_expiry_idx"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["user"],
                        condition=models.Q(is_default=True, is_active=True),
                        name="unique_default_payment_method_per_user",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Display name for the plan",
                        max_length=100,
                        unique=True,
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="URL-friendly identifier",
                        max_length=100,
                        unique=True,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Detailed plan description",
                    ),
                ),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Price per billing interval",
                        max_digits=10,
                        validators=[MinValueValidator(decimal.Decimal("0.01"))],
                    ),
                ),
                (
                    "currency",
                    models.CharField(
                        default="TRY",
                        help_text="ISO 4217 currency code",
                        max_length=3,
                    ),
                ),
                (
                    "billing_interval",
                    models.CharField(
                        choices=[
                            ("daily", "Daily"),
                            ("weekly", "Weekly"),
                            ("monthly", "Monthly"),
                            ("quarterly", "Quarterly"),
                            ("yearly", "Yearly"),
                        ],
                        default="monthly",
                        help_text="How often to bill",
                        max_length=20,
                    ),
                ),
                (
                    "billing_interval_count",
                    models.PositiveIntegerField(
                        default=1,
                        help_text=("Number of intervals between billings (e.g., 3 months)"),
                        validators=[MinValueValidator(1)],
                    ),
                ),
                (
                    "trial_period_days",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Free trial period in days (0 = no trial)",
                    ),
                ),
                (
                    "features",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Plan features and limits as JSON",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        help_text="Whether this plan is available for new subscriptions",
                    ),
                ),
                (
                    "max_subscribers",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Maximum subscribers allowed (null = unlimited)",
                        null=True,
                    ),
                ),
                (
                    "sort_order",
                    models.IntegerField(
                        default=0,
                        help_text="Display order (lower numbers appear first)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                "verbose_name": "Subscription Plan",
                "verbose_name_plural": "Subscription Plans",
                "db_table": "iyzico_subscription_plans",
                "ordering": ["sort_order", "price"],
                "indexes": [
                    models.Index(
                        fields=["is_active", "billing_interval"],
                        name="iyzico_plan_active_interval_idx",
                    ),
                    models.Index(fields=["slug"], name="iyzico_plan_slug_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("trialing", "Trialing"),
                            ("active", "Active"),
                            ("past_due", "Past Due"),
                            ("paused", "Paused"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        db_index=True,
                        default="pending",
                        help_text="Current subscription status",
                        max_length=20,
                    ),
                ),
                (
                    "start_date",
                    models.DateTimeField(
                        help_text="When subscription started",
                    ),
                ),
                (
                    "trial_end_date",
                    models.DateTimeField(
                        blank=True,
                        help_text="When trial period ends (if applicable)",
                        null=True,
                    ),
                ),
                (
                    "current_period_start",
                    models.DateTimeField(
                        help_text="Start of current billing period",
                    ),
                ),
                (
                    "current_period_end",
                    models.DateTimeField(
                        help_text="End of current billing period",
                    ),
                ),
                (
                    "cancelled_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When subscription was cancelled",
                        null=True,
                    ),
                ),
                (
                    "ended_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="When subscription ended",
                        null=True,
                    ),
                ),
                (
                    "next_billing_date",
                    models.DateTimeField(
                        db_index=True,
                        help_text="Next scheduled billing date",
                    ),
                ),
                (
                    "failed_payment_count",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Number of consecutive failed payment attempts",
                    ),
                ),
                (
                    "last_payment_attempt",
                    models.DateTimeField(
                        blank=True,
                        help_text="When last payment was attempted",
                        null=True,
                    ),
                ),
                (
                    "last_payment_error",
                    models.TextField(
                        blank=True,
                        help_text="Error message from last failed payment",
                        null=True,
                    ),
                ),
                (
                    "cancel_at_period_end",
                    models.BooleanField(
                        default=False,
                        help_text="Whether to cancel at end of current period",
                    ),
                ),
                (
                    "cancellation_reason",
                    models.TextField(
                        blank=True,
                        help_text="Reason for cancellation",
                        null=True,
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional metadata",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "plan",
                    models.ForeignKey(
                        help_text="Subscription plan",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="subscriptions",
                        to="payments_tr_iyzico.subscriptionplan",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="Subscriber user",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="iyzico_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Subscription",
                "verbose_name_plural": "Subscriptions",
                "db_table": "iyzico_subscriptions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["user", "status"], name="iyzico_sub_user_status_idx"),
                    models.Index(
                        fields=["status", "next_billing_date"],
                        name="iyzico_sub_status_next_bill_idx",
                    ),
                    models.Index(fields=["plan", "status"], name="iyzico_sub_plan_status_idx"),
                    models.Index(
                        fields=["cancel_at_period_end", "current_period_end"],
                        name="iyzico_sub_cancel_period_end_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(  # type: ignore[call-overload]
                        # Django 5.1 renamed ``check`` -> ``condition``; we
                        # resolve the name via ``CHECKCONSTRAINT_PARAM``.
                        **{
                            CHECKCONSTRAINT_PARAM: models.Q(
                                current_period_end__gte=models.F("current_period_start")
                            )
                        },
                        name="period_end_after_start",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SubscriptionPayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("iyzico", "iyzico"),
                            ("stripe", "Stripe"),
                            ("paypal", "PayPal"),
                            ("paytr", "PayTR"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        default="other",
                        help_text="Payment provider (e.g., iyzico, stripe)",
                        max_length=20,
                        verbose_name="Provider",
                    ),
                ),
                (
                    "provider_payment_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Payment ID from the provider",
                        max_length=255,
                        null=True,
                        unique=True,
                        verbose_name="Provider Payment ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("refund_pending", "Refund Pending"),
                            ("refunded", "Refunded"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="pending",
                        help_text="Current payment status",
                        max_length=20,
                        verbose_name="Status",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Payment amount",
                        max_digits=10,
                        verbose_name="Amount",
                    ),
                ),
                (
                    "paid_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Actual amount paid (may differ with fees/installments)",
                        max_digits=10,
                        null=True,
                        verbose_name="Paid Amount",
                    ),
                ),
                (
                    "currency",
                    models.CharField(
                        default="TRY",
                        help_text="Currency code (e.g., TRY, USD, EUR)",
                        max_length=3,
                        verbose_name="Currency",
                    ),
                ),
                (
                    "buyer_email",
                    models.EmailField(
                        blank=True,
                        help_text="Buyer's email address",
                        max_length=255,
                        null=True,
                        verbose_name="Buyer Email",
                    ),
                ),
                (
                    "buyer_name",
                    models.CharField(
                        blank=True,
                        help_text="Buyer's first name",
                        max_length=255,
                        null=True,
                        verbose_name="Buyer Name",
                    ),
                ),
                (
                    "buyer_surname",
                    models.CharField(
                        blank=True,
                        help_text="Buyer's last name",
                        max_length=255,
                        null=True,
                        verbose_name="Buyer Surname",
                    ),
                ),
                (
                    "error_code",
                    models.CharField(
                        blank=True,
                        help_text="Error code (if payment failed)",
                        max_length=50,
                        null=True,
                        verbose_name="Error Code",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        help_text="Error message (if payment failed)",
                        null=True,
                        verbose_name="Error Message",
                    ),
                ),
                (
                    "raw_response",
                    models.JSONField(
                        blank=True,
                        help_text=("Complete response from provider API (for debugging and audit)"),
                        null=True,
                        verbose_name="Raw Response",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this payment record was created",
                        verbose_name="Created At",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="When this payment record was last updated",
                        verbose_name="Updated At",
                    ),
                ),
                (
                    "conversation_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Unique conversation ID for tracking this payment",
                        max_length=255,
                        null=True,
                        verbose_name="Conversation ID",
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text="Checkout form token",
                        max_length=255,
                        null=True,
                        verbose_name="Checkout Token",
                    ),
                ),
                (
                    "locale",
                    models.CharField(
                        default="tr",
                        help_text="Locale for the payment (e.g., tr, en)",
                        max_length=5,
                        verbose_name="Locale",
                    ),
                ),
                (
                    "card_last_four_digits",
                    models.CharField(
                        blank=True,
                        help_text="Last 4 digits of card number",
                        max_length=4,
                        null=True,
                        verbose_name="Card Last 4 Digits",
                    ),
                ),
                (
                    "card_type",
                    models.CharField(
                        blank=True,
                        help_text="Card type (e.g., CREDIT_CARD, DEBIT_CARD)",
                        max_length=50,
                        null=True,
                        verbose_name="Card Type",
                    ),
                ),
                (
                    "card_association",
                    models.CharField(
                        blank=True,
                        help_text=("Card association (e.g., VISA, MASTER_CARD, AMEX)"),
                        max_length=50,
                        null=True,
                        verbose_name="Card Association",
                    ),
                ),
                (
                    "card_family",
                    models.CharField(
                        blank=True,
                        help_text="Card family/program (e.g., Bonus, Axess, Maximum)",
                        max_length=50,
                        null=True,
                        verbose_name="Card Family",
                    ),
                ),
                (
                    "card_bank_name",
                    models.CharField(
                        blank=True,
                        help_text="Issuing bank name",
                        max_length=100,
                        null=True,
                        verbose_name="Card Bank Name",
                    ),
                ),
                (
                    "card_bank_code",
                    models.CharField(
                        blank=True,
                        help_text="Issuing bank code",
                        max_length=50,
                        null=True,
                        verbose_name="Card Bank Code",
                    ),
                ),
                (
                    "bin_number",
                    models.CharField(
                        blank=True,
                        help_text=("First 6 digits of card (Bank Identification Number)"),
                        max_length=6,
                        null=True,
                        verbose_name="BIN Number",
                    ),
                ),
                (
                    "installment",
                    models.IntegerField(
                        default=1,
                        help_text="Number of installments (1 for single payment)",
                        verbose_name="Installment",
                    ),
                ),
                (
                    "installment_rate",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Installment fee rate as percentage",
                        max_digits=5,
                        null=True,
                        verbose_name="Installment Rate",
                    ),
                ),
                (
                    "monthly_installment_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Amount per month for installment payments",
                        max_digits=10,
                        null=True,
                        verbose_name="Monthly Installment Amount",
                    ),
                ),
                (
                    "total_with_installment",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Total amount including installment fees",
                        max_digits=10,
                        null=True,
                        verbose_name="Total with Installment",
                    ),
                ),
                (
                    "error_group",
                    models.CharField(
                        blank=True,
                        help_text="Iyzico error group (if payment failed)",
                        max_length=50,
                        null=True,
                        verbose_name="Error Group",
                    ),
                ),
                (
                    "period_start",
                    models.DateTimeField(
                        help_text="Start of billing period",
                    ),
                ),
                (
                    "period_end",
                    models.DateTimeField(
                        help_text="End of billing period",
                    ),
                ),
                (
                    "attempt_number",
                    models.PositiveIntegerField(
                        default=1,
                        help_text="Payment attempt number (1 = first attempt)",
                    ),
                ),
                (
                    "is_retry",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this is a retry after failure",
                    ),
                ),
                (
                    "is_prorated",
                    models.BooleanField(
                        default=False,
                        help_text="Whether this payment is prorated",
                    ),
                ),
                (
                    "prorated_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Prorated amount (if different from plan price)",
                        max_digits=10,
                        null=True,
                    ),
                ),
                (
                    "refund_reason",
                    models.CharField(
                        blank=True,
                        help_text="Reason for refund if applicable",
                        max_length=200,
                        null=True,
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        help_text="Associated subscription",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="payments",
                        to="payments_tr_iyzico.subscription",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="User who made the payment",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="iyzico_subscription_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Subscription Payment",
                "verbose_name_plural": "Subscription Payments",
                "db_table": "iyzico_subscription_payments",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["provider_payment_id"], name="iyzico_subpay_provider_payment_id_idx"
                    ),
                    models.Index(fields=["provider"], name="iyzico_subpay_provider_idx"),
                    models.Index(fields=["status"], name="iyzico_subpay_status_idx"),
                    models.Index(fields=["created_at"], name="iyzico_subpay_created_at_idx"),
                    models.Index(fields=["-created_at"], name="iyzico_subpay_created_at_desc_idx"),
                    models.Index(fields=["buyer_email"], name="iyzico_subpay_buyer_email_idx"),
                    models.Index(
                        fields=["provider", "status"], name="iyzico_subpay_provider_status_idx"
                    ),
                    models.Index(
                        fields=["status", "created_at"], name="iyzico_subpay_status_created_idx"
                    ),
                    models.Index(
                        fields=["provider_payment_id", "status"],
                        name="iyzico_subpay_provider_payment_status_idx",
                    ),
                    models.Index(
                        fields=["buyer_email", "status"],
                        name="iyzico_subpay_buyer_email_status_idx",
                    ),
                    models.Index(
                        fields=["currency", "status", "created_at"],
                        name="iyzico_subpay_currency_status_created_idx",
                    ),
                    models.Index(
                        fields=["conversation_id"], name="iyzico_subpay_conversation_id_idx"
                    ),
                    models.Index(fields=["token"], name="iyzico_subpay_token_idx"),
                    models.Index(
                        fields=["card_association", "status"],
                        name="iyzico_subpay_card_assoc_status_idx",
                    ),
                    models.Index(
                        fields=["subscription", "status"],
                        name="iyzico_subpay_subscription_status_idx",
                    ),
                    models.Index(
                        fields=["period_start", "period_end"], name="iyzico_subpay_period_range_idx"
                    ),
                    models.Index(
                        fields=["attempt_number", "is_retry"],
                        name="iyzico_subpay_attempt_retry_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=[
                            "subscription",
                            "period_start",
                            "period_end",
                            "attempt_number",
                        ],
                        name="unique_subscription_payment_period",
                    )
                ],
            },
        ),
    ]
