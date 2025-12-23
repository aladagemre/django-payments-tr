"""Tests for EFT payment module."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from payments_tr.eft.models import EFTStatus
from payments_tr.eft.services import ApprovalResult, EFTApprovalService, EFTPaymentProtocol


class MockEFTPayment:
    """Mock EFT payment for testing the protocol."""

    def __init__(self):
        self.id = 1
        self.eft_reference_number = "REF123"
        self.eft_bank_name = "Test Bank"
        self.eft_transfer_date = date.today()
        self.eft_sender_name = "Test Sender"
        self.approved_at = None
        self.approved_by = None
        self.rejected_at = None
        self.rejected_by = None
        self.rejection_reason = ""

    def approve(self, user, save=True):
        self.approved_by = user
        self.approved_at = timezone.now()
        self.rejected_by = None
        self.rejected_at = None
        self.rejection_reason = ""

    def reject(self, user, reason="", save=True):
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.approved_by = None
        self.approved_at = None


class TestEFTStatus:
    """Tests for EFTStatus choices."""

    def test_status_values(self):
        """Test that status choices have correct values."""
        assert EFTStatus.PENDING == "pending"
        assert EFTStatus.APPROVED == "approved"
        assert EFTStatus.REJECTED == "rejected"

    def test_status_labels(self):
        """Test that status choices have correct labels."""
        assert EFTStatus.PENDING.label == "Pending Review"
        assert EFTStatus.APPROVED.label == "Approved"
        assert EFTStatus.REJECTED.label == "Rejected"


class TestEFTPaymentProtocol:
    """Tests for EFT payment protocol."""

    def test_mock_payment_implements_protocol(self):
        """Test that mock payment implements the protocol."""
        payment = MockEFTPayment()
        assert isinstance(payment, EFTPaymentProtocol)

    def test_protocol_attributes(self):
        """Test protocol required attributes."""
        payment = MockEFTPayment()
        assert hasattr(payment, "eft_reference_number")
        assert hasattr(payment, "approved_at")
        assert hasattr(payment, "rejected_at")


class TestApprovalResult:
    """Tests for ApprovalResult dataclass."""

    def test_success_result(self):
        """Test creating a success result."""
        result = ApprovalResult(
            success=True,
            payment_id=1,
            action="approved",
        )
        assert result.success is True
        assert result.payment_id == 1
        assert result.action == "approved"
        assert result.error is None

    def test_failure_result(self):
        """Test creating a failure result."""
        result = ApprovalResult(
            success=False,
            payment_id=1,
            action="approved",
            error="Payment already approved",
        )
        assert result.success is False
        assert result.error == "Payment already approved"


class TestEFTApprovalService:
    """Tests for EFT approval service."""

    @pytest.fixture
    def service(self):
        """Create EFT approval service."""
        return EFTApprovalService()

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock()
        user.id = 1
        user.__str__ = MagicMock(return_value="testuser")
        return user

    @pytest.fixture
    def mock_payment(self):
        """Create mock payment."""
        return MockEFTPayment()

    @patch("payments_tr.eft.services.transaction")
    def test_approve_payment_success(self, mock_transaction, service, mock_user, mock_payment):
        """Test successful payment approval."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        result = service.approve_payment(mock_payment, mock_user)

        assert result.success is True
        assert result.action == "approved"
        assert mock_payment.approved_at is not None
        assert mock_payment.approved_by == mock_user

    def test_approve_payment_no_reference(self, service, mock_user, mock_payment):
        """Test approval fails without reference number."""
        mock_payment.eft_reference_number = None

        result = service.approve_payment(mock_payment, mock_user)

        assert result.success is False
        assert "no EFT reference number" in result.error

    def test_approve_payment_already_approved(self, service, mock_user, mock_payment):
        """Test approval fails if already approved."""
        mock_payment.approved_at = timezone.now()

        result = service.approve_payment(mock_payment, mock_user)

        assert result.success is False
        assert "already approved" in result.error

    @patch("payments_tr.eft.services.transaction")
    def test_reject_payment_success(self, mock_transaction, service, mock_user, mock_payment):
        """Test successful payment rejection."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        result = service.reject_payment(mock_payment, mock_user, reason="Invalid receipt")

        assert result.success is True
        assert result.action == "rejected"
        assert mock_payment.rejected_at is not None
        assert mock_payment.rejection_reason == "Invalid receipt"

    def test_reject_payment_already_rejected(self, service, mock_user, mock_payment):
        """Test rejection fails if already rejected."""
        mock_payment.rejected_at = timezone.now()

        result = service.reject_payment(mock_payment, mock_user)

        assert result.success is False
        assert "already rejected" in result.error

    @patch("payments_tr.eft.services.transaction")
    def test_bulk_approve(self, mock_transaction, service, mock_user):
        """Test bulk approval."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payments = [MockEFTPayment() for _ in range(3)]

        results = service.bulk_approve(payments, mock_user)

        assert len(results) == 3
        assert all(r.success for r in results)

    @patch("payments_tr.eft.services.transaction")
    def test_bulk_reject(self, mock_transaction, service, mock_user):
        """Test bulk rejection."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payments = [MockEFTPayment() for _ in range(3)]

        results = service.bulk_reject(payments, mock_user, reason="Bulk rejection")

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_get_pending_payments(self, service):
        """Test filtering pending payments."""
        queryset = MagicMock()
        service.get_pending_payments(queryset)

        queryset.filter.assert_called_once_with(
            eft_reference_number__isnull=False,
            approved_at__isnull=True,
            rejected_at__isnull=True,
        )

    @patch("payments_tr.eft.services.transaction")
    def test_on_approved_hook(self, mock_transaction, service, mock_user, mock_payment):
        """Test on_approved hook is called."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        service.on_approved = MagicMock()
        service.approve_payment(mock_payment, mock_user, notify=True)

        service.on_approved.assert_called_once_with(mock_payment, mock_user)

    @patch("payments_tr.eft.services.transaction")
    def test_on_rejected_hook(self, mock_transaction, service, mock_user, mock_payment):
        """Test on_rejected hook is called."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        service.on_rejected = MagicMock()
        service.reject_payment(mock_payment, mock_user, reason="Test", notify=True)

        service.on_rejected.assert_called_once_with(mock_payment, mock_user, "Test")

    @patch("payments_tr.eft.services.transaction")
    def test_approve_without_notify(self, mock_transaction, service, mock_user, mock_payment):
        """Test approval without notification."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        service.on_approved = MagicMock()
        service.approve_payment(mock_payment, mock_user, notify=False)

        service.on_approved.assert_not_called()

    @patch("payments_tr.eft.services.transaction")
    def test_approve_payment_exception(self, mock_transaction, service, mock_user, mock_payment):
        """Test approval handles exceptions."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)
        mock_payment.approve = MagicMock(side_effect=Exception("DB error"))

        result = service.approve_payment(mock_payment, mock_user)

        assert result.success is False
        assert "DB error" in result.error

    @patch("payments_tr.eft.services.transaction")
    def test_reject_payment_exception(self, mock_transaction, service, mock_user, mock_payment):
        """Test rejection handles exceptions."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)
        mock_payment.reject = MagicMock(side_effect=Exception("DB error"))

        result = service.reject_payment(mock_payment, mock_user)

        assert result.success is False
        assert "DB error" in result.error


class TestCustomEFTService:
    """Test custom EFT service subclass."""

    @patch("payments_tr.eft.services.transaction")
    def test_custom_hooks(self, mock_transaction):
        """Test custom service with overridden hooks."""
        mock_transaction.atomic.return_value.__enter__ = MagicMock()
        mock_transaction.atomic.return_value.__exit__ = MagicMock(return_value=False)

        approved_payments = []
        rejected_payments = []

        class CustomService(EFTApprovalService):
            def on_approved(self, payment, user):
                approved_payments.append(payment.id)

            def on_rejected(self, payment, user, reason):
                rejected_payments.append((payment.id, reason))

        service = CustomService()
        user = MagicMock()
        user.id = 1

        payment1 = MockEFTPayment()
        payment1.id = 101
        service.approve_payment(payment1, user)

        payment2 = MockEFTPayment()
        payment2.id = 102
        service.reject_payment(payment2, user, reason="Bad receipt")

        assert approved_payments == [101]
        assert rejected_payments == [(102, "Bad receipt")]
