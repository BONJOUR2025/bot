"""Способы выплат и какие из них разрешены конкретному сотруднику.

В карточке сотрудника можно закрепить способы (поле payout_methods) —
например, только «🤝 Наличными». Тогда Telegram-бот, VK-бот и кабинет
показывают ему только их, а API не примет заявку другим способом.
Пустой список — можно любым, как раньше.
"""
from __future__ import annotations

from typing import Any, Iterable

ALL_METHODS = ["💳 На карту", "🏦 Из кассы", "🤝 Наличными"]


def normalize(methods: Iterable[Any] | None) -> list[str]:
    """Только известные способы, в обычном порядке, без повторов."""
    chosen = {str(m).strip() for m in (methods or [])}
    return [m for m in ALL_METHODS if m in chosen]


def allowed_for(employee: Any) -> list[str]:
    """Способы, которыми можно выплачивать этому сотруднику."""
    raw = getattr(employee, "payout_methods", None) if employee is not None else None
    if isinstance(employee, dict):
        raw = employee.get("payout_methods")
    return normalize(raw) or list(ALL_METHODS)


def allowed_for_id(employee_id: Any) -> list[str]:
    try:
        from app.data.employee_repository import EmployeeRepository

        return allowed_for(EmployeeRepository().get_employee(str(employee_id)))
    except Exception:
        return list(ALL_METHODS)


def describe(methods: list[str]) -> str:
    """«только наличными» / «на карту или наличными» — для сообщений."""
    words = [m.split(" ", 1)[1].lower() if " " in m else m for m in methods]
    if len(words) == 1:
        return f"только {words[0]}"
    return ", ".join(words[:-1]) + f" или {words[-1]}"
