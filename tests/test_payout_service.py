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
