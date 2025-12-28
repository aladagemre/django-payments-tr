"""
URL patterns for installment views.

Add to your project's urls.py:
    path('iyzico/', include('payments_tr.providers.iyzico.installments.urls')),
"""

from django.urls import path

from .views import BestInstallmentOptionsView, InstallmentOptionsView, ValidateInstallmentView

app_name = "iyzico_installments"

urlpatterns = [
    # Get all installment options
    path(
        "installments/",
        InstallmentOptionsView.as_view(),
        name="installment_options",
    ),
    # Get best/recommended installment options
    path(
        "installments/best/",
        BestInstallmentOptionsView.as_view(),
        name="best_installment_options",
    ),
    # Validate installment selection
    path(
        "installments/validate/",
        ValidateInstallmentView.as_view(),
        name="validate_installment",
    ),
]


# Optional: DRF router configuration
try:
    from rest_framework.routers import DefaultRouter

    from .views import InstallmentViewSet

    if InstallmentViewSet:
        router = DefaultRouter()
        router.register(r"installments", InstallmentViewSet, basename="installment")

        # Add to urlpatterns for DRF
        # urlpatterns += router.urls

except ImportError:
    router = None
