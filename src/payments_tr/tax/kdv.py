"""
KDV (Katma Deger Vergisi / Value Added Tax) calculation utilities.

Turkish VAT rates as of 2024:
- Standard rate: 20% (increased from 18% in July 2023)
- Reduced rate: 10% (increased from 8%)
- Super-reduced rate: 1% (basic necessities)

Note: Some services like healthcare and education are exempt.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import NamedTuple


class KDVRate(Enum):
    """
    Turkish KDV (VAT) rates.

    Standard rates as of 2024:
    - STANDARD (20%): Most goods and services
    - REDUCED (10%): Food, tourism, some services
    - SUPER_REDUCED (1%): Basic necessities, newspapers
    - EXEMPT (0%): Healthcare, education, exports

    Historical rates (pre-July 2023):
    - STANDARD_OLD (18%)
    - REDUCED_OLD (8%)
    """

    # Current rates (as of July 2023)
    STANDARD = Decimal("0.20")
    REDUCED = Decimal("0.10")
    SUPER_REDUCED = Decimal("0.01")
    EXEMPT = Decimal("0.00")

    # Historical rates (for reference/migration)
    STANDARD_OLD = Decimal("0.18")
    REDUCED_OLD = Decimal("0.08")

    @classmethod
    def from_percentage(cls, percentage: int | float) -> KDVRate:
        """
        Get KDVRate from percentage value.

        Args:
            percentage: VAT percentage (e.g., 20, 10, 1)

        Returns:
            Matching KDVRate

        Raises:
            ValueError: If no matching rate found

        Example:
            >>> KDVRate.from_percentage(20)
            KDVRate.STANDARD
        """
        decimal_value = Decimal(str(percentage)) / 100
        for rate in cls:
            if rate.value == decimal_value:
                return rate
        raise ValueError(f"No KDV rate matching {percentage}%")


class KDVBreakdown(NamedTuple):
    """
    Breakdown of a price into net amount and KDV.

    Attributes:
        net_amount: Amount before tax (in kuruş)
        kdv_amount: Tax amount (in kuruş)
        gross_amount: Total amount including tax (in kuruş)
        rate: KDV rate applied
    """

    net_amount: int
    kdv_amount: int
    gross_amount: int
    rate: KDVRate


def calculate_kdv(
    amount: int,
    rate: KDVRate = KDVRate.STANDARD,
) -> int:
    """
    Calculate KDV amount from a net amount.

    Args:
        amount: Net amount in kuruş (smallest currency unit)
        rate: KDV rate to apply (default: STANDARD 20%)

    Returns:
        KDV amount in kuruş

    Example:
        >>> calculate_kdv(10000)  # 100.00 TRY net
        2000  # 20.00 TRY KDV
        >>> calculate_kdv(10000, KDVRate.REDUCED)
        1000  # 10.00 TRY KDV
    """
    kdv = Decimal(amount) * rate.value
    return int(kdv.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def amount_with_kdv(
    net_amount: int,
    rate: KDVRate = KDVRate.STANDARD,
) -> int:
    """
    Calculate gross amount including KDV from net amount.

    Args:
        net_amount: Net amount in kuruş
        rate: KDV rate to apply (default: STANDARD 20%)

    Returns:
        Gross amount (net + KDV) in kuruş

    Example:
        >>> amount_with_kdv(10000)  # 100.00 TRY net
        12000  # 120.00 TRY gross (incl. 20% KDV)
    """
    return net_amount + calculate_kdv(net_amount, rate)


def extract_kdv(
    gross_amount: int,
    rate: KDVRate = KDVRate.STANDARD,
) -> tuple[int, int]:
    """
    Extract net amount and KDV from gross amount.

    Uses the formula: net = gross / (1 + rate)

    Args:
        gross_amount: Gross amount including KDV in kuruş
        rate: KDV rate that was applied (default: STANDARD 20%)

    Returns:
        Tuple of (net_amount, kdv_amount) in kuruş

    Example:
        >>> extract_kdv(12000)  # 120.00 TRY gross
        (10000, 2000)  # 100.00 TRY net, 20.00 TRY KDV
    """
    divisor = 1 + rate.value
    net = Decimal(gross_amount) / divisor
    net_rounded = int(net.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    kdv = gross_amount - net_rounded
    return net_rounded, kdv


def get_kdv_breakdown(
    gross_amount: int,
    rate: KDVRate = KDVRate.STANDARD,
) -> KDVBreakdown:
    """
    Get full KDV breakdown from gross amount.

    Args:
        gross_amount: Gross amount including KDV in kuruş
        rate: KDV rate that was applied

    Returns:
        KDVBreakdown with net, kdv, gross amounts and rate

    Example:
        >>> breakdown = get_kdv_breakdown(12000)
        >>> breakdown.net_amount
        10000
        >>> breakdown.kdv_amount
        2000
    """
    net_amount, kdv_amount = extract_kdv(gross_amount, rate)
    return KDVBreakdown(
        net_amount=net_amount,
        kdv_amount=kdv_amount,
        gross_amount=gross_amount,
        rate=rate,
    )


def format_currency(
    amount: int,
    currency: str = "TRY",
    locale: str = "tr_TR",
) -> str:
    """
    Format amount in kuruş as currency string.

    Args:
        amount: Amount in kuruş
        currency: Currency code (default: TRY)
        locale: Locale for formatting (default: tr_TR)

    Returns:
        Formatted currency string

    Example:
        >>> format_currency(12345)
        "123,45 TL"
        >>> format_currency(12345, locale="en_US")
        "123.45 TRY"
    """
    decimal_amount = Decimal(amount) / 100

    if locale.startswith("tr"):
        # Turkish format: 1.234,56 TL
        formatted = f"{decimal_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        symbol = "TL" if currency == "TRY" else currency
        return f"{formatted} {symbol}"
    else:
        # International format: 1,234.56 TRY
        return f"{decimal_amount:,.2f} {currency}"


def calculate_commission(
    amount: int,
    rate: Decimal | float = 0.10,
) -> int:
    """
    Calculate platform commission from payment amount.

    Args:
        amount: Payment amount in kuruş
        rate: Commission rate (default: 10%)

    Returns:
        Commission amount in kuruş

    Example:
        >>> calculate_commission(10000)  # 100.00 TRY
        1000  # 10.00 TRY commission
        >>> calculate_commission(10000, 0.15)  # 15% commission
        1500
    """
    commission = Decimal(amount) * Decimal(str(rate))
    return int(commission.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def net_after_commission(
    amount: int,
    commission_rate: Decimal | float = 0.10,
) -> int:
    """
    Calculate net amount after platform commission.

    Args:
        amount: Payment amount in kuruş
        commission_rate: Commission rate (default: 10%)

    Returns:
        Net amount after commission in kuruş

    Example:
        >>> net_after_commission(10000)  # 100.00 TRY
        9000  # 90.00 TRY after 10% commission
    """
    return amount - calculate_commission(amount, commission_rate)
