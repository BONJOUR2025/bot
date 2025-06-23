from telegram import ReplyKeyboardMarkup
from typing import List


def get_admin_menu() -> ReplyKeyboardMarkup:
    keyboard: List[List[str]] = [
        ["📄 Просмотр данных", "📢 Рассылка"],
        ["💸 Просмотр выплат", "🔄 Сбросить запросы"],  # Новая кнопка
        ["🎂 Дни рождения"],
        ["📈 Отчёт по авансам"],
        ["📨 Сообщение пользователю", "➕ Создать запрос", "🏠 Домой"],
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


def get_confirmation_keyboard() -> ReplyKeyboardMarkup:
    """
    Возвращает клавиатуру для подтверждения выплаты.
    Клавиатура содержит кнопки "✅ Подтверждаю", "✏️ Изменить сумму" и "🏠 Домой".
    """
    keyboard: List[List[str]] = [
        ["✅ Подтверждаю", "✏️ Изменить сумму"],
        ["🏠 Домой"],
    ]
    return ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
