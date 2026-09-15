"""Раздел мастера в боте: заработок, незакрытые работы, потолок аванса.

Раздел показывается по должности из карточки сотрудника (см.
master_bot_service.MASTER_POSITIONS), а данные тянутся из общего прогретого
кэша — см. модуль сервиса, там же объяснено, почему именно так.
"""
from __future__ import annotations

from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...keyboards.reply_user import get_main_menu
from ...services.master_bot_service import (
    PERIOD_MONTH,
    PERIOD_PREV_MONTH,
    get_earnings,
    get_wip,
    resolve_master,
)
from ...utils.logger import log

MONTHS_NOM = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

NOT_A_MASTER = (
    "❌ Этот раздел доступен только мастерам.\n"
    "Если вы мастер и видите это сообщение — значит в вашей карточке не "
    "проставлен код Агбис. Обратитесь к руководителю."
)

DISCLAIMER = "ℹ️ Показатели предварительные, уточните у руководителя."


def money(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def _month_title(d: date) -> str:
    return f"{MONTHS_NOM[d.month - 1]} {d.year}"


async def _load(fn, *args):
    """Вызов блокирующего сервиса в потоке, с границей по времени."""
    from ...services.firebird_service import run_with_timeout

    return await run_with_timeout(fn, *args, timeout=55)


def _period_keyboard(current: str) -> InlineKeyboardMarkup:
    options = [(PERIOD_MONTH, "Текущий месяц"), (PERIOD_PREV_MONTH, "Прошлый месяц")]
    row = [
        InlineKeyboardButton(
            ("• " if key == current else "") + label, callback_data=f"master_earn:{key}"
        )
        for key, label in options
    ]
    return InlineKeyboardMarkup([row])


def format_earnings(master, report: dict) -> str:
    title = _month_title(report["date_from"])
    lines: list[str] = []

    if report["is_apprentice"]:
        lines.append(f"🎓 <b>Мой отчёт — {title}</b>")
        lines.append("")
        lines.append("<b>К выплате — стипендия</b>")
        lines.append(
            f"Дней обучения: {report['stipend_days']} × {money(report['day_rate'])}"
            f" = <b>{money(report['stipend'])}</b>"
        )
        lines.append("")
        lines.append("<i>Справочно — если бы работал на проценте:</i>")
        lines.append(
            f"услуг {report['services_count']}, "
            f"на сумму {money(report['kredit'])} → {money(report['accrued'])}"
        )
    else:
        lines.append(f"🔧 <b>Мой заработок — {title}</b>")
        lines.append("")
        lines.append(f"Начислено: <b>{money(report['accrued'])}</b>")
        lines.append(
            f"Услуг: {report['services_count']} · "
            f"сумма работ {money(report['kredit'])}"
        )

    if report["groups"]:
        lines.append("")
        lines.append("<b>По видам работ:</b>")
        for row in report["groups"][:8]:
            lines.append(
                f"  {row['group']} — {int(row['count'])} шт, {money(row['salary'])}"
            )

    lines.append("")
    if report["advances"]:
        lines.append(f"Авансы с последней ЗП: −{money(report['advances'])}")
    # Минус на экране у человека читается как долг и пугает, хотя означает
    # всего лишь «аванс уже перекрыл начисленное». Пояснений под итогом нет —
    # руководитель попросил оставить одну сноску, как в кабинете.
    lines.append(f"<b>К выплате сейчас: {money(max(0.0, report['to_pay']))}</b>")

    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_wip(rows: list[dict]) -> str:
    if not rows:
        return "🧰 <b>Что на мне висит</b>\n\nНезакрытых работ нет — всё сдано. 👍"

    total = sum(r["kredit"] for r in rows)
    lines = [f"🧰 <b>Что на мне висит — {len(rows)} шт</b>", ""]
    for row in rows[:30]:
        mark = "🔴" if row["urgent"] else "•"
        days = f" · {row['days']} дн" if row["days"] is not None else ""
        lines.append(f"{mark} <b>{row['doc_num']}</b>{days}")
        lines.append(f"    {str(row['name'])[:48]} — {money(row['kredit'])}")
    if len(rows) > 30:
        lines.append(f"\n…и ещё {len(rows) - 30}")
    lines.append("")
    lines.append(f"Итого в работе: {money(total)}")
    lines.append("")
    lines.append("🔴 — срочный заказ")
    return "\n".join(lines)


async def master_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка «Мой заработок»."""
    user_id = str(update.effective_user.id)
    master = resolve_master(user_id)
    if master is None:
        await update.message.reply_text(NOT_A_MASTER, reply_markup=get_main_menu(user_id))
        return

    loading = await update.message.reply_text("⏳ Считаю…")
    try:
        report = await _load(get_earnings, master, PERIOD_MONTH)
    except Exception as exc:
        log(f"❌ [master_earnings] {master.employee_id}: {exc}")
        await loading.edit_text(
            "❌ Не получилось загрузить данные, попробуйте через пару минут."
        )
        return

    await loading.edit_text(
        format_earnings(master, report),
        parse_mode="HTML",
        reply_markup=_period_keyboard(PERIOD_MONTH),
    )


async def master_earnings_period(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переключение периода под сообщением с заработком."""
    query = update.callback_query
    await query.answer()
    period = (query.data or "").split(":", 1)[-1]
    if period not in (PERIOD_MONTH, PERIOD_PREV_MONTH):
        return

    user_id = str(update.effective_user.id)
    master = resolve_master(user_id)
    if master is None:
        await query.edit_message_text(NOT_A_MASTER)
        return

    try:
        report = await _load(get_earnings, master, period)
    except Exception as exc:
        log(f"❌ [master_earnings_period] {master.employee_id}: {exc}")
        await query.answer("Не удалось загрузить, попробуйте позже", show_alert=True)
        return

    text = format_earnings(master, report)
    if text.strip() == (query.message.text_html or "").strip():
        return
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=_period_keyboard(period)
    )


async def master_wip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка «Что на мне висит»."""
    user_id = str(update.effective_user.id)
    master = resolve_master(user_id)
    if master is None:
        await update.message.reply_text(NOT_A_MASTER, reply_markup=get_main_menu(user_id))
        return

    loading = await update.message.reply_text("⏳ Смотрю незакрытые работы…")
    try:
        rows = await _load(get_wip, master)
    except Exception as exc:
        log(f"❌ [master_wip] {master.employee_id}: {exc}")
        await loading.edit_text(
            "❌ Не получилось загрузить данные, попробуйте через пару минут."
        )
        return

    await loading.edit_text(format_wip(rows), parse_mode="HTML")
