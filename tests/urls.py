"""URL configuration for tests."""

from django.urls import include, path

urlpatterns = [
    path("iyzico/", include("payments_tr.providers.iyzico.urls")),
]
