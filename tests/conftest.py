"""Shared fixtures for the test suite."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Patch the telegram module early so we never hit the real (broken) library.
# The stub lives in <repo>/telegram_stub and is a lightweight replacement.
# ---------------------------------------------------------------------------
import importlib
import sys
from pathlib import Path as _Path
from types import ModuleType

_STUB_DIR = _Path(__file__).resolve().parent.parent / "telegram_stub"

if "telegram" not in sys.modules and _STUB_DIR.exists():
    # Register the stub as the ``telegram`` package
    sys.path.insert(0, str(_STUB_DIR.parent))
    _tg = importlib.import_module("telegram_stub")
    sys.modules["telegram"] = _tg

    # telegram.ext
    _ext = importlib.import_module("telegram_stub.ext")
    sys.modules["telegram.ext"] = _ext

    # telegram.error  (some files do ``from telegram.error import BadRequest``)
    _err = importlib.import_module("telegram_stub.error")
    sys.modules["telegram.error"] = _err

    # Add missing names to the telegram stub that the app imports
    for _name in ("InputFile",):
        if not hasattr(_tg, _name):
            setattr(_tg, _name, type(_name, (), {}))

    # Make sub-attributes reachable from the top-level ``telegram`` module
    _tg.ext = _ext
    _tg.error = _err

    # Provide Application stub for telegram.ext
    if not hasattr(_ext, "Application"):
        class _Application:
            class Builder:
                def __init__(self):
                    pass
                def token(self, t):
                    return self
                def build(self):
                    return _Application()
            @classmethod
            def builder(cls):
                return cls.Builder()
            async def initialize(self): pass
            async def start(self): pass
            async def stop(self): pass
            async def shutdown(self): pass
            async def process_update(self, u): pass
            bot = None
        _ext.Application = _Application
        _ext.ApplicationBuilder = _Application.Builder

    if not hasattr(_ext, "CommandHandler"):
        class _Handler:
            def __init__(self, *a, **kw): pass
        _ext.CommandHandler = _Handler

    if not hasattr(_ext, "CallbackQueryHandler"):
        class _CQHandler:
            def __init__(self, *a, **kw): pass
        _ext.CallbackQueryHandler = _CQHandler

# ---------------------------------------------------------------------------
# Stub for fpdf (cannot be built in this environment)
# ---------------------------------------------------------------------------
if "fpdf" not in sys.modules:
    _fpdf_mod = ModuleType("fpdf")
    class _FPDF:
        def __init__(self, *a, **kw): pass
        def add_page(self, *a, **kw): pass
        def set_font(self, *a, **kw): pass
        def cell(self, *a, **kw): pass
        def output(self, *a, **kw): return b""
        def add_font(self, *a, **kw): pass
        def multi_cell(self, *a, **kw): pass
        def set_xy(self, *a, **kw): pass
        def set_text_color(self, *a, **kw): pass
        def set_fill_color(self, *a, **kw): pass
        def image(self, *a, **kw): pass
        def ln(self, *a, **kw): pass
        def set_auto_page_break(self, *a, **kw): pass
        w = 210
        h = 297
    _fpdf_mod.FPDF = _FPDF
    sys.modules["fpdf"] = _fpdf_mod

# ---------------------------------------------------------------------------

import json
import os
import asyncio
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, List
from dataclasses import dataclass

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def write_json(path: Path | str, data: Any) -> Path:
    """Write *data* to a JSON file and return the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fixtures – temporary JSON files
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_json(tmp_path):
    """Return a helper that writes a JSON file inside *tmp_path*."""
    def _write(name: str, data: Any) -> str:
        p = tmp_path / name
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)
    return _write


@pytest.fixture
def empty_json(tmp_path):
    """Return a path to an empty JSON file."""
    p = tmp_path / "empty.json"
    p.write_text("[]", encoding="utf-8")
    return str(p)


