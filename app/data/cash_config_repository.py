from __future__ import annotations

import json
from pathlib import Path

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
        self._data = {"branches": DEFAULT_BRANCHES}
        self._save()

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Branches ─────────────────────────────────────────────────────
    def get_branches(self) -> dict[str, str]:
        return dict(self._data.get("branches", {}))

    def upsert_branch(self, bid: str, name: str) -> None:
        self._data.setdefault("branches", {})[bid.strip()] = name.strip()
        self._save()

    def delete_branch(self, bid: str) -> None:
        self._data.setdefault("branches", {}).pop(bid.strip(), None)
        self._save()

    def resolve_branch(self, bid) -> str:
        k = str(bid or "")
        return self._data.get("branches", {}).get(k, k or "—")


_repo: CashConfigRepository | None = None


def get_cash_config_repository() -> CashConfigRepository:
    global _repo
    if _repo is None:
        _repo = CashConfigRepository()
    return _repo
