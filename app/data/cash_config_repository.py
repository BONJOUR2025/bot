from __future__ import annotations

import json
from pathlib import Path

DEFAULT_USERS: dict[str, str] = {
    "110275": "Вера 0102",
    "110171": "Анастасия 2602",
    "110158": "Арина 7272",
    "110273": "Александр 1505",
    "110221": "Эмиль 2404",
    "111111": "Полина 5984",
    "110276": "Наталья 0704",
    "1136": "Катя 2201",
    "110146": "Лали 1606",
    "110145": "Екатерина 0104",
    "110265": "Ирина 2006",
    "110255": "Полина 1802",
    "110150": "Вероника 1996",
    "1134": "Ира 2405",
    "110287": "Юля 3007",
    "110222": "Алекс 2104",
    "109110": "Марина 0208",
}

DEFAULT_BRANCHES: dict[str, str] = {
    "17": "Охта-Молл",
    "11": "Меркурий",
    "7": "Пассаж",
    "5": "Academ Park",
    "3": "Озерки",
    "8": "Бестужевская",
}


class CashConfigRepository:
    def __init__(self, path: str = "cash_config.json") -> None:
        self._path = Path(path)
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                return
            except Exception:
                pass
        self._data = {"users": DEFAULT_USERS, "branches": DEFAULT_BRANCHES}
        self._save()

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Users ────────────────────────────────────────────────────────
    def get_users(self) -> dict[str, str]:
        return dict(self._data.get("users", {}))

    def upsert_user(self, uid: str, name: str) -> None:
        self._data.setdefault("users", {})[uid.strip()] = name.strip()
        self._save()

    def delete_user(self, uid: str) -> None:
        self._data.setdefault("users", {}).pop(uid.strip(), None)
        self._save()

    # ── Branches ─────────────────────────────────────────────────────
    def get_branches(self) -> dict[str, str]:
        return dict(self._data.get("branches", {}))

    def upsert_branch(self, bid: str, name: str) -> None:
        self._data.setdefault("branches", {})[bid.strip()] = name.strip()
        self._save()

    def delete_branch(self, bid: str) -> None:
        self._data.setdefault("branches", {}).pop(bid.strip(), None)
        self._save()

    def resolve_user(self, uid) -> str:
        k = str(uid or "")
        return self._data.get("users", {}).get(k, k or "—")

    def resolve_branch(self, bid) -> str:
        k = str(bid or "")
        return self._data.get("branches", {}).get(k, k or "—")


_repo: CashConfigRepository | None = None


def get_cash_config_repository() -> CashConfigRepository:
    global _repo
    if _repo is None:
        _repo = CashConfigRepository()
    return _repo
