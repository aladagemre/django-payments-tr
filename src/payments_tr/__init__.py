"""
Django Payments TR - Payment processing for Django with Turkey-specific features.

This package provides:
- Provider abstraction layer for multiple payment gateways (iyzico, Stripe)
- Turkey-specific utilities (KDV/VAT, TCKN validation, IBAN validation)
- EFT payment workflow with admin approval
- Commission calculation utilities
- Security features (webhook verification, rate limiting, audit logging)
- Payment signals for lifecycle events
- Async/await support for providers
- Retry logic with exponential backoff
- Comprehensive logging and monitoring
- Testing utilities and mocks
"""

from payments_tr.providers import (
    BuyerInfo,
    PaymentProvider,
    PaymentResult,
    RefundResult,
    WebhookResult,
    get_payment_provider,
    get_provider_name,
    register_provider,
)

# Async support
from payments_tr.providers.async_base import (
    AsyncPaymentProvider,
    get_async_payment_provider,
)

# Configuration and validation
from payments_tr.config import (
    validate_settings,
    get_setting,
    check_configuration,
)

# Security
from payments_tr.security import (
    IyzicoWebhookVerifier,
    RateLimiter,
    AuditLogger,
    IdempotencyManager,
)

# Retry utilities
from payments_tr.retry import (
    retry_with_backoff,
    RetryableOperation,
)

# Logging
from payments_tr.logging_config import (
    configure_logging,
    get_logger,
)

# Health checks
from payments_tr.health import (
    ProviderHealthChecker,
    HealthCheckResult,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Provider abstraction
    "PaymentProvider",
    "PaymentResult",
    "RefundResult",
    "WebhookResult",
    "BuyerInfo",
    "get_payment_provider",
    "get_provider_name",
    "register_provider",
    # Async support
    "AsyncPaymentProvider",
    "get_async_payment_provider",
    # Configuration
    "validate_settings",
    "get_setting",
    "check_configuration",
    # Security
    "IyzicoWebhookVerifier",
    "RateLimiter",
    "AuditLogger",
    "IdempotencyManager",
    # Retry
    "retry_with_backoff",
    "RetryableOperation",
    # Logging
    "configure_logging",
    "get_logger",
    # Health checks
    "ProviderHealthChecker",
    "HealthCheckResult",
]
