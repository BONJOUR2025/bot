"""Comprehensive tests for PayoutService."""

import json
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.data.payout_repository import PayoutRepository
from app.services.payout_service import PayoutService
from app.schemas.payout import PayoutCreate, PayoutUpdate, Payout
from app.core.enums import PAYOUT_STATUSES
from tests.conftest import make_payout_dict, run_async


def _make_service(tmp_path, data=None, telegram=None):
    p = tmp_path / "payouts.json"
    if data is None:
        data = [
            make_payout_dict(1, status="Ожидает"),
            make_payout_dict(2, user_id="200", status="Одобрено"),
        ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    repo = PayoutRepository(file_path=str(p))
    return PayoutService(repo=repo, telegram_service=telegram)


class TestPayoutServiceList:
    def test_list_all(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_payouts()
            assert len(result) == 2
            assert all(isinstance(r, Payout) for r in result)
        run_async(_run())

    def test_list_filtered(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_payouts(status="Одобрено")
            assert len(result) == 1
        run_async(_run())


class TestPayoutServiceCreate:
    def test_create_payout(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            data = PayoutCreate(
                user_id="100", name="Иван", phone="+79001234567",
                bank="Сбер", amount=5000, method="💳 На карту",
                payout_type="Аванс",
            )
            result = await svc.create_payout(data)
            assert isinstance(result, Payout)
            assert result.status == PAYOUT_STATUSES[0]
            assert result.amount == 5000
        run_async(_run())

    def test_create_with_card_number(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            data = PayoutCreate(
                user_id="100", name="Иван", phone="+7",
                card_number="4111111111111111", bank="Сбер",
                amount=3000, method="💳 На карту", payout_type="Аванс",
            )
            result = await svc.create_payout(data)
            assert result.card_number == "4111111111111111"
        run_async(_run())

    def test_create_syncs_to_bot(self, tmp_path):
        telegram = MagicMock()
        telegram.send_payout_request_to_admin = AsyncMock()
        svc = _make_service(tmp_path, data=[], telegram=telegram)
        async def _run():
            data = PayoutCreate(
                user_id="100", name="Иван", phone="+7",
                bank="Сбер", amount=1000, method="💳 На карту",
                payout_type="Аванс", sync_to_bot=True,
            )
            await svc.create_payout(data)
            telegram.send_payout_request_to_admin.assert_called_once()
        run_async(_run())

    def test_create_without_sync(self, tmp_path):
        telegram = MagicMock()
        telegram.send_payout_request_to_admin = AsyncMock()
        svc = _make_service(tmp_path, data=[], telegram=telegram)
        async def _run():
            data = PayoutCreate(
                user_id="100", name="Иван", phone="+7",
                bank="Сбер", amount=1000, method="💳 На карту",
                payout_type="Аванс", sync_to_bot=False,
            )
            await svc.create_payout(data)
            telegram.send_payout_request_to_admin.assert_not_called()
        run_async(_run())

    def test_create_with_timestamp(self, tmp_path):
        svc = _make_service(tmp_path, data=[])
        async def _run():
            ts = datetime(2025, 6, 15, 12, 0, 0)
            data = PayoutCreate(
                user_id="100", name="T", phone="+7",
                bank="S", amount=100, method="m",
                payout_type="Аванс", timestamp=ts,
            )
            result = await svc.create_payout(data)
            assert "2025-06-15" in str(result.timestamp)
        run_async(_run())


class TestPayoutServiceUpdate:
    def test_update_payout(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            update = PayoutUpdate(amount=9999)
            result = await svc.update_payout("1", update)
            assert result is not None
            assert result.amount == 9999
        run_async(_run())

    def test_update_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            update = PayoutUpdate(amount=100)
            result = await svc.update_payout("999", update)
            assert result is None
        run_async(_run())

    def test_update_status_notifies_user(self, tmp_path):
        telegram = MagicMock()
        telegram.send_message_to_user = AsyncMock()
        svc = _make_service(tmp_path, telegram=telegram)
        async def _run():
            update = PayoutUpdate(status="Одобрено", notify_user=True)
            await svc.update_payout("1", update)
            telegram.send_message_to_user.assert_called_once()
        run_async(_run())

    def test_update_empty_returns_none(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            update = PayoutUpdate()
            result = await svc.update_payout("1", update)
            assert result is None
        run_async(_run())


class TestPayoutServiceUpdateStatus:
    def test_update_status(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.update_status("1", "Одобрено")
            assert result is not None
            assert result.status == "Одобрено"
        run_async(_run())

    def test_update_status_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.update_status("999", "Одобрено")
            assert result is None
        run_async(_run())


class TestPayoutServiceDelete:
    def test_delete_single(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            assert await svc.delete_payout("1") is True
        run_async(_run())

    def test_delete_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            assert await svc.delete_payout("999") is False
        run_async(_run())

    def test_delete_many(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            await svc.delete_payouts(["1", "2"])
            result = await svc.list_payouts()
            assert len(result) == 0
        run_async(_run())

    def test_delete_empty_list(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            await svc.delete_payouts([])
            result = await svc.list_payouts()
            assert len(result) == 2
        run_async(_run())


class TestPayoutServiceActivePayouts:
    def test_list_active(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            result = await svc.list_active_payouts()
            assert len(result) == 2
            statuses = {r.status for r in result}
            assert statuses.issubset(set(PAYOUT_STATUSES[:2]))
        run_async(_run())


class TestPayoutServiceGetEmployee:
    def test_get_employee(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_payout_employee("1") == "100"

    def test_get_employee_nonexistent(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.get_payout_employee("999") is None


class TestSerializeTimestamp:
    def test_datetime_object(self):
        result = PayoutService._serialize_timestamp(datetime(2025, 1, 15, 10, 30, 0))
        assert result == "2025-01-15 10:30:00"

    def test_iso_string(self):
        result = PayoutService._serialize_timestamp("2025-01-15T10:30:00")
        assert result == "2025-01-15 10:30:00"

    def test_already_formatted_string(self):
        result = PayoutService._serialize_timestamp("2025-01-15 10:30:00")
        assert result == "2025-01-15 10:30:00"

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            PayoutService._serialize_timestamp(12345)
