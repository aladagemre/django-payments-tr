"""Django settings configuration for django-iyzico."""

from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_setting(name: str, default: Any = None, required: bool = False) -> Any:
    """
    Get a django-iyzico setting from Django settings.

    Args:
        name: Setting name (without IYZICO_ prefix)
        default: Default value if setting not found
        required: Whether the setting is required

    Returns:
        Setting value

    Raises:
        ImproperlyConfigured: If required setting is not found
    """
    setting_name = f"IYZICO_{name}"
    value = getattr(settings, setting_name, default)

    if required and value is None:
        raise ImproperlyConfigured(
            f"{setting_name} is required. Please add it to your Django settings."
        )

    return value


class IyzicoSettings:
    """Central configuration for Iyzico settings."""

    @property
    def api_key(self) -> str:
        """Iyzico API key."""
        return cast(str, get_setting("API_KEY", required=True))

    @property
    def secret_key(self) -> str:
        """Iyzico secret key."""
        return cast(str, get_setting("SECRET_KEY", required=True))

    @property
    def base_url(self) -> str:
        """
        Iyzico base URL.

        Defaults to the **production** host (``https://api.iyzipay.com``).
        Set ``IYZICO_BASE_URL = "https://sandbox-api.iyzipay.com"`` to use the
        sandbox. The value is validated against the known iyzico hosts and
        must be HTTPS; anything else raises ``ImproperlyConfigured``.

        Rationale (M-03): the previous sandbox default silently sent
        production traffic to the sandbox (payments appear to "work" but
        never settle) when an integrator forgot ``IYZICO_BASE_URL``. An
        unconstrained host also let a misconfigured/compromised setting send
        merchant-secret-keyed requests to an arbitrary endpoint.
        """
        url = cast(str, get_setting("BASE_URL", default="https://api.iyzipay.com"))

        allowed_hosts = {
            "https://api.iyzipay.com",
            "https://sandbox-api.iyzipay.com",
        }
        normalized = url.rstrip("/")
        if normalized not in allowed_hosts:
            raise ImproperlyConfigured(
                f"IYZICO_BASE_URL={url!r} is not an allowed iyzico host. "
                f"Use one of: {', '.join(sorted(allowed_hosts))}."
            )
        return normalized

    @property
    def locale(self) -> str:
        """Default locale for Iyzico requests."""
        return cast(str, get_setting("LOCALE", default="tr"))

    @property
    def currency(self) -> str:
        """Default currency for Iyzico payments."""
        return cast(str, get_setting("CURRENCY", default="TRY"))

    @property
    def store_card_data(self) -> bool:
        """
        Whether to store card data (last 4 digits, card family, etc.).

        Note: Full card numbers are NEVER stored for PCI DSS compliance.
        """
        return cast(bool, get_setting("STORE_CARD_DATA", default=True))

    @property
    def enable_3d_secure(self) -> bool:
        """Whether 3D Secure is enabled by default."""
        return cast(bool, get_setting("ENABLE_3D_SECURE", default=True))

    @property
    def callback_url(self) -> str:
        """Callback URL for 3D Secure payments."""
        return cast(str, get_setting("CALLBACK_URL", default="/iyzico/callback/"))

    @property
    def webhook_url(self) -> str:
        """Webhook URL for payment notifications."""
        return cast(str, get_setting("WEBHOOK_URL", default="/iyzico/webhook/"))

    @property
    def webhook_secret(self) -> str:
        """
        Webhook secret for signature validation.

        If set, webhook requests will be validated using HMAC-SHA256 signature.
        Leave empty to disable signature validation.
        """
        return cast(str, get_setting("WEBHOOK_SECRET", default=""))

    @property
    def webhook_allowed_ips(self) -> list[str]:
        """
        List of allowed IP addresses for webhook requests.

        If set, only requests from these IPs will be accepted.
        Leave empty to allow all IPs.

        Example:
            IYZICO_WEBHOOK_ALLOWED_IPS = [
                "185.201.20.0/24",  # Iyzico webhook IPs
                "127.0.0.1",        # Localhost for testing
            ]
        """
        return cast(list[str], get_setting("WEBHOOK_ALLOWED_IPS", default=[]))

    @property
    def trust_x_forwarded_for(self) -> bool:
        """
        Whether to trust X-Forwarded-For header for client IP detection.

        WARNING: Only set this to True if your application is behind a trusted
        reverse proxy (nginx, HAProxy, load balancer) that properly sets this
        header. If set to True without a trusted proxy, attackers can spoof
        their IP address and bypass IP-based security controls.

        Default: False (secure by default)

        Security Note:
            If you're behind a reverse proxy, set IYZICO_TRUST_X_FORWARDED_FOR=True
            to correctly detect client IP addresses through the proxy.
        """
        return cast(bool, get_setting("TRUST_X_FORWARDED_FOR", default=False))

    @property
    def strict_ip_validation(self) -> bool:
        """
        Whether to require IP addresses for all payment operations.

        When True (recommended for production), IP address is required for all
        buyer info and refund operations. Raises validation error if missing.

        When False (development only), allows fallback to default IP address.

        Default: True (strict mode - production safe)

        Security Note:
            Iyzico API requires valid IP addresses. Setting this to False and
            using default IP (127.0.0.1) will cause API rejections in production.
        """
        return cast(bool, get_setting("STRICT_IP_VALIDATION", default=True))

    @property
    def connection_timeout(self) -> float:
        """
        Outbound HTTPS timeout (seconds) for calls into the iyzipay SDK.

        The bundled ``iyzipay`` SDK constructs ``http.client.HTTPSConnection``
        with no explicit timeout, which means a slow Iyzico endpoint will
        block the calling worker thread until the OS-level TCP timeout
        (often several minutes). That's a real DoS amplification risk: a
        single hung Iyzico call can pin a Celery / gunicorn worker.

        We monkey-patch ``iyzipay.IyzipayResource.connect`` at module
        import (see ``client.py``) to pass this value into the underlying
        ``HTTPSConnection``. Defaults to 30s — long enough for the slowest
        legitimate Iyzico response, short enough to fail-fast on hangs.

        Override per project::

            IYZICO_CONNECTION_TIMEOUT = 15.0
        """
        return float(get_setting("CONNECTION_TIMEOUT", default=30.0))

    @property
    def default_ip(self) -> str:
        """
        Default IP address to use when strict validation is disabled.

        WARNING: This is for development/testing only. Iyzico will reject
        localhost IPs in production. Always capture real user IP addresses.

        Default: "127.0.0.1"

        Note: This setting is ignored when IYZICO_STRICT_IP_VALIDATION is True.
        """
        return cast(str, get_setting("DEFAULT_IP", default="127.0.0.1"))

    def get_options(self) -> dict[str, str]:
        """
        Get Iyzico API options dict.

        Returns:
            Dict with api_key, secret_key, and base_url
        """
        return {
            "api_key": self.api_key,
            "secret_key": self.secret_key,
            "base_url": self.base_url,
        }


# Global settings instance
iyzico_settings = IyzicoSettings()
