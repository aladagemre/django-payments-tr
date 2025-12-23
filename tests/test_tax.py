"""Tests for tax calculation utilities."""

from decimal import Decimal

import pytest

from payments_tr.tax import KDVRate, amount_with_kdv, calculate_kdv, extract_kdv, format_currency
from payments_tr.tax.kdv import calculate_commission, get_kdv_breakdown, net_after_commission


class TestKDVRate:
    """Tests for KDVRate enum."""

    def test_standard_rate(self):
        """Test standard KDV rate is 20%."""
        assert KDVRate.STANDARD.value == Decimal("0.20")

    def test_reduced_rate(self):
        """Test reduced KDV rate is 10%."""
        assert KDVRate.REDUCED.value == Decimal("0.10")

    def test_super_reduced_rate(self):
        """Test super-reduced KDV rate is 1%."""
        assert KDVRate.SUPER_REDUCED.value == Decimal("0.01")

    def test_exempt_rate(self):
        """Test exempt rate is 0%."""
        assert KDVRate.EXEMPT.value == Decimal("0.00")

    def test_from_percentage_standard(self):
        """Test getting rate from percentage."""
        assert KDVRate.from_percentage(20) == KDVRate.STANDARD
        assert KDVRate.from_percentage(10) == KDVRate.REDUCED
        assert KDVRate.from_percentage(1) == KDVRate.SUPER_REDUCED

    def test_from_percentage_invalid(self):
        """Test invalid percentage raises error."""
        with pytest.raises(ValueError):
            KDVRate.from_percentage(15)


class TestCalculateKDV:
    """Tests for calculate_kdv function."""

    def test_standard_rate(self):
        """Test KDV calculation with standard rate."""
        assert calculate_kdv(10000) == 2000  # 100 TRY -> 20 TRY KDV

    def test_reduced_rate(self):
        """Test KDV calculation with reduced rate."""
        assert calculate_kdv(10000, KDVRate.REDUCED) == 1000  # 100 TRY -> 10 TRY KDV

    def test_super_reduced_rate(self):
        """Test KDV calculation with super-reduced rate."""
        assert calculate_kdv(10000, KDVRate.SUPER_REDUCED) == 100  # 100 TRY -> 1 TRY KDV

    def test_exempt_rate(self):
        """Test KDV calculation with exempt rate."""
        assert calculate_kdv(10000, KDVRate.EXEMPT) == 0

    def test_rounding(self):
        """Test proper rounding of KDV."""
        # 33.33 TRY -> 6.666 TRY KDV -> should round to 667 kuruş
        assert calculate_kdv(3333) == 667


class TestAmountWithKDV:
    """Tests for amount_with_kdv function."""

    def test_standard_rate(self):
        """Test gross amount with standard KDV."""
        assert amount_with_kdv(10000) == 12000  # 100 + 20 = 120 TRY

    def test_reduced_rate(self):
        """Test gross amount with reduced KDV."""
        assert amount_with_kdv(10000, KDVRate.REDUCED) == 11000  # 100 + 10 = 110 TRY


class TestExtractKDV:
    """Tests for extract_kdv function."""

    def test_standard_rate(self):
        """Test extracting KDV from gross amount."""
        net, kdv = extract_kdv(12000)
        assert net == 10000
        assert kdv == 2000

    def test_reduced_rate(self):
        """Test extracting KDV with reduced rate."""
        net, kdv = extract_kdv(11000, KDVRate.REDUCED)
        assert net == 10000
        assert kdv == 1000

    def test_round_trip(self):
        """Test that extract_kdv reverses amount_with_kdv."""
        original = 9999
        gross = amount_with_kdv(original)
        net, kdv = extract_kdv(gross)
        assert net == original


class TestGetKDVBreakdown:
    """Tests for get_kdv_breakdown function."""

    def test_breakdown(self):
        """Test full KDV breakdown."""
        breakdown = get_kdv_breakdown(12000)
        assert breakdown.net_amount == 10000
        assert breakdown.kdv_amount == 2000
        assert breakdown.gross_amount == 12000
        assert breakdown.rate == KDVRate.STANDARD


class TestFormatCurrency:
    """Tests for format_currency function."""

    def test_turkish_format(self):
        """Test Turkish currency format."""
        assert format_currency(12345) == "123,45 TL"
        assert format_currency(100000) == "1.000,00 TL"

    def test_international_format(self):
        """Test international currency format."""
        assert format_currency(12345, locale="en_US") == "123.45 TRY"


class TestCommission:
    """Tests for commission calculation."""

    def test_default_commission(self):
        """Test default 10% commission."""
        assert calculate_commission(10000) == 1000

    def test_custom_commission(self):
        """Test custom commission rate."""
        assert calculate_commission(10000, 0.15) == 1500

    def test_net_after_commission(self):
        """Test net amount after commission."""
        assert net_after_commission(10000) == 9000
        assert net_after_commission(10000, 0.15) == 8500
