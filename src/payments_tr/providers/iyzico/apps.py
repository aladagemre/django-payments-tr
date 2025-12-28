"""Django app configuration for iyzico provider."""

from django.apps import AppConfig


class IyzicoConfig(AppConfig):
    """Configuration for the iyzico payment provider."""

    name = "payments_tr.providers.iyzico"
    label = "payments_tr_iyzico"
    verbose_name = "Iyzico Payment Provider"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Import signals when app is ready."""
        # Import signals to register them
        from . import signals  # noqa: F401
