import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.constants import PAYMENT_REQUEST_PATTERN, PayoutStates
from telegram_stub import Bot, Message, Update, CallbackQuery
from telegram_stub.ext import ConversationHandler
from datetime import datetime
from unittest.mock import AsyncMock, patch
import types
import pytest
import asyncio
from app.handlers.user import payout
from app.services import advance_requests


def _make_message(bot, text, update_id=1, chat_id=1, user_id=1):
    data = {
        "message_id": update_id,
        "date": int(datetime.now().timestamp()),
        "chat": {"id": chat_id, "type": "private"},
        "text": text,
        "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
    }
    msg = Message.de_json(data, bot)
    return Update(update_id=update_id, message=msg)


def _make_callback(bot, data, update_id=1, chat_id=1, user_id=1):
    payload = {
        "id": str(update_id),
        "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
        "chat_instance": "1",
        "data": data,
        "message": {
            "message_id": update_id,
            "chat": {"id": chat_id, "type": "private"},
            "date": int(datetime.now().timestamp()),
        },
    }
    cb = CallbackQuery.de_json(payload, bot)
    return Update(update_id=update_id, callback_query=cb)


class DummyRepo:
    def __init__(self):
        self.records = []
        self._file = "dummy.json"

    def create(self, data):
        self.records.append(data)
        return data

    def list(self, *args, **kwargs):
        return []


def test_payment_request_pattern_matches_regular_spaces():
    text = "💰 Запросить выплату"
    assert PAYMENT_REQUEST_PATTERN.match(text)


def test_payment_request_pattern_matches_nbsp():
    text = "\u00A0💰\u00A0Запросить\u00A0выплату\u00A0"
    assert PAYMENT_REQUEST_PATTERN.match(text)


def test_payment_request_pattern_ignore_case():
    text = "💰 ЗАПРОСИТЬ ВЫПЛАТУ"
    assert PAYMENT_REQUEST_PATTERN.match(text)


def test_payment_request_pattern_triggers_start():
    async def _run():
        bot = Bot("TEST", request=AsyncMock())
        context = types.SimpleNamespace(
            application=types.SimpleNamespace(chat_data={}), user_data={}
        )
        with (
        patch("telegram_stub.Message.reply_text", new=AsyncMock()) as reply,
        patch("app.handlers.user.payout.load_users_map", return_value={"1": {
            "name": "Test",
            "phone": "123",
            "bank": "TB",
            "card_number": "9999",
        }}),
        patch("app.handlers.user.payout.check_pending_request", return_value=False),
    ):
            update = _make_message(bot, "💰 Запросить выплату")
            state = await payout.request_payout_start(update, context)
        assert state == PayoutStates.SELECT_TYPE
        assert context.user_data["payout_in_progress"] is True
        assert reply.called

    asyncio.run(_run())


def test_full_payout_conversation_creates_record():
    async def _run():
        bot = Bot("TEST", request=AsyncMock())
        repo = DummyRepo()
        advance_requests._repo = repo
        context = types.SimpleNamespace(
            application=types.SimpleNamespace(chat_data={}), user_data={}
        )
        with (
            patch("telegram_stub.Message.reply_text", new=AsyncMock()),
            patch("telegram_stub.Bot.edit_message_text", new=AsyncMock()),
            patch(
                "app.handlers.user.payout.TelegramService.send_payout_request_to_admin",
                new=AsyncMock(),
            ),
            patch(
                "app.handlers.user.payout.load_users_map",
                return_value={
                    "1": {
                        "name": "Test",
                        "phone": "123",
                        "bank": "TB",
                        "card_number": "9999",
                    }
                },
            ),
            patch("app.handlers.user.payout.check_pending_request", return_value=False),
            patch("app.handlers.user.payout.load_advance_requests", return_value=[]),
        ):
            state = await payout.request_payout_start(
                _make_message(bot, "💰 Запросить выплату"), context
            )
            assert state == PayoutStates.SELECT_TYPE
            state = await payout.select_type(
                _make_message(bot, "Аванс", update_id=2), context
            )
            assert state == PayoutStates.ENTER_AMOUNT
            state = await payout.enter_amount(
                _make_message(bot, "1000", update_id=3), context
            )
            assert state == PayoutStates.SELECT_METHOD
            state = await payout.select_method(
                _make_message(bot, "💳 На карту", update_id=4), context
            )
            assert state == PayoutStates.CONFIRM_CARD
            state = await payout.confirm_card(
                _make_callback(bot, "payout_confirm", update_id=5), context
            )
            assert state == ConversationHandler.END
        assert len(repo.records) == 1

    asyncio.run(_run())
