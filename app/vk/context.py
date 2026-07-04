"""Shared helpers for VK handlers.

Business-logic services (services/users.py, advance_requests.py, etc.) are
all keyed by employee.id — for a VK-only employee that's the "nb_..." stub
id created when their profile was set up in the admin, NOT their VK numeric
id. Every VK handler must resolve message.from_id -> employee.id via vk_id
before touching any shared repository, exactly the way Telegram handlers use
str(update.effective_user.id) directly (because for Telegram, id IS the
Telegram user id already)."""

from __future__ import annotations

from typing import Optional

from vkbottle import PhotoMessageUploader
from vkbottle.bot import Message

from app.core.types import Employee
from app.data.employee_repository import EmployeeRepository


def resolve_employee(vk_id: int | str) -> Optional[Employee]:
    return EmployeeRepository().get_by_vk_id(str(vk_id))


async def send_photo(message: Message, file_path: str, caption: str = "", keyboard=None) -> None:
    uploader = PhotoMessageUploader(message.ctx_api)
    attachment = await uploader.upload(file_path)
    await message.answer(
        caption,
        attachment=attachment,
        keyboard=keyboard.get_json() if keyboard is not None else None,
    )
