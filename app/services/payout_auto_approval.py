"""Автоодобрение авансов.

Сотрудник просит аванс (Telegram-бот, VK-бот, кабинет, приложение мастера),
и если вместе с уже выданными с последней зарплаты авансами выходит не
больше лимита (по умолчанию 85 000 ₽), заявка одобряется сразу — ровно так
же, как кнопкой «✅ Разрешить»: статус «Одобрено», сообщение сотруднику,
реквизиты кассиру (payout_actions.approve_request). В группу «Запросы на
выплаты» уведомление уходит всё равно, но без кнопок и с пометкой
«одобрено автоматически, действий не требуется».

«С последней зарплаты» — то же, что вычитается при расчёте зарплаты:
авансы в статусах «Одобрено»/«Выплачено» после последней одобренной или
выплаченной «Зарплаты» (PayoutRepository.advances_since_last_salary).

Не автоодобряется: не «Аванс», не «Ожидает», неактивный сотрудник, лимит
выключен (0) — такие заявки идут на ручное решение, как раньше. Заявки,
которые админ создаёт сам в панели, сюда не попадают: это уже его решение.

Лимит — config.json, ключ payout_auto_approve_limit («Настройки → Общие»).
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 85000
ADVANCE_TYPE = "Аванс"
PENDING_STATUS = "Ожидает"


def limit() -> int:
    try:
        from app.services.config_service import ConfigService

        raw = ConfigService().load().get("payout_auto_approve_limit")
    except Exception:
        raw = None
    if raw is None or raw == "":
        return DEFAULT_LIMIT
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def _rub(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ") + " ₽"


def check(record: dict[str, Any]) -> dict[str, Any]:
    """Можно ли одобрить автоматически. {"ok", "reason", "since_total",
    "since", "limit"}; reason — почему нет (для пометки в уведомлении)."""
    cap = limit()
    info: dict[str, Any] = {"ok": False, "reason": "", "since_total": 0.0, "since": None, "limit": cap}
    if cap <= 0:
        info["reason"] = "автоодобрение выключено"
        return info
    if (record.get("payout_type") or "") != ADVANCE_TYPE:
        info["reason"] = "не аванс"
        return info
    if (record.get("status") or "") != PENDING_STATUS:
        info["reason"] = "заявка уже обработана"
        return info
    try:
        from app.data.employee_repository import EmployeeRepository

        emp = EmployeeRepository().get_employee(str(record.get("user_id")))
    except Exception:
        emp = None
    if emp is None or (getattr(emp, "status", "active") or "active") != "active":
        info["reason"] = "сотрудник не найден или неактивен"
        return info
    try:
        from app.data.payout_repository import PayoutRepository

        adv = PayoutRepository().advances_since_last_salary(str(record.get("user_id")))
    except Exception:
        log.warning("Автоодобрение: не удалось посчитать авансы с последней ЗП", exc_info=True)
        info["reason"] = "не удалось посчитать авансы с последней зарплаты"
        return info
    info["since_total"] = float(adv.get("total") or 0)
    info["since"] = adv.get("since")
    amount = float(record.get("amount") or 0)
    if info["since_total"] + amount > cap:
        info["reason"] = (f"сверх лимита автоодобрения: с последней ЗП уже {_rub(info['since_total'])}"
                          f" + {_rub(amount)} > {_rub(cap)}")
        return info
    info["ok"] = True
    return info


def _since_line(info: dict[str, Any], amount: float) -> str:
    since = info.get("since")
    when = f" (с {since[8:10]}.{since[5:7]})" if since and len(since) >= 10 else ""
    return (f"📊 Авансов с последней ЗП{when}: {_rub(info['since_total'] + amount)} "
            f"из {_rub(info['limit'])}, включая этот")


async def handle_new_request(telegram_service, record: dict[str, Any]) -> bool:
    """Новая заявка сотрудника: одобрить автоматически или отправить на
    решение с кнопками. True — одобрена автоматически."""
    from app.handlers.admin.payout_actions import approve_request

    info = check(record)
    bot = getattr(telegram_service, "bot", None)
    if not info["ok"] or bot is None:
        extra = ""
        if record.get("payout_type") == ADVANCE_TYPE and info["reason"].startswith("сверх"):
            extra = f"⚠️ Не одобрено автоматически — {info['reason']}"
        await telegram_service.send_payout_request_to_admin(record, extra=extra)
        return False

    result = await approve_request(bot, record, how=" (автоматически, в пределах лимита)")
    if not result["updated"]:
        # Кто-то успел обработать заявку раньше — отправляем как обычно,
        # пусть решают глазами.
        await telegram_service.send_payout_request_to_admin(record)
        return False
    log.info("Аванс %s (%s, %s ₽) одобрен автоматически", record.get("id"), record.get("name"), record.get("amount"))
    lines = [_since_line(info, float(record.get("amount") or 0))]
    if result["cashier_line"]:
        lines.append(result["cashier_line"])
    await telegram_service.send_payout_auto_approved_to_admin(record, "\n".join(lines))
    return True
