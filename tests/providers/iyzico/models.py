"""
Models for iyzico tests.

Provides concrete implementations of abstract models for testing.
"""

from payments_tr.providers.iyzico.models import AbstractIyzicoPayment


class ConcretePayment(AbstractIyzicoPayment):
    """
    Concrete payment model for testing.

    This extends AbstractIyzicoPayment to create a real database table
    that can be used in tests.
    """

    # No additional fields needed for basic testing
    # AbstractIyzicoPayment provides all payment fields

    class Meta(AbstractIyzicoPayment.Meta):
        db_table = "test_payments"
        app_label = "tests"


# Aliases for backwards compatibility in tests
TestPayment = ConcretePayment
SamplePayment = ConcretePayment
