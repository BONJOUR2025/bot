import asyncio
import types
from unittest.mock import AsyncMock

from app.services.telegram_service import TelegramService
from app.core.types import Employee
from app.schemas.message import SentMessage


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


def test_send_payout_request_uses_card_number():
    repo = DummyRepo()
    svc = TelegramService(repo)
    svc.bot = types.SimpleNamespace(send_message=AsyncMock())

    payout = {
        "id": "1",
        "name": "Test",
        "phone": "79990000000",
        "card_number": "5555 6666 7777 8888",
        "bank": "Т-Банк",
        "amount": 1000,
        "method": "💳 На карту",
        "payout_type": "Аванс",
    }

    asyncio.run(svc.send_payout_request_to_admin(payout))

    args, kwargs = svc.bot.send_message.await_args
    assert "5555 6666 7777 8888" in kwargs["text"]
    assert "79990000000" not in kwargs["text"]
