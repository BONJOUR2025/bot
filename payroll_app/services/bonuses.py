import json
import re
from datetime import datetime

CODE_RE = re.compile(r"(\d{4})$")

def _code(name: str) -> str | None:
    m = CODE_RE.search((name or "").strip())
    return m.group(1) if m else None

def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)

def bonuses_penalties_for_month(json_path: str, year: int, month: int) -> tuple[dict[str, float], dict[str, float]]:
    data = json.loads(open(json_path, "r", encoding="utf-8").read())

    bonuses: dict[str, float] = {}
    penalties: dict[str, float] = {}

    for r in data:
        code = _code(r.get("name"))
        if not code:
            continue
        dt = _parse_dt(r.get("date"))
        if dt.year != year or dt.month != month:
            continue

        amt = float(r.get("amount") or 0)
        if r.get("type") == "bonus":
            bonuses[code] = bonuses.get(code, 0.0) + amt
        elif r.get("type") == "penalty":
            penalties[code] = penalties.get(code, 0.0) + amt

    return bonuses, penalties
