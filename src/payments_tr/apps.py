"""Django app configuration for payments_tr."""

from django.apps import AppConfig


class PaymentsTrConfig(AppConfig):
    """Django app configuration."""

    name = "payments_tr"
    verbose_name = "Payments TR"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Initialize the app and auto-discover providers."""
        # Auto-register available providers
        from payments_tr.providers import registry

        # Try to register iyzico adapter if django-iyzico is installed
        try:
            from payments_tr.providers.iyzico import IyzicoAdapter

            registry.register("iyzico", IyzicoAdapter)
        except ImportError:
            pass

        # Try to register stripe adapter if stripe is installed
        try:
            from payments_tr.providers.stripe import StripeAdapter

            registry.register("stripe", StripeAdapter)
        except ImportError:
            pass