@pytest.fixture
def empty_dict_json(tmp_path):
    """Return a path to a JSON file with empty dict."""
    p = tmp_path / "empty_dict.json"
    p.write_text("{}", encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Sample employee data
# ---------------------------------------------------------------------------

def make_employee_dict(
    uid: str = "100",
    name: str = "Иван",
    full_name: str = "Иванов Иван Иванович",
    phone: str = "+79001234567",
    position: str = "Продавец",
    status: str = "active",
    archived: bool = False,
    birthdate: str | None = None,
    **kwargs,
) -> Dict[str, Any]:
    data = {
        "name": name,
        "full_name": full_name,
        "phone": phone,
        "position": position,
        "is_admin": kwargs.get("is_admin", False),
        "card_number": kwargs.get("card_number", "1234567890123456"),
        "bank": kwargs.get("bank", "Сбер"),
        "work_place": kwargs.get("work_place", "Магазин 1"),
        "clothing_size": kwargs.get("clothing_size", "M"),
        "birthdate": birthdate,
        "note": kwargs.get("note", ""),
        "photo_url": kwargs.get("photo_url", ""),
        "status": status,
        "created_at": kwargs.get("created_at", datetime.utcnow().isoformat()),
        "tags": kwargs.get("tags", []),
        "payout_chat_key": kwargs.get("payout_chat_key", None),
        "archived": archived,
        "archived_at": kwargs.get("archived_at", None),
    }
    return data


def make_employees_json(employees: Dict[str, Dict] | None = None) -> Dict[str, Dict]:
    """Build a dict suitable for user.json."""
    if employees is not None:
        return employees
    return {
        "100": make_employee_dict("100", "Иван", "Иванов Иван Иванович"),
        "200": make_employee_dict("200", "Мария", "Петрова Мария Сергеевна",
                                   position="Администратор"),
        "300": make_employee_dict("300", "Алексей", "Сидоров Алексей Дмитриевич",
                                   status="inactive"),
    }


# ---------------------------------------------------------------------------
# Sample payout data
# ---------------------------------------------------------------------------

def make_payout_dict(
    payout_id: int = 1,
    user_id: str = "100",
    name: str = "Иван",
    amount: float = 5000,
    status: str = "Ожидает",
    **kwargs,
) -> Dict[str, Any]:
    return {
        "id": payout_id,
        "user_id": user_id,
        "name": name,
        "phone": kwargs.get("phone", "+79001234567"),
        "card_number": kwargs.get("card_number", "1234567890123456"),
        "bank": kwargs.get("bank", "Сбер"),
        "amount": amount,
        "method": kwargs.get("method", "💳 На карту"),
        "payout_type": kwargs.get("payout_type", "Аванс"),
        "status": status,
        "timestamp": kwargs.get("timestamp", "2025-01-15 10:30:00"),
    }


# ---------------------------------------------------------------------------
# Sample vacation data
# ---------------------------------------------------------------------------

def make_vacation_dict(
    vac_id: int = 1,
    employee_id: str = "100",
    name: str = "Иван",
    **kwargs,
) -> Dict[str, Any]:
    return {
        "id": vac_id,
        "employee_id": employee_id,
        "name": name,
        "start_date": kwargs.get("start_date", "2025-06-01"),
        "end_date": kwargs.get("end_date", "2025-06-14"),
        "type": kwargs.get("type", "Отпуск"),
        "comment": kwargs.get("comment", ""),
    }


# ---------------------------------------------------------------------------
# Sample incentive data
# ---------------------------------------------------------------------------

def make_incentive_dict(
    item_id: int = 1,
    employee_id: str = "100",
    **kwargs,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "employee_id": employee_id,
        "name": kwargs.get("name", "Иван"),
        "type": kwargs.get("type", "bonus"),
        "amount": kwargs.get("amount", 1000),
        "reason": kwargs.get("reason", "За хорошую работу"),
        "date": kwargs.get("date", "2025-01-15"),
        "added_by": kwargs.get("added_by", "admin"),
        "locked": kwargs.get("locked", False),
    }


# ---------------------------------------------------------------------------
# Sample asset data
# ---------------------------------------------------------------------------

def make_asset_dict(
    item_id: int = 1,
    employee_id: str = "100",
    **kwargs,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "employee_id": employee_id,
        "employee_name": kwargs.get("employee_name", "Иван"),
        "position": kwargs.get("position", "Продавец"),
        "item_name": kwargs.get("item_name", "Футболка"),
        "size": kwargs.get("size", "M"),
        "quantity": kwargs.get("quantity", 1),
        "issue_date": kwargs.get("issue_date", "2025-01-10"),
        "return_date": kwargs.get("return_date", None),
        "service_life": kwargs.get("service_life", None),
    }


# ---------------------------------------------------------------------------
# Sample adjustment data
# ---------------------------------------------------------------------------

def make_adjustment_dict(
    adj_id: int = 1,
    employee_id: str = "100",
    **kwargs,
) -> Dict[str, Any]:
    return {
        "id": adj_id,
        "employee_id": employee_id,
        "employee_name": kwargs.get("employee_name", "Иван"),
        "record_type": kwargs.get("record_type", "Премия"),
        "reason": kwargs.get("reason", "Хорошая работа"),
        "amount": kwargs.get("amount", 2000),
        "date": kwargs.get("date", "2025-01-15"),
        "status": kwargs.get("status", "active"),
    }


# ---------------------------------------------------------------------------
# Sample message data
# ---------------------------------------------------------------------------

def make_message_dict(
    msg_id: str = "1",
    user_id: str = "100",
    **kwargs,
) -> Dict[str, Any]:
    return {
        "id": msg_id,
        "user_id": user_id,
        "name": kwargs.get("name", "Иван"),
        "text": kwargs.get("text", "Тестовое сообщение"),
        "photo": kwargs.get("photo", None),
        "status": kwargs.get("status", "Отправлено"),
        "accepted": kwargs.get("accepted", False),
        "timestamp": kwargs.get("timestamp", "2025-01-15T10:30:00"),
        "message_id": kwargs.get("message_id", 12345),
    }
