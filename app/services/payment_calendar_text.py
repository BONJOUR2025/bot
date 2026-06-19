def build_invoice_text(schedule: dict) -> str:
    """Render the cashier-facing invoice message for a payment schedule.

    Shared between the initial send and the "Оплачено" edit so the edit can
    rebuild the exact original markdown source instead of reusing
    query.message.text/caption (Telegram strips markdown syntax from those,
    so re-parsing them with parse_mode would lose the original formatting).
    """

    def esc(v) -> str:
        return str(v or "—").replace("`", "'")

    amount = f"{schedule['planned_amount']:,.2f}".replace(",", " ").replace(".", ",")
    objects = schedule.get("objects") or []
    objects_line = f"Объекты      : {esc(', '.join(objects))}\n" if objects else ""
    return (
        "📋 *Просьба оплатить счёт*\n\n"
        "```\n"
        f"Товар/Услуга : {esc(schedule['name'])}\n"
        f"Продавец     : {esc(schedule.get('seller'))}\n"
        f"Сумма        : {amount} ₽\n"
        f"Платим от    : {esc(schedule.get('pay_from'))}\n"
        f"{objects_line}"
        "```"
    )
