"""Open salon (shift check-in via receipt photo) — VK port of
app/handlers/user/shift_checkin.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from vkbottle.bot import Bot, Message

from app.services.shift_checkin_service import get_shift_checkin_service
from app.services.work_hours import MOSCOW_TZ
from app.utils.logger import log
from ..keyboards import home_only_menu, main_menu
from ..states import ShiftCheckinStates

MEDIA_DIR = Path(__file__).parent.parent.parent.parent / "media_archive" / "shift_checkins"


async def start_open_salon(bot: Bot, message: Message, employee_id: str) -> None:
    service = get_shift_checkin_service()
    point = await service.find_point_for_employee_id(employee_id, date.today())
    text = (
        f"📸 Отправьте фото чека об открытии точки «{point.point}»."
        if point
        else (
            "⚠️ По графику на сегодня вы не назначены ни в одну точку.\n"
            "Отправьте фото чека об открытии — запись сохранится без расчёта штрафа."
        )
    )
    await bot.state_dispenser.set(message.peer_id, ShiftCheckinStates.AWAITING_PHOTO)
    await message.answer(text, keyboard=home_only_menu().get_json())


async def handle_photo(bot: Bot, message: Message, employee_id: str, employee_name: str) -> None:
    photos = message.get_photo_attachments() or []
    if not photos:
        await message.answer("❌ Пожалуйста, отправьте фото чека.")
        return

    sent_at = datetime_now_moscow()
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{sent_at.strftime('%Y%m%d_%H%M%S')}_vk{employee_id}.jpg"
    filepath = MEDIA_DIR / filename

    # VK photo objects list all resolutions under .sizes — take the largest.
    photo = photos[0]
    best_size = max(photo.sizes, key=lambda s: (s.width or 0) * (s.height or 0)) if photo.sizes else None
    url = best_size.url if best_size else None
    if not url:
        log("⚠️ [vk/shift_checkin] Не удалось определить URL фото")
        await message.answer("❌ Не удалось сохранить фото, попробуйте ещё раз.")
        return

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
    except Exception as e:
        log(f"⚠️ [vk/shift_checkin] Failed to save photo: {e}")
        await message.answer("❌ Не удалось сохранить фото, попробуйте ещё раз.")
        return

    await bot.state_dispenser.delete(message.peer_id)
    service = get_shift_checkin_service()
    record = await service.record_checkin(
        employee_id=employee_id,
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

    await message.answer(reply, keyboard=main_menu(employee_id).get_json())


def datetime_now_moscow():
    from datetime import datetime
    return datetime.now(MOSCOW_TZ)
