"""VK reply keyboards — mirrors app/keyboards/reply_user.py. VK has no
separate "inline keyboard + callback_query" concept as convenient as
Telegram's for a from-memory, untested port, so confirmation steps that are
inline buttons in Telegram (payout confirm/cancel, profile-edit confirm) are
plain reply-keyboard text buttons here instead — simpler and more robust
without a live VK bot to test against."""

from __future__ import annotations

from vkbottle import Keyboard, Text

from app.services.access_control_service import get_access_control_service

HOME_LABEL = "🏠 Домой"


def _from_rows(rows: list[list[str]]) -> Keyboard:
    kb = Keyboard(one_time=False, inline=False)
    for i, row in enumerate(rows):
        if i:
            kb.row()
        for label in row:
            kb.add(Text(label))
    return kb


def main_menu(employee_id: str | None) -> Keyboard:
    texts = get_access_control_service().get_bot_button_texts(employee_id)
    # one button per row keeps VK's keyboard legible regardless of label length
    return _from_rows([[t] for t in texts])


def month_keyboard() -> Keyboard:
    return _from_rows([
        ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ"],
        ["АПРЕЛЬ", "МАЙ", "ИЮНЬ"],
        ["ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ"],
        ["ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"],
        [HOME_LABEL],
    ])


def cabinet_menu() -> Keyboard:
    return _from_rows([
        ["📋 Мои данные", "✏️ Изменить данные"],
        ["💰 Запросить выплату", "📜 История запросов"],
        [HOME_LABEL],
    ])


def edit_menu() -> Keyboard:
    return _from_rows([["📱 Изменить телефон"], ["🏦 Изменить банк"], [HOME_LABEL]])


def confirm_menu() -> Keyboard:
    return _from_rows([["✅ Подтвердить", "❌ Отменить"]])


def payout_type_menu() -> Keyboard:
    return _from_rows([["Аванс", "Зарплата"], [HOME_LABEL]])


def payout_method_menu() -> Keyboard:
    return _from_rows([["💳 На карту", "🏦 Из кассы", "🤝 Наличными"], [HOME_LABEL]])


def home_only_menu() -> Keyboard:
    return _from_rows([[HOME_LABEL]])
