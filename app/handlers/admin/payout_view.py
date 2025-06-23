# -*- coding: utf-8 -*-
"""Handlers for viewing payouts in admin mode."""

import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from ...constants import UserStates
from ...core.constants import MONTHS_RU, PAYOUT_TYPES
from ...config import ADMIN_ID
from ...keyboards.reply_admin import get_admin_menu
from ...services.advance_requests import load_advance_requests

__all__ = [
    "view_payouts",
    "select_payout_type",
    "select_period",
    "select_status",
    "select_employee_filter",
    "select_sort",
    "handle_pagination",
    "cancel_payouts",
    "show_employee_keyboard",
    "show_payouts_page",
]


async def view_payouts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало сценария просмотра выплат."""
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    keyboard = [
        PAYOUT_TYPES,
        ["Все типы"],
        ["🏠 Домой"],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "📊 Выберите тип выплаты для фильтрации:", reply_markup=reply_markup
    )
    return UserStates.SELECT_PAYOUT_TYPE


async def select_payout_type(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    payout_type = update.message.text.strip()
    if payout_type == "🏠 Домой":
        await update.message.reply_text(
            "🏠 Вы вернулись в меню администратора.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    if payout_type not in PAYOUT_TYPES + ["Все типы"]:
        await update.message.reply_text(
            "❌ Выберите корректный тип из предложенных."
        )
        return UserStates.SELECT_PAYOUT_TYPE

    context.user_data["payout_type_filter"] = (
        payout_type if payout_type != "Все типы" else None
    )

    keyboard = [[month]
                for month in MONTHS_RU] + [["Все периоды"], ["🏠 Домой"]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "📅 Выберите период (месяц) для фильтрации:", reply_markup=reply_markup
    )
    return UserStates.SELECT_PERIOD


async def select_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    period = update.message.text.strip()
    if period == "🏠 Домой":
        await update.message.reply_text(
            "🏠 Вы вернулись в меню администратора.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    months = {name: f"{i:02d}" for i, name in enumerate(MONTHS_RU, start=1)}
    if period not in months and period != "Все периоды":
        await update.message.reply_text(
            "❌ Выберите корректный месяц из предложенных."
        )
        return UserStates.SELECT_PERIOD

    current_year = datetime.datetime.now().year
    period_filter = (
        f"{current_year}-{months[period]}" if period != "Все периоды" else None
    )
    context.user_data["period_filter"] = period_filter

    keyboard = [
        ["Ожидает", "Одобрено"],
        ["Отклонено", "Отменено"],
        ["Все статусы"],
        ["🏠 Домой"],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "🔍 Выберите статус выплат для фильтрации:", reply_markup=reply_markup
    )
    return UserStates.SELECT_STATUS


async def select_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = update.message.text.strip()
    if status == "🏠 Домой":
        await update.message.reply_text(
            "🏠 Вы вернулись в меню администратора.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    status_map = {
        "Ожидает": "Ожидает",
        "Одобрено": "Одобрено",
        "Отклонено": "Отклонено",
        "Отменено": "Отменено",
    }
    if status not in status_map and status != "Все статусы":
        await update.message.reply_text(
            "❌ Выберите корректный статус из предложенных."
        )
        return UserStates.SELECT_STATUS

    context.user_data["status_filter"] = (
        status_map[status] if status != "Все статусы" else None
    )
    return await show_employee_keyboard(update, context)


async def show_employee_keyboard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    from ...services.users import load_users

    users = load_users()
    employees = sorted(
        {u.get("name", "").strip() for u in users.values() if u.get("name")}
    )
    if not employees:
        await update.message.reply_text("❌ Список сотрудников пуст.")
        return UserStates.SELECT_EMPLOYEE_FILTER

    keyboard = [[emp] for emp in employees] + [["Все сотрудники"]]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "Выберите сотрудника для фильтрации:", reply_markup=reply_markup
    )
    return UserStates.SELECT_EMPLOYEE_FILTER


async def select_employee_filter(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    from ...services.users import load_users

    users = load_users()
    employees = {
        u.get("name", "").strip() for u in users.values() if u.get("name")
    }

    selected = update.message.text.strip()
    if selected not in employees and selected != "Все сотрудники":
        await update.message.reply_text(
            "❌ Неверный выбор. Пожалуйста, выберите имя из списка."
        )
        return UserStates.SELECT_EMPLOYEE_FILTER

    context.user_data["employee_filter"] = selected
    context.user_data["page"] = 0

    keyboard = [
        ["По дате (новые сверху)", "По дате (старые сверху)"],
        ["По сумме (убывание)", "По сумме (возрастание)"],
        ["🏠 Домой"],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(
        "📈 Выберите сортировку выплат:", reply_markup=reply_markup
    )
    return UserStates.SELECT_SORT


async def select_sort(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sort_option = update.message.text.strip()
    if sort_option == "🏠 Домой":
        await update.message.reply_text(
            "🏠 Вы вернулись в меню администратора.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    sort_map = {
        "По дате (новые сверху)": ("timestamp", True),
        "По дате (старые сверху)": ("timestamp", False),
        "По сумме (убывание)": ("amount", True),
        "По сумме (возрастание)": ("amount", False),
    }
    if sort_option not in sort_map:
        await update.message.reply_text(
            "❌ Выберите корректный вариант сортировки."
        )
        return UserStates.SELECT_SORT

    sort_key, reverse = sort_map[sort_option]
    context.user_data["sort_key"] = sort_key
    context.user_data["sort_reverse"] = reverse

    requests = load_advance_requests()
    payout_type_filter = context.user_data.get("payout_type_filter")
    period_filter = context.user_data.get("period_filter")
    status_filter = context.user_data.get("status_filter")

    filtered_requests = [
        req
        for req in requests
        if (
            payout_type_filter is None
            or req.get("payout_type") == payout_type_filter
        )
        and (
            period_filter is None or req["timestamp"].startswith(period_filter)
        )
        and (status_filter is None or req.get("status") == status_filter)
    ]

    if not filtered_requests:
        await update.message.reply_text(
            "📊 Нет выплат, соответствующих выбранным фильтрам.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    filtered_requests.sort(
        key=lambda x: x.get(sort_key, 0 if sort_key == "amount" else ""),
        reverse=reverse,
    )
    context.user_data["filtered_requests"] = filtered_requests
    context.user_data["page"] = 0
    return await show_payouts_page(update, context)


async def show_payouts_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    filtered_requests = context.user_data.get("filtered_requests", [])
    employee_filter = context.user_data.get("employee_filter")
    if employee_filter and employee_filter != "Все сотрудники":
        filtered_requests = [
            req
            for req in filtered_requests
            if req.get("name") == employee_filter
        ]

    if not filtered_requests:
        await update.message.reply_text(
            "📭 Нет выплат по выбранным фильтрам.",
            reply_markup=get_admin_menu(),
        )
        return ConversationHandler.END

    items_per_page = 5
    total_pages = (
        len(filtered_requests) + items_per_page - 1
    ) // items_per_page
    page = max(0, min(context.user_data.get("page", 0), total_pages - 1))
    context.user_data["page"] = page

    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_requests))
    page_requests = filtered_requests[start_idx:end_idx]

    from ...services.users import load_users

    users = load_users()

    lines = []
    for req in page_requests:
        uid = req.get("user_id", "Неизвестно")
        uname = users.get(uid, {}).get("name", "Неизвестно")
        lines.append(
            "\n".join(
                [
                    f"👤 {uname}",
                    f"Тип: {req.get('payout_type', 'Не указано')}",
                    f"Сумма: {req.get('amount', 'Не указано')} ₽",
                    f"Метод: {req.get('method', 'Не указано')}",
                    f"Статус: {req.get('status', 'Не указано')}",
                    f"Дата: {req.get('timestamp', 'Не указана')}",
                ]
            )
        )

    result_text = (
        f"📊 Список выплат (страница {page + 1} из {total_pages}):\n\n"
        + "\n\n".join(lines)
    )

    keyboard = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append("⬅️ Назад")
    if page < total_pages - 1:
        nav_buttons.append("➡️ Далее")
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append(["🏠 Домой"])
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=True
    )
    await update.message.reply_text(result_text, reply_markup=reply_markup)
    return UserStates.SHOW_PAYOUTS


async def handle_pagination(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    action = update.message.text.strip()
    if action == "🏠 Домой":
        await update.message.reply_text(
            "🏠 Вы вернулись в меню администратора.",
            reply_markup=get_admin_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END
    if action == "⬅️ Назад":
        context.user_data["page"] = max(
            0, context.user_data.get("page", 0) - 1
        )
    elif action == "➡️ Далее":
        context.user_data["page"] = context.user_data.get("page", 0) + 1
    else:
        await update.message.reply_text(
            "❌ Выберите действие из предложенных."
        )
        return UserStates.SHOW_PAYOUTS
    return await show_payouts_page(update, context)


async def cancel_payouts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏠 Вы вернулись в меню администратора.", reply_markup=get_admin_menu()
    )
    context.user_data.clear()
    return ConversationHandler.END
