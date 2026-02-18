import json
import re
from datetime import datetime

CODE_RE = re.compile(r"(\d{4})$")


def _code(name: str) -> str | None:
    m = CODE_RE.search((name or "").strip())
    return m.group(1) if m else None


def _parse_dt(v) -> datetime:
    """
    Живучий парсер даты.

    Поддерживает:
    - ISO строку: "2026-02-10T12:34:56" (в т.ч. с Z на конце)
    - "2026-02-10 12:34:56"
    - timestamp (int/float) в секундах или миллисекундах
    - None -> 1970-01-01
    """
    if isinstance(v, datetime):
        return v

    if v is None:
        return datetime(1970, 1, 1)

    if isinstance(v, (int, float)):
        ts = float(v)
        # если число слишком большое — почти наверняка миллисекунды
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts)

    if isinstance(v, str):
        s = v.strip()
        if not s:
            return datetime(1970, 1, 1)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            try:
                return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return datetime(1970, 1, 1)

    return datetime(1970, 1, 1)


def _dt_field(r: dict):
    # Подстрой под твой JSON, если поля называются иначе
    return (
        r.get("date")
        or r.get("created_at")
        or r.get("createdAt")
        or r.get("timestamp")
        or r.get("created")
    )


def advances_for_month(json_path: str, year: int, month: int) -> dict[str, float]:
    """
    Правило:
    - Находим последнюю запись payout_type == "Зарплата"
    - Суммируем payout_type == "Аванс" ПОСЛЕ неё, но только в месяце расчёта

    Важно:
    - Имя сотрудника определяется по последним 4 цифрам в поле "name" (например, "Юля 1234")
    - Дата в JSON может быть разных типов (строка/число/None) — обрабатываем безопасно.
    """
    data = json.loads(open(json_path, "r", encoding="utf-8").read())

    # сгруппировать операции по сотруднику
    ops: dict[str, list[dict]] = {}
    for row in data:
        code = _code(row.get("name"))
        if not code:
            continue
        ops.setdefault(code, []).append(row)

    out: dict[str, float] = {}

    for code, items in ops.items():
        # сортируем по дате операции
        items_sorted = sorted(items, key=lambda r: _parse_dt(_dt_field(r)))

        # находим последнюю "Зарплата"
        last_salary_dt: datetime | None = None
        for r in items_sorted:
            if r.get("payout_type") == "Зарплата":
                last_salary_dt = _parse_dt(_dt_field(r))

        if not last_salary_dt:
            out[code] = 0.0
            continue

        # суммируем авансы после последней зарплаты в целевом месяце
        s = 0.0
        for r in items_sorted:
            if r.get("payout_type") != "Аванс":
                continue

            dt = _parse_dt(_dt_field(r))
            if dt <= last_salary_dt:
                continue

            if dt.year == year and dt.month == month:
                s += float(r.get("amount") or 0)

        out[code] = s

    return out
