import asyncio
import types
from unittest.mock import AsyncMock

from app.services.telegram_service import TelegramService
from app.core.types import Employee


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
