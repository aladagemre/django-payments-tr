"""Tests for EFT admin module."""

from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from payments_tr.eft.admin import EFTPaymentAdminMixin, EFTPaymentListFilter


class MockEFTPayment:
    """Mock EFT payment for admin tests."""

    def __init__(self):
        self.id = 1
        self.eft_reference_number = "REF123"
        self.approved_at = None
        self.rejected_at = None
        self.is_eft_approved = False
        self.is_eft_rejected = False

    def approve(self, user, save=True):
        self.approved_at = timezone.now()
        self.is_eft_approved = True

    def reject(self, user, reason="", save=True):
        self.rejected_at = timezone.now()
        self.is_eft_rejected = True


class TestEFTPaymentAdminMixin:
    """Tests for EFTPaymentAdminMixin."""

    @pytest.fixture
    def admin_mixin(self):
        """Create admin mixin instance."""
        mixin = EFTPaymentAdminMixin()
        return mixin

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = MagicMock()
        request.user = MagicMock()
        request.user.id = 1
        return request

    def test_eft_status_display_approved(self, admin_mixin):
        """Test status display for approved payment."""
        payment = MockEFTPayment()
        payment.is_eft_approved = True

        result = admin_mixin.eft_status_display(payment)

        assert "Approved" in result
        assert "#28a745" in result  # Green color

    def test_eft_status_display_rejected(self, admin_mixin):
        """Test status display for rejected payment."""
        payment = MockEFTPayment()
        payment.is_eft_rejected = True

        result = admin_mixin.eft_status_display(payment)

        assert "Rejected" in result
        assert "#dc3545" in result  # Red color

    def test_eft_status_display_pending(self, admin_mixin):
        """Test status display for pending payment."""
        payment = MockEFTPayment()

        result = admin_mixin.eft_status_display(payment)

        assert "Pending" in result
        assert "#ffc107" in result  # Yellow color

    def test_eft_status_display_no_eft(self, admin_mixin):
        """Test status display for non-EFT payment."""
        payment = MockEFTPayment()
        payment.eft_reference_number = None

        result = admin_mixin.eft_status_display(payment)

        assert "N/A" in result

    def test_approve_eft_payments_action(self, admin_mixin, mock_request):
        """Test approve action."""
        payments = [MockEFTPayment() for _ in range(3)]
        queryset = MagicMock()
        queryset.__iter__ = MagicMock(return_value=iter(payments))

        admin_mixin.message_user = MagicMock()
        admin_mixin._on_eft_approved = MagicMock()

        admin_mixin.approve_eft_payments(mock_request, queryset)

        assert all(p.is_eft_approved for p in payments)
        admin_mixin.message_user.assert_called_once()
        assert admin_mixin._on_eft_approved.call_count == 3

    def test_reject_eft_payments_action(self, admin_mixin, mock_request):
        """Test reject action."""
        payments = [MockEFTPayment() for _ in range(2)]
        queryset = MagicMock()
        queryset.__iter__ = MagicMock(return_value=iter(payments))

        admin_mixin.message_user = MagicMock()
        admin_mixin._on_eft_rejected = MagicMock()

        admin_mixin.reject_eft_payments(mock_request, queryset)

        assert all(p.is_eft_rejected for p in payments)
        admin_mixin.message_user.assert_called_once()

    def test_mixin_has_required_attributes(self, admin_mixin):
        """Test mixin has required class attributes."""
        assert hasattr(admin_mixin, "actions")
        assert "approve_eft_payments" in admin_mixin.actions
        assert "reject_eft_payments" in admin_mixin.actions
        assert hasattr(admin_mixin, "eft_fieldset")
        assert hasattr(admin_mixin, "approval_fieldset")

    def test_on_eft_approved_hook_default(self, admin_mixin, mock_request):
        """Test default _on_eft_approved hook does nothing."""
        payment = MockEFTPayment()
        # Should not raise
        admin_mixin._on_eft_approved(mock_request, payment)

    def test_on_eft_rejected_hook_default(self, admin_mixin, mock_request):
        """Test default _on_eft_rejected hook does nothing."""
        payment = MockEFTPayment()
        # Should not raise
        admin_mixin._on_eft_rejected(mock_request, payment)

    def test_approve_payment_without_method(self, admin_mixin, mock_request):
        """Test approve action skips payments without approve method."""
        payment = MagicMock(spec=[])  # No approve method
        queryset = MagicMock()
        queryset.__iter__ = MagicMock(return_value=iter([payment]))

        admin_mixin.message_user = MagicMock()

        admin_mixin.approve_eft_payments(mock_request, queryset)

        # Should complete without error, count should be 0
        call_args = admin_mixin.message_user.call_args[0]
        assert "0 EFT payment" in call_args[1]


class TestEFTPaymentListFilter:
    """Tests for EFTPaymentListFilter."""

    @pytest.fixture
    def list_filter(self):
        """Create list filter instance."""
        return EFTPaymentListFilter(
            request=MagicMock(),
            params={},
            model=MagicMock(),
            model_admin=MagicMock(),
        )

    def test_lookups(self, list_filter):
        """Test filter lookups."""
        lookups = list_filter.lookups(MagicMock(), MagicMock())

        assert len(lookups) == 4
        lookup_values = [item[0] for item in lookups]
        assert "pending" in lookup_values
        assert "approved" in lookup_values
        assert "rejected" in lookup_values
        assert "no_eft" in lookup_values

    def test_queryset_pending(self, list_filter):
        """Test filtering pending payments."""
        list_filter.value = MagicMock(return_value="pending")
        queryset = MagicMock()

        list_filter.queryset(MagicMock(), queryset)

        queryset.filter.assert_called_once_with(
            eft_reference_number__isnull=False,
            approved_at__isnull=True,
            rejected_at__isnull=True,
        )

    def test_queryset_approved(self, list_filter):
        """Test filtering approved payments."""
        list_filter.value = MagicMock(return_value="approved")
        queryset = MagicMock()

        list_filter.queryset(MagicMock(), queryset)

        queryset.filter.assert_called_once_with(approved_at__isnull=False)

    def test_queryset_rejected(self, list_filter):
        """Test filtering rejected payments."""
        list_filter.value = MagicMock(return_value="rejected")
        queryset = MagicMock()

        list_filter.queryset(MagicMock(), queryset)

        queryset.filter.assert_called_once_with(rejected_at__isnull=False)

    def test_queryset_no_eft(self, list_filter):
        """Test filtering non-EFT payments."""
        list_filter.value = MagicMock(return_value="no_eft")
        queryset = MagicMock()

        list_filter.queryset(MagicMock(), queryset)

        queryset.filter.assert_called_once_with(eft_reference_number__isnull=True)

    def test_queryset_no_filter(self, list_filter):
        """Test no filtering when no value selected."""
        list_filter.value = MagicMock(return_value=None)
        queryset = MagicMock()

        result = list_filter.queryset(MagicMock(), queryset)

        assert result == queryset
        queryset.filter.assert_not_called()
