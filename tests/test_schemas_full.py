"""Comprehensive tests for Pydantic schemas."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.employee import EmployeeBase, EmployeeCreate, EmployeeUpdate, EmployeeOut
from app.schemas.payout import Payout, PayoutCreate, PayoutUpdate, PayoutControlItem
from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from app.schemas.incentive import Incentive, IncentiveCreate, IncentiveUpdate
from app.schemas.asset import Asset, AssetCreate, AssetUpdate
from app.schemas.message import MessageRequest, MessageOut, BroadcastRequest, SentMessage


# ---------------------------------------------------------------------------
# Employee schemas
# ---------------------------------------------------------------------------

class TestEmployeeSchemas:
    def test_employee_base_defaults(self):
        emp = EmployeeBase(name="Тест")
        assert emp.phone == ""
        assert emp.is_admin is False
        assert emp.status == "active"
        assert emp.archived is False

    def test_employee_create(self):
        emp = EmployeeCreate(name="Новый")
        assert emp.id == ""

    def test_employee_update(self):
        emp = EmployeeUpdate(name="Обновлённый")
        assert emp.name == "Обновлённый"

    def test_employee_out_requires_id(self):
        with pytest.raises(ValidationError):
            EmployeeOut(name="X")

    def test_employee_out_valid(self):
        emp = EmployeeOut(
            id="1", name="Тест", created_at=datetime.utcnow(),
        )
        assert emp.id == "1"

    def test_employee_birthdate_parsing(self):
        emp = EmployeeBase(name="X", birthdate="1990-05-15")
        assert emp.birthdate == date(1990, 5, 15)


# ---------------------------------------------------------------------------
# Payout schemas
# ---------------------------------------------------------------------------

class TestPayoutSchemas:
    def test_payout_minimal(self):
        p = Payout(user_id="1", name="X", phone="+7", bank="S",
                   amount=100, method="m", payout_type="Аванс", status="Ожидает")
        assert p.amount == 100
        assert p.card_number is None

    def test_payout_create(self):
        p = PayoutCreate(
            user_id="1", name="X", phone="+7", bank="S",
            amount=5000, method="m", payout_type="Аванс",
        )
        assert p.sync_to_bot is False
        assert p.force_notify_cashier is False

    def test_payout_update_all_optional(self):
        p = PayoutUpdate()
        assert p.user_id is None
        assert p.status is None

    def test_payout_control_item(self):
        item = PayoutControlItem(
            id="1", name="X", amount=100, status="Ожидает",
            type="Аванс", method="m",
        )
        assert item.warnings == []
        assert item.is_manual is False


# ---------------------------------------------------------------------------
# Vacation schemas
# ---------------------------------------------------------------------------

class TestVacationSchemas:
    def test_vacation_valid(self):
        v = Vacation(
            employee_id="1", name="X",
            start_date="2025-01-01", end_date="2025-01-14",
            type="Отпуск",
        )
        assert v.type == "Отпуск"

    def test_vacation_invalid_type(self):
        with pytest.raises(ValidationError):
            Vacation(
                employee_id="1", name="X",
                start_date="2025-01-01", end_date="2025-01-14",
                type="Прогул",
            )

    def test_vacation_create(self):
        v = VacationCreate(
            employee_id="1", name="X",
            start_date="2025-01-01", end_date="2025-01-14",
            type="Больничный",
        )
        assert v.comment == ""

    def test_vacation_update_all_optional(self):
        v = VacationUpdate()
        assert v.start_date is None


# ---------------------------------------------------------------------------
# Incentive schemas
# ---------------------------------------------------------------------------

class TestIncentiveSchemas:
    def test_incentive_valid(self):
        inc = Incentive(
            employee_id="1", name="X", type="bonus",
            amount=500, reason="test", date="2025-01-15", added_by="admin",
        )
        assert inc.locked is False

    def test_incentive_invalid_type(self):
        with pytest.raises(ValidationError):
            Incentive(
                employee_id="1", name="X", type="unknown",
                amount=100, reason="x", date="2025-01-01", added_by="admin",
            )

    def test_incentive_create(self):
        inc = IncentiveCreate(
            employee_id="1", name="X", type="penalty",
            amount=200, reason="test", date="2025-01-15", added_by="admin",
        )
        assert inc.type == "penalty"

    def test_incentive_update_optional(self):
        inc = IncentiveUpdate()
        assert inc.amount is None


# ---------------------------------------------------------------------------
# Asset schemas
# ---------------------------------------------------------------------------

class TestAssetSchemas:
    def test_asset_valid(self):
        a = Asset(
            employee_id="1", employee_name="X",
            item_name="Ботинки", issue_date="2025-01-10",
        )
        assert a.quantity == 1
        assert a.return_date is None

    def test_asset_create(self):
        a = AssetCreate(
            employee_id="1", employee_name="X",
            item_name="Кепка", issue_date="2025-01-01",
        )
        assert a.size == ""

    def test_asset_update_optional(self):
        a = AssetUpdate()
        assert a.item_name is None


# ---------------------------------------------------------------------------
# Message schemas
# ---------------------------------------------------------------------------

class TestMessageSchemas:
    def test_message_request(self):
        m = MessageRequest(user_id="1", message="Привет")
        assert m.parse_mode == "HTML"
        assert m.require_ack is False

    def test_message_out(self):
        m = MessageOut(
            id="1", user_id="1", name="X", text="Hi",
            status="Отправлено", accepted=False,
            timestamp="2025-01-15T10:00:00", message_id=100,
        )
        assert m.photo is None

    def test_broadcast_request(self):
        b = BroadcastRequest(message="Всем привет")
        assert b.birthday_today is False
        assert b.tags is None

    def test_sent_message(self):
        s = SentMessage(
            id="1", message="Hi", timestamp="2025-01-15T10:00:00",
        )
        assert s.broadcast is False
        assert s.accepted is False
