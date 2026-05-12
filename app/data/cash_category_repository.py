from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.settings import settings

DEFAULT_CATEGORIES = [
    {"name": "ЗАРПЛАТА",    "prefixes": ["ЗАРПЛАТА_", "ЗП_"]},
    {"name": "ЛОГИСТИКА",   "prefixes": ["ЛОГИСТИКА"]},
    {"name": "МАТЕРИАЛЫ",   "prefixes": ["МАТЕРИАЛЫ_"]},
    {"name": "УБОРКА",      "prefixes": ["УБОРКА_"]},
    {"name": "ЧАЙ",         "prefixes": ["ЧАЙ_"]},
    {"name": "АПТЕЧКА",     "prefixes": ["АПТЕЧКА_"]},
    {"name": "ВОЗВРАТ",     "prefixes": ["ВОЗВРАТ_"]},
    {"name": "КАНЦТОВАРЫ",  "prefixes": ["КАНЦТОВАРЫ_"]},
    {"name": "УПАКОВКА",    "prefixes": ["УПАКОВКА_"]},
    {"name": "ИНКАССАЦИЯ",  "prefixes": ["ИНКАССАЦИЯ_"]},
]


class CashCategoryRepository:
    def __init__(self) -> None:
        self._path = Path(settings.cash_categories_file)
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                return
            except Exception:
                pass
        self._data = {"categories": DEFAULT_CATEGORIES, "assignments": {}}
        self._save()

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Categories ──────────────────────────────────────────────────

    def list_categories(self) -> list[dict]:
        return self._data.get("categories", [])

    def get_category(self, name: str) -> Optional[dict]:
        return next((c for c in self.list_categories() if c["name"] == name), None)

    def create_category(self, name: str, prefixes: list[str] | None = None) -> dict:
        if self.get_category(name):
            raise ValueError(f"Category '{name}' already exists")
        cat = {"name": name, "prefixes": prefixes or []}
        self._data.setdefault("categories", []).append(cat)
        self._save()
        return cat

    def update_category(self, name: str, new_name: str | None = None, prefixes: list[str] | None = None) -> dict:
        cats = self._data.setdefault("categories", [])
        for cat in cats:
            if cat["name"] == name:
                if new_name and new_name != name:
                    # update assignments that reference old name
                    asgn = self._data.setdefault("assignments", {})
                    for k, v in asgn.items():
                        if v == name:
                            asgn[k] = new_name
                    cat["name"] = new_name
                if prefixes is not None:
                    cat["prefixes"] = prefixes
                self._save()
                return cat
        raise KeyError(f"Category '{name}' not found")

    def delete_category(self, name: str) -> None:
        self._data["categories"] = [c for c in self.list_categories() if c["name"] != name]
        # remove assignments for this category
        asgn = self._data.setdefault("assignments", {})
        self._data["assignments"] = {k: v for k, v in asgn.items() if v != name}
        self._save()

    def add_prefix(self, category_name: str, prefix: str) -> dict:
        cat = self.get_category(category_name)
        if not cat:
            raise KeyError(f"Category '{category_name}' not found")
        if prefix not in cat["prefixes"]:
            cat["prefixes"].append(prefix)
            self._save()
        return cat

    def remove_prefix(self, category_name: str, prefix: str) -> dict:
        cat = self.get_category(category_name)
        if not cat:
            raise KeyError(f"Category '{category_name}' not found")
        cat["prefixes"] = [p for p in cat["prefixes"] if p != prefix]
        self._save()
        return cat

    # ── Assignments ─────────────────────────────────────────────────

    def get_assignments(self) -> dict[str, str]:
        return self._data.get("assignments", {})

    def assign(self, record_id: str, category_name: str, add_prefix: str | None = None) -> None:
        if category_name and not self.get_category(category_name):
            raise KeyError(f"Category '{category_name}' not found")
        asgn = self._data.setdefault("assignments", {})
        if category_name:
            asgn[str(record_id)] = category_name
        else:
            asgn.pop(str(record_id), None)
        if add_prefix and category_name:
            self.add_prefix(category_name, add_prefix)
        else:
            self._save()

    # ── Lookup ───────────────────────────────────────────────────────

    def resolve_category(self, record_id: str | int, basis: str | None) -> str | None:
        """Return category name for a record, checking assignments first, then prefixes."""
        rid = str(record_id)
        asgn = self._data.get("assignments", {})
        if rid in asgn:
            return asgn[rid]
        if not basis:
            return None
        t = basis.strip().upper()
        for cat in self.list_categories():
            for prefix in cat.get("prefixes", []):
                if t.startswith(prefix.upper()):
                    return cat["name"]
        return None

    def all_prefixes(self) -> list[str]:
        result = []
        for cat in self.list_categories():
            result.extend(cat.get("prefixes", []))
        return result


_repo: CashCategoryRepository | None = None


def get_cash_category_repository() -> CashCategoryRepository:
    global _repo
    if _repo is None:
        _repo = CashCategoryRepository()
    return _repo
