"""Tests for django-iyzico settings."""

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from payments_tr.providers.iyzico.settings import IyzicoSettings, get_setting


def test_get_setting_with_default():
    """Test getting a setting with default value."""
    value = get_setting("NONEXISTENT", default="default_value")
    assert value == "default_value"


def test_get_setting_required_missing():
    """Test that required missing setting raises error."""
    with pytest.raises(ImproperlyConfigured):
        get_setting("REQUIRED_BUT_MISSING", required=True)


def test_iyzico_settings_api_key(settings):
    """Test API key setting."""
    iyzico_settings = IyzicoSettings()
    assert iyzico_settings.api_key == settings.IYZICO_API_KEY


def test_iyzico_settings_get_options():
    """Test getting options dict."""
    iyzico_settings = IyzicoSettings()
    options = iyzico_settings.get_options()

    assert "api_key" in options
    assert "secret_key" in options
    assert "base_url" in options


class TestIyzicoConnectionTimeout:
    """Tests for the outbound HTTPS timeout patch on the iyzipay SDK.

    Defends against a DoS amplification vector where a slow / hung Iyzico
    endpoint could pin a worker thread for minutes because the bundled
    iyzipay SDK constructs ``HTTPSConnection`` with no explicit timeout.
    """

    def test_default_connection_timeout_is_30s(self):
        s = IyzicoSettings()
        assert s.connection_timeout == 30.0

    @override_settings(IYZICO_CONNECTION_TIMEOUT=7.5)
    def test_custom_connection_timeout_is_honoured(self):
        s = IyzicoSettings()
        assert s.connection_timeout == 7.5

    def test_connect_patch_passes_timeout_to_https_connection(self):
        """The patched ``IyzipayResource.connect`` must construct
        ``HTTPSConnection`` with ``timeout=`` set to the configured value.
        """
        # Importing the client module triggers the monkey-patch.
        from iyzipay.iyzipay_resource import IyzipayResource

        from payments_tr.providers.iyzico import client  # noqa: F401

        resource = IyzipayResource()
        fake_https = MagicMock()
        # Stub out the SDK's ``httplib`` so we never actually open a socket.
        resource.httplib = MagicMock()
        resource.httplib.HTTPSConnection = fake_https
        # Skip auth header generation — we only care that the timeout was
        # threaded through to the HTTPSConnection constructor.
        with (
            patch.object(resource, "get_http_header", return_value={}),
            override_settings(IYZICO_CONNECTION_TIMEOUT=12.0),
        ):
            resource.connect(
                method="POST",
                url="/payment/auth",
                options={"base_url": "https://sandbox-api.iyzipay.com"},
                request_body_dict={"foo": "bar"},
            )

        fake_https.assert_called_once_with("https://sandbox-api.iyzipay.com", timeout=12.0)
