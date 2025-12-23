"""
Turkish identification and financial validation utilities.

This module provides validation for:
- TC Kimlik No (Turkish Citizenship Number) - 11-digit national ID
- Turkish IBAN (International Bank Account Number)
- VKN (Vergi Kimlik Numarasi / Tax Identification Number)
- Turkish phone numbers (+90 format)
"""

from __future__ import annotations

import re
from typing import NamedTuple


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, code: str = "invalid"):
        self.message = message
        self.code = code
        super().__init__(message)


class ValidationResult(NamedTuple):
    """Result of a validation operation."""

    is_valid: bool
    error: str | None = None
    formatted: str | None = None


def validate_tckn(tckn: str, raise_exception: bool = False) -> bool:
    """
    Validate Turkish Citizenship Number (TC Kimlik No).

    The TC Kimlik No is an 11-digit number with the following rules:
    1. First digit cannot be 0
    2. Sum of digits at odd positions × 7 - sum of even positions = 10th digit (mod 10)
    3. Sum of first 10 digits = 11th digit (mod 10)

    Args:
        tckn: The TC Kimlik No to validate (11 digits)
        raise_exception: If True, raises ValidationError instead of returning False

    Returns:
        True if valid, False otherwise

    Raises:
        ValidationError: If raise_exception=True and validation fails

    Example:
        >>> validate_tckn("10000000146")
        True
        >>> validate_tckn("12345678901")
        False
    """
    # Clean input
    tckn = tckn.strip().replace(" ", "")

    # Basic checks
    if len(tckn) != 11:
        if raise_exception:
            raise ValidationError("TC Kimlik No must be 11 digits", "invalid_length")
        return False

    if not tckn.isdigit():
        if raise_exception:
            raise ValidationError("TC Kimlik No must contain only digits", "invalid_format")
        return False

    if tckn[0] == "0":
        if raise_exception:
            raise ValidationError("TC Kimlik No cannot start with 0", "invalid_start")
        return False

    # Convert to list of integers
    digits = [int(d) for d in tckn]

    # Rule 1: (sum of odd positions × 7 - sum of even positions) mod 10 = 10th digit
    odd_sum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
    even_sum = digits[1] + digits[3] + digits[5] + digits[7]
    check1 = (odd_sum * 7 - even_sum) % 10

    if check1 != digits[9]:
        if raise_exception:
            raise ValidationError("TC Kimlik No checksum failed (digit 10)", "invalid_checksum")
        return False

    # Rule 2: sum of first 10 digits mod 10 = 11th digit
    check2 = sum(digits[:10]) % 10

    if check2 != digits[10]:
        if raise_exception:
            raise ValidationError("TC Kimlik No checksum failed (digit 11)", "invalid_checksum")
        return False

    return True


def format_tckn(tckn: str) -> str:
    """
    Format TC Kimlik No with spaces for readability.

    Args:
        tckn: The TC Kimlik No to format

    Returns:
        Formatted string (e.g., "123 456 789 01")

    Example:
        >>> format_tckn("10000000146")
        "100 000 001 46"
    """
    tckn = tckn.strip().replace(" ", "")
    if len(tckn) != 11:
        return tckn
    return f"{tckn[:3]} {tckn[3:6]} {tckn[6:9]} {tckn[9:]}"


def validate_iban_tr(iban: str, raise_exception: bool = False) -> bool:
    """
    Validate Turkish IBAN (International Bank Account Number).

    Turkish IBAN format: TR + 2 check digits + 5-digit bank code + 16-digit account
    Total: 26 characters

    Args:
        iban: The IBAN to validate
        raise_exception: If True, raises ValidationError instead of returning False

    Returns:
        True if valid, False otherwise

    Raises:
        ValidationError: If raise_exception=True and validation fails

    Example:
        >>> validate_iban_tr("TR330006100519786457841326")
        True
    """
    # Clean input
    iban = iban.strip().replace(" ", "").upper()

    # Check length
    if len(iban) != 26:
        if raise_exception:
            raise ValidationError("Turkish IBAN must be 26 characters", "invalid_length")
        return False

    # Check country code
    if not iban.startswith("TR"):
        if raise_exception:
            raise ValidationError("Turkish IBAN must start with TR", "invalid_country")
        return False

    # Check format (TR + 24 digits)
    if not iban[2:].isdigit():
        if raise_exception:
            raise ValidationError("IBAN must contain only digits after TR", "invalid_format")
        return False

    # IBAN mod 97 check
    # Move first 4 chars to end, replace letters with numbers (A=10, B=11, etc.)
    rearranged = iban[4:] + iban[:4]
    numeric = ""
    for char in rearranged:
        if char.isdigit():
            numeric += char
        else:
            numeric += str(ord(char) - ord("A") + 10)

    if int(numeric) % 97 != 1:
        if raise_exception:
            raise ValidationError("IBAN checksum failed", "invalid_checksum")
        return False

    return True


