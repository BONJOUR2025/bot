import asyncio
import sys
import types
from unittest.mock import AsyncMock

from app.services.telegram_service import TelegramService
from app.core.types import Employee
sys.modules.setdefault(
    "fdb",
    types.SimpleNamespace(Connection=type("Connection", (), {})),
)

from app.schemas.message import SentMessage
from app.api.telegram import _to_sent_message


class DummyRepo:
    def list_employees(self, **filters):
        return [Employee(id="123456", name="Test", full_name="Test User", phone="123")] 


def test_broadcast_unknown_placeholder_does_not_crash():
    async def _run():
        repo = DummyRepo()
        svc = TelegramService(repo)
        svc.bot = types.SimpleNamespace(send_message=AsyncMock())
        result = await svc.broadcast_message_to_all("Hello {unknown}")
        assert result["success"] is True
        assert result["sent"] == 0
        assert svc.bot.send_message.call_count == 0

    asyncio.run(_run())


def test_sent_message_schema_allows_broadcast_without_status():
    entry = {
        "id": "123",
        "broadcast": True,
        "message": "Test broadcast",
        "timestamp": "2024-01-01T00:00:00",
        "recipients": [],
    }

    model = SentMessage(**entry)

    assert model.broadcast is True
    assert model.status is None


def test_to_sent_message_builds_summary_for_broadcast():
    raw_entry = {
        "id": "321",
        "broadcast": True,
        "message": "Bulk message",
        "timestamp": "2024-01-01T00:00:00",
        "recipients": [
            {"user_id": "1", "status": "отправлено"},
            {"user_id": "2", "status": "ошибка: chat not found"},
            {"user_id": "3", "status": "невалидный id"},
        ],
    }

    parsed = _to_sent_message(raw_entry)

    assert parsed.summary is not None
    assert parsed.summary.total == 3
    assert parsed.summary.success == 1
    assert parsed.summary.errors == 1
    assert parsed.summary.invalid == 1
    assert "отправлено 1/3" in (parsed.status or "")
    assert "ошибки 1" in (parsed.status or "")
