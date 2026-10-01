"""Незнакомцу бот не показывает меню — только «Ожидайте привязку»."""
import asyncio
from types import SimpleNamespace

from telegram import ReplyKeyboardRemove

from app.handlers.user import home


class _Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, reply_markup=None):
        self.sent.append((text, reply_markup))


def _update(uid):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=_Msg(),
                           effective_chat=SimpleNamespace(id=uid))


def test_unknown_user_gets_waiting_text_without_keyboard(monkeypatch):
    monkeypatch.setattr(home, "load_users_map", lambda: {})
    upd = _update(777)
    asyncio.run(home.get_user_info_user(upd, SimpleNamespace()))
    text, markup = upd.message.sent[0]
    assert "Ожидайте привязку" in text
    assert isinstance(markup, ReplyKeyboardRemove)


def test_known_user_still_gets_menu(monkeypatch):
    monkeypatch.setattr(home, "load_users_map", lambda: {"777": {"name": "Иван"}})
    monkeypatch.setattr(home, "get_main_menu", lambda uid: "MENU")
    upd = _update(777)
    asyncio.run(home.get_user_info_user(upd, SimpleNamespace()))
    assert upd.message.sent == [("Приветствую тебя, Иван!\n\nВыберите действие:", "MENU")]