def format_iban(iban: str) -> str:
    """
    Format IBAN with spaces for readability.

    Args:
        iban: The IBAN to format

    Returns:
        Formatted IBAN (groups of 4)

    Example:
        >>> format_iban("TR330006100519786457841326")
        "TR33 0006 1005 1978 6457 8413 26"
    """
    iban = iban.strip().replace(" ", "").upper()
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def validate_vkn(vkn: str, raise_exception: bool = False) -> bool:
    """
    Validate Turkish Tax Identification Number (Vergi Kimlik Numarasi).

    VKN is a 10-digit number for businesses/entities.
    Uses the Turkish VKN algorithm for validation.

    Args:
        vkn: The VKN to validate (10 digits)
        raise_exception: If True, raises ValidationError instead of returning False

    Returns:
        True if valid, False otherwise

    Raises:
        ValidationError: If raise_exception=True and validation fails

    Example:
        >>> validate_vkn("1234567890")
        # Returns True or False based on checksum
    """
    # Clean input
    vkn = vkn.strip().replace(" ", "")

    # Basic checks
    if len(vkn) != 10:
        if raise_exception:
            raise ValidationError("VKN must be 10 digits", "invalid_length")
        return False

    if not vkn.isdigit():
        if raise_exception:
            raise ValidationError("VKN must contain only digits", "invalid_format")
        return False

    # VKN algorithm
    digits = [int(d) for d in vkn]
    total = 0

    for i in range(9):
        tmp = (digits[i] + (9 - i)) % 10
        total += (tmp * (2 ** (9 - i))) % 9
        if tmp != 0 and (tmp * (2 ** (9 - i))) % 9 == 0:
            total += 9

    check_digit = (10 - (total % 10)) % 10

    if check_digit != digits[9]:
        if raise_exception:
            raise ValidationError("VKN checksum failed", "invalid_checksum")
        return False

    return True


def validate_phone_tr(phone: str, raise_exception: bool = False) -> bool:
    """
    Validate Turkish phone number.

    Accepts formats:
    - +905551234567
    - 905551234567
    - 05551234567
    - 5551234567

    Args:
        phone: The phone number to validate
        raise_exception: If True, raises ValidationError instead of returning False

    Returns:
        True if valid, False otherwise

    Raises:
        ValidationError: If raise_exception=True and validation fails

    Example:
        >>> validate_phone_tr("+905551234567")
        True
    """
    # Clean input
    phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Remove + prefix
    if phone.startswith("+"):
        phone = phone[1:]

    # Normalize to 10-digit format
    if phone.startswith("90"):
        phone = phone[2:]
    elif phone.startswith("0"):
        phone = phone[1:]

    # Should now be 10 digits starting with 5
    if len(phone) != 10:
        if raise_exception:
            raise ValidationError("Turkish phone must be 10 digits", "invalid_length")
        return False

    if not phone.isdigit():
        if raise_exception:
            raise ValidationError("Phone must contain only digits", "invalid_format")
        return False

    if not phone.startswith("5"):
        if raise_exception:
            raise ValidationError("Turkish mobile numbers must start with 5", "invalid_prefix")
        return False

    return True


def format_phone(phone: str, international: bool = True) -> str:
    """
    Format Turkish phone number.

    Args:
        phone: The phone number to format
        international: If True, use +90 format; otherwise use 0 format

    Returns:
        Formatted phone number

    Example:
        >>> format_phone("5551234567")
        "+90 555 123 45 67"
        >>> format_phone("5551234567", international=False)
        "0555 123 45 67"
    """
    # Clean to 10 digits
    phone = re.sub(r"[^\d]", "", phone)
    if phone.startswith("90"):
        phone = phone[2:]
    elif phone.startswith("0"):
        phone = phone[1:]

    if len(phone) != 10:
        return phone

    if international:
        return f"+90 {phone[:3]} {phone[3:6]} {phone[6:8]} {phone[8:]}"
    else:
        return f"0{phone[:3]} {phone[3:6]} {phone[6:8]} {phone[8:]}"
