"""Кабинет точки: какие рабочие ПК к какой точке подключены, и отметки звонков.

Подключение — одноразовым кодом: руководитель в «Салонах» выдаёт код, на ПК
точки его вводят один раз, и браузер получает свой ключ. Храним только хэш
ключа: утечка файла не даёт зайти в кабинет ни одной точки.

JSON-файлы, как у остальных репозиториев; перечитываем перед каждой записью —
пишут и bot-app, и (потенциально) другие процессы.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import POINT_CALLS_FILE, POINT_DEVICES_FILE

CODE_TTL = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def _save(path: str, data) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class PointDeviceRepository:
    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or POINT_DEVICES_FILE

    def _data(self) -> dict[str, Any]:
        data = _load(self._file, {})
        data.setdefault("devices", [])
        data.setdefault("codes", [])
        return data

    def issue_code(self, salon_id: str, author: str) -> dict[str, Any]:
        """Шесть цифр на 15 минут. Старые коды этой точки гасим."""
        data = self._data()
        now = _now()
        data["codes"] = [c for c in data["codes"]
                         if c.get("salon_id") != salon_id and c.get("expires_at", "") > now.isoformat()]
        taken = {c["code"] for c in data["codes"]}
        code = f"{secrets.randbelow(10**6):06d}"
        while code in taken:
            code = f"{secrets.randbelow(10**6):06d}"
        entry = {"code": code, "salon_id": salon_id, "author": author,
                 "expires_at": (now + CODE_TTL).isoformat()}
        data["codes"].append(entry)
        _save(self._file, data)
        return entry

    def activate(self, code: str, label: str) -> Optional[tuple[str, dict[str, Any]]]:
        """Обменять код на ключ ПК. Код одноразовый."""
        data = self._data()
        now = _now().isoformat()
        entry = next((c for c in data["codes"]
                      if secrets.compare_digest(str(c.get("code", "")), str(code or "").strip())
                      and c.get("expires_at", "") > now), None)
        if entry is None:
            return None
        data["codes"] = [c for c in data["codes"] if c is not entry]
        token = secrets.token_urlsafe(32)
        device = {"id": secrets.token_hex(6), "salon_id": entry["salon_id"], "label": (label or "").strip()[:60],
                  "token_hash": _hash(token), "created_at": now, "created_by": entry.get("author"),
                  "last_seen_at": now}
        data["devices"].append(device)
        _save(self._file, data)
        return token, device

    def by_token(self, token: str) -> Optional[dict[str, Any]]:
        if not token:
            return None
        h = _hash(token)
        data = self._data()
        for d in data["devices"]:
            if secrets.compare_digest(str(d.get("token_hash", "")), h):
                # last_seen пишем не чаще раза в 5 минут — иначе каждый запрос кабинета
                # переписывал бы файл.
                last = d.get("last_seen_at") or ""
                if last < (_now() - timedelta(minutes=5)).isoformat():
                    d["last_seen_at"] = _now().isoformat()
                    _save(self._file, data)
                return d
        return None

    def list(self, salon_id: Optional[str] = None) -> list[dict[str, Any]]:
        out = []
        for d in self._data()["devices"]:
            if salon_id and d.get("salon_id") != salon_id:
                continue
            out.append({k: v for k, v in d.items() if k != "token_hash"})
        return out

    def revoke(self, device_id: str) -> bool:
        data = self._data()
        before = len(data["devices"])
        data["devices"] = [d for d in data["devices"] if d.get("id") != device_id]
        if len(data["devices"]) == before:
            return False
        _save(self._file, data)
        return True


class PointCallRepository:
    """Отметки «позвонила клиенту» — в Агбисе такого поля нет (DATE_OUT_INFORM
    не заполняется), поэтому ведём у себя: заказ → последние отметки."""

    RESULTS = {"reached": "дозвонилась", "no_answer": "не ответил", "message": "написала в мессенджер"}

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or POINT_CALLS_FILE

    def add(self, order_id: int, result: str, note: str, salon_id: str, device_id: str) -> dict[str, Any]:
        data = _load(self._file, {})
        rec = {"at": _now().isoformat(), "result": result, "note": (note or "").strip()[:300],
               "salon_id": salon_id, "device_id": device_id}
        data.setdefault(str(order_id), []).append(rec)
        data[str(order_id)] = data[str(order_id)][-10:]
        _save(self._file, data)
        return rec

    def last_for(self, order_ids: list[int]) -> dict[int, dict[str, Any]]:
        data = _load(self._file, {})
        out = {}
        for oid in order_ids:
            recs = data.get(str(oid))
            if recs:
                out[oid] = {**recs[-1], "count": len(recs)}
        return out
