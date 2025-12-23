"""Tests for Turkish validation utilities."""

import pytest

from payments_tr.validation import (
    ValidationError,
    format_iban,
    format_phone,
    format_tckn,
    validate_iban_tr,
    validate_phone_tr,
    validate_tckn,
    validate_vkn,
)


class TestValidateTCKN:
    """Tests for TC Kimlik No validation."""

    def test_valid_tckn(self):
        """Test valid TC Kimlik numbers."""
        # These are algorithmically valid test numbers
        assert validate_tckn("10000000146") is True

    def test_invalid_length(self):
        """Test invalid length."""
        assert validate_tckn("1234567890") is False  # 10 digits
        assert validate_tckn("123456789012") is False  # 12 digits

    def test_invalid_start(self):
        """Test TCKN cannot start with 0."""
        assert validate_tckn("01234567890") is False

    def test_invalid_format(self):
        """Test non-digit characters."""
        assert validate_tckn("1234567890a") is False

    def test_invalid_checksum(self):
        """Test invalid checksum."""
        assert validate_tckn("12345678901") is False

    def test_raise_exception(self):
        """Test raising exception on invalid TCKN."""
        with pytest.raises(ValidationError) as exc_info:
            validate_tckn("123", raise_exception=True)
        assert exc_info.value.code == "invalid_length"

    def test_whitespace_handling(self):
        """Test that whitespace is stripped."""
        assert validate_tckn(" 10000000146 ") is True


class TestFormatTCKN:
    """Tests for TC Kimlik No formatting."""

    def test_format(self):
        """Test TCKN formatting."""
        assert format_tckn("10000000146") == "100 000 001 46"

    def test_invalid_length(self):
        """Test formatting with invalid length."""
        assert format_tckn("123") == "123"


class TestValidateIBANTR:
    """Tests for Turkish IBAN validation."""

    def test_valid_iban(self):
        """Test valid Turkish IBAN."""
        assert validate_iban_tr("TR330006100519786457841326") is True

    def test_invalid_length(self):
        """Test invalid length."""
        assert validate_iban_tr("TR33000610051978645784132") is False  # 25 chars

    def test_invalid_country(self):
        """Test non-Turkish IBAN."""
        assert validate_iban_tr("DE89370400440532013000") is False

    def test_invalid_checksum(self):
        """Test invalid IBAN checksum."""
        assert validate_iban_tr("TR000006100519786457841326") is False

    def test_raise_exception(self):
        """Test raising exception on invalid IBAN."""
        with pytest.raises(ValidationError) as exc_info:
            validate_iban_tr("TR123", raise_exception=True)
        assert exc_info.value.code == "invalid_length"

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert validate_iban_tr("tr330006100519786457841326") is True

    def test_whitespace_handling(self):
        """Test whitespace is stripped."""
        assert validate_iban_tr("TR33 0006 1005 1978 6457 8413 26") is True


class TestFormatIBAN:
    """Tests for IBAN formatting."""

    def test_format(self):
        """Test IBAN formatting."""
        assert format_iban("TR330006100519786457841326") == "TR33 0006 1005 1978 6457 8413 26"


class TestValidateVKN:
    """Tests for VKN (Tax Number) validation."""

    def test_invalid_length(self):
        """Test invalid length."""
        assert validate_vkn("123456789") is False  # 9 digits
        assert validate_vkn("12345678901") is False  # 11 digits

    def test_invalid_format(self):
        """Test non-digit characters."""
        assert validate_vkn("123456789a") is False

    def test_raise_exception(self):
        """Test raising exception on invalid VKN."""
        with pytest.raises(ValidationError) as exc_info:
            validate_vkn("123", raise_exception=True)
        assert exc_info.value.code == "invalid_length"


class TestValidatePhoneTR:
    """Tests for Turkish phone number validation."""

    def test_valid_formats(self):
        """Test various valid phone formats."""
        assert validate_phone_tr("+905551234567") is True
        assert validate_phone_tr("905551234567") is True
        assert validate_phone_tr("05551234567") is True
        assert validate_phone_tr("5551234567") is True

    def test_invalid_length(self):
        """Test invalid length."""
        assert validate_phone_tr("555123456") is False  # 9 digits

    def test_invalid_prefix(self):
        """Test invalid prefix (must start with 5)."""
        assert validate_phone_tr("4551234567") is False

    def test_raise_exception(self):
        """Test raising exception on invalid phone."""
        with pytest.raises(ValidationError) as exc_info:
            validate_phone_tr("123", raise_exception=True)
        assert exc_info.value.code == "invalid_length"


class TestFormatPhone:
    """Tests for phone number formatting."""

    def test_international_format(self):
        """Test international format."""
        assert format_phone("5551234567") == "+90 555 123 45 67"

    def test_local_format(self):
        """Test local format."""
        assert format_phone("5551234567", international=False) == "0555 123 45 67"
