"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def payment_data():
    """Sample payment data for tests."""
    return {
        "id": 1,
        "amount": 10000,  # 100.00 TRY
        "currency": "TRY",
    }


@pytest.fixture
def buyer_info_data():
    """Sample buyer info for tests."""
    return {
        "email": "test@example.com",
        "name": "Test",
        "surname": "User",
        "phone": "+905551234567",
        "identity_number": "10000000146",
        "address": "Test Street 123",
        "city": "Istanbul",
        "country": "Turkey",
        "zip_code": "34000",
        "ip": "127.0.0.1",
    }


class MockPayment:
    """Mock payment object for testing."""

    def __init__(
        self,
        id: int = 1,
        amount: int = 10000,
        currency: str = "TRY",
    ):
        self.id = id
        self.amount = amount
        self.currency = currency


@pytest.fixture
def mock_payment():
    """Create a mock payment object."""
    return MockPayment()
