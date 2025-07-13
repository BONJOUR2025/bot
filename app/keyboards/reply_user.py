from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes
from typing import List


def get_main_menu() -> ReplyKeyboardMarkup:
    """
    Возвращает главное меню для обычного сотрудника.
    """
    keyboard: List[List[str]] = [
        ["📄 Просмотр ЗП"],
        ["💰 Запросить выплату"],
        ["📅 Просмотр расписания", "👤 Личный кабинет"],
    ]
    return ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )


def get_month_keyboard_user() -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру с названиями месяцев для выбора зарплаты.
    """
    months: List[List[str]] = [
        ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ"],
        ["АПРЕЛЬ", "МАЙ", "ИЮНЬ"],
        ["ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ"],
        ["ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"],
        ["🏠 Домой"],
    ]
    return ReplyKeyboardMarkup(
        months, resize_keyboard=True, one_time_keyboard=False
    )


def get_cabinet_menu() -> ReplyKeyboardMarkup:
    """
    Возвращает меню личного кабинета сотрудника.
    """
    keyboard: List[List[str]] = [
        ["📋 Мои данные", "✏️ Изменить данные"],
        ["💰 Запросить выплату", "📜 История запросов"],
        ["🏠 Домой"],
    ]
    return ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )


def get_edit_keyboard():
    keyboard = [["📱 Изменить телефон"], ["🏦 Изменить банк"], ["🏠 Домой"]]
    return ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )


async def send_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the main user menu."""
    await update.message.reply_text(
        "🏠 Вы вернулись в главное меню.", reply_markup=get_main_menu()
    )
