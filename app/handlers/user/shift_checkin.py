from __future__ import annotations

from datetime import date
from pathlib import Path

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from ...constants import ShiftCheckinStates
from ...keyboards.reply_user import get_main_menu
from ...services.shift_checkin_service import get_shift_checkin_service
from ...services.users import load_users_map
from ...services.work_hours import MOSCOW_TZ
from ...utils.logger import log

MEDIA_DIR = Path(__file__).parent.parent.parent.parent / "media_archive" / "shift_checkins"

HOME_KEYBOARD = ReplyKeyboardMarkup([["🏠 Домой"]], resize_keyboard=True)


async def open_salon_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the "🏪 Открыть салон" button."""
    user_id = str(update.effective_user.id)
    user = load_users_map().get(user_id)
    if not user:
        await update.message.reply_text(
            "❌ Ваши данные не найдены. Обратитесь к администратору.",
            reply_markup=get_main_menu(user_id),
        )
        return ConversationHandler.END

    employee_name = user.get("full_name") or user.get("name") or ""
    service = get_shift_checkin_service()
    point = await service.find_point_for_employee(employee_name, date.today())

    if point:
        context.user_data["open_salon_point"] = point.model_dump()
        text = f"📸 Отправьте фото чека об открытии точки «{point.point}»."
    else:
        context.user_data["open_salon_point"] = None
        text = (
            "⚠️ По графику на сегодня вы не назначены ни в одну точку.\n"
            "Отправьте фото чека об открытии — запись сохранится без расчёта штрафа."
        )

    await update.message.reply_text(text, reply_markup=HOME_KEYBOARD)
    return ShiftCheckinStates.AWAITING_PHOTO


async def open_salon_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the opening-shift receipt photo and record the check-in."""
    message = update.message
    if not message.photo:
        await message.reply_text("❌ Пожалуйста, отправьте фото чека.")
        return ShiftCheckinStates.AWAITING_PHOTO

    user_id = str(update.effective_user.id)
    user = load_users_map().get(user_id)
    if not user:
        await message.reply_text(
            "❌ Ваши данные не найдены. Обратитесь к администратору.",
            reply_markup=get_main_menu(user_id),
        )
        context.user_data.pop("open_salon_point", None)
        return ConversationHandler.END

    sent_at = message.date.astimezone(MOSCOW_TZ)

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{sent_at.strftime('%Y%m%d_%H%M%S')}_{user_id}.jpg"
    filepath = MEDIA_DIR / filename
    try:
        tg_file = await message.photo[-1].get_file()
        await tg_file.download_to_drive(filepath)
    except Exception as e:
        log(f"⚠️ [shift_checkin] Failed to save photo: {e}")
        await message.reply_text("❌ Не удалось сохранить фото, попробуйте ещё раз.")
        return ShiftCheckinStates.AWAITING_PHOTO

    employee_name = user.get("full_name") or user.get("name") or ""
    service = get_shift_checkin_service()
    record = await service.record_checkin(
        employee_id=user_id,
        employee_name=employee_name,
        photo_path=f"shift_checkins/{filename}",
        sent_at=sent_at,
    )

    reply = f"✅ Открытие зафиксировано: {sent_at.strftime('%H:%M')}"
    if record.get("salon_name"):
        reply += f"\nТочка: {record['salon_name']}"
    if record.get("penalty_amount"):
        reply += (
            f"\n⚠️ Опоздание {record['delay_minutes']} мин "
            f"(открытие в {record['expected_open_time']}) — штраф {record['penalty_amount']:.0f} ₽"
        )
    elif record.get("no_schedule"):
        reply += "\nℹ️ Точка по графику не определена, штраф не рассчитан."

    await message.reply_text(reply, reply_markup=get_main_menu(user_id))
    context.user_data.pop("open_salon_point", None)
    return ConversationHandler.END


async def open_salon_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)
    context.user_data.pop("open_salon_point", None)
    await update.message.reply_text("🏠 Вы вернулись в главное меню.", reply_markup=get_main_menu(user_id))
    return ConversationHandler.END
