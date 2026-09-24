import asyncio
from app.schemas.payout import PayoutCreate
from app.services.payout_service import PayoutService


class DummyPayoutRepository:
    def __init__(self) -> None:
        self.created = None

    def reload(self) -> None:
        pass

    def create(self, data):
        self.created = data.copy()
        self.created.setdefault("id", "1")
        return self.created


class DummyTelegramService:
    def __init__(self) -> None:
        self.last_payload = None

    async def send_payout_request_to_admin(self, payload):
        self.last_payload = payload


def test_create_payout_keeps_card_number_in_payload():
    repo = DummyPayoutRepository()
    telegram = DummyTelegramService()
    service = PayoutService(repo=repo, telegram_service=telegram)

    data = PayoutCreate(
        user_id="7",
        name="Test User",
        phone="79998887766",
        card_number="1111 2222 3333 4444",
        bank="Т-Банк",
        amount=12345,
        method="💳 На карту",
        payout_type="Аванс",
        sync_to_bot=True,
    )

    payout = asyncio.run(service.create_payout(data))

    assert repo.created["card_number"] == "1111 2222 3333 4444"
    assert telegram.last_payload["card_number"] == "1111 2222 3333 4444"
    assert payout.card_number == "1111 2222 3333 4444"


def test_approve_and_notify_cashier(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import pytest

    from app.handlers.admin import payout_actions
    from app.services.payout_service import PayoutService

    sent = []

    async def fake_notice(bot, payout, chat=None):
        sent.append(payout["id"])
        return {"sent": True, "chat": "Кассир", "error": None}

    monkeypatch.setattr(payout_actions, "send_cashier_notice", fake_notice)
    svc = PayoutService.__new__(PayoutService)
    rows = {"7": {"id": 7, "user_id": "1", "status": "Ожидает"}}
    svc._repo = SimpleNamespace(reload=lambda: None, load_all=lambda: list(rows.values()))
    svc._telegram = SimpleNamespace(bot=object())

    async def fake_update_status(pid, status, notify=True):
        rows[str(pid)]["status"] = status
        return SimpleNamespace(model_dump=lambda: dict(rows[str(pid)]))

    svc.update_status = fake_update_status
    res = asyncio.run(svc.approve_and_notify_cashier("7"))
    assert res["cashier"]["sent"] and rows["7"]["status"] == "Одобрено" and sent == [7]

    rows["7"]["status"] = "Выплачено"
    with pytest.raises(ValueError):
        asyncio.run(svc.approve_and_notify_cashier("7"))
