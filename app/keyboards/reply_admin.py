from typing import List

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes


def get_admin_menu() -> ReplyKeyboardMarkup:
    keyboard: List[List[str]] = [
        ["📄 Просмотр данных", "📢 Рассылка"],
        ["💸 Просмотр выплат", "🔄 Сбросить запросы"],
        ["📈 Отчёт по авансам"],
        ["📚 База знаний"],
        ["📨 Сообщение пользователю", "➕ Создать запрос", "🏠 Домой"],
        ["📝 Задача"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_month_keyboard() -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру для выбора месяца.
    Кнопки представлены с названиями месяцев и кнопкой возврата ("🏠 Домой").
    """
    keyboard: List[List[str]] = [
        ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ"],
        ["АПРЕЛЬ", "МАЙ", "ИЮНЬ"],
        ["ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ"],
        ["ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"],
        ["🏠 Домой"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_home_button() -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру, содержащую только кнопку "Домой".
    """
    keyboard: List[List[str]] = [["🏠 Домой"]]
    return ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )


async def send_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the main admin menu."""
    await update.message.reply_text("🏠 Главное меню", reply_markup=get_admin_menu())
