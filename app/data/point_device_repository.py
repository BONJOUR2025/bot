"""Кабинет точки: какие рабочие ПК к какой точке подключены, отметки звонков
и журнал передачи смены.

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

from app.config import POINT_CALLS_FILE, POINT_DEVICES_FILE, POINT_HANDOVERS_FILE, POINT_NOTES_FILE

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


def _money_or_none(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


class PointHandoverRepository:
    """Журнал передачи смены: кто сдал, что проверил, сколько насчитал в кассе
    и что осталось на следующего. Принимающий подтверждает приём — своим
    пересчётом и комментарием, если что-то не сошлось. В Агбисе такого нет.

    Остаток кассы по Агбису на момент записи храним рядом с пересчётом: через
    час Агбис покажет уже другую цифру, а сверять надо с той, что была."""

    KEEP = 500  # записей на точку — хватает на год с лишним, файл не пухнет

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or POINT_HANDOVERS_FILE

    def list(self, salon_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = [r for r in _load(self._file, []) if r.get("salon_id") == salon_id]
        return list(reversed(rows))[:limit]

    def add(self, salon_id: str, device_id: str, *, by: str, cash_counted, cash_agbis,
            checklist: list[str], notes: str, passed: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        data = _load(self._file, [])
        rec = {"id": secrets.token_hex(5), "salon_id": salon_id, "device_id": device_id,
               "at": _now().isoformat(), "by": by.strip()[:80],
               "cash_counted": _money_or_none(cash_counted), "cash_agbis": _money_or_none(cash_agbis),
               "checklist": [str(x)[:80] for x in checklist][:12], "notes": (notes or "").strip()[:2000],
               "passed": passed or [], "accepted": None}
        data.append(rec)
        mine = [r for r in data if r.get("salon_id") == salon_id]
        if len(mine) > self.KEEP:
            drop = {id(r) for r in mine[:len(mine) - self.KEEP]}
            data = [r for r in data if id(r) not in drop]
        _save(self._file, data)
        return rec

    def accept(self, salon_id: str, rec_id: str, *, by: str, cash_counted, comment: str) -> Optional[dict[str, Any]]:
        data = _load(self._file, [])
        rec = next((r for r in data if r.get("id") == rec_id and r.get("salon_id") == salon_id), None)
        if rec is None:
            return None
        if rec.get("accepted"):
            return rec
        rec["accepted"] = {"by": by.strip()[:80], "at": _now().isoformat(),
                           "cash_counted": _money_or_none(cash_counted), "comment": (comment or "").strip()[:1000]}
        _save(self._file, data)
        return rec


class PointNoteRepository:
    """Заметки смены: «что передать» пишут в течение дня, а не одним полем при
    уходе. У каждой — дата, на которую она (сегодня, завтра, через неделю),
    и, если она про заказ, — сам заказ. Закрывает тот, кто сделал.

    Закрытые храним DONE_KEEP_DAYS дней — видно, что сделано, а файл не
    растёт бесконечно."""

    DONE_KEEP_DAYS = 30

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or POINT_NOTES_FILE

    def _prune(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        edge = (_now() - timedelta(days=self.DONE_KEEP_DAYS)).isoformat()
        return [n for n in data if not n.get("done") or n["done"].get("at", "") > edge]

    def list(self, salon_id: str) -> list[dict[str, Any]]:
        return [n for n in _load(self._file, []) if n.get("salon_id") == salon_id]

    def open_until(self, salon_id: str, until: str) -> list[dict[str, Any]]:
        return sorted((n for n in self.list(salon_id) if not n.get("done") and n.get("due", "") <= until),
                      key=lambda n: (n.get("due", ""), n.get("created_at", "")))

    def add(self, salon_id: str, device_id: str, *, text: str, due: str, by: str,
            order: Optional[dict[str, Any]]) -> dict[str, Any]:
        data = self._prune(_load(self._file, []))
        rec = {"id": secrets.token_hex(5), "salon_id": salon_id, "device_id": device_id,
               "text": text.strip()[:500], "due": due, "by": (by or "").strip()[:80],
               "created_at": _now().isoformat(), "order": order, "done": None}
        data.append(rec)
        _save(self._file, data)
        return rec

    def update(self, salon_id: str, note_id: str, *, due: Optional[str] = None, done: Optional[bool] = None,
               by: str = "", text: Optional[str] = None) -> Optional[dict[str, Any]]:
        data = _load(self._file, [])
        rec = next((n for n in data if n.get("id") == note_id and n.get("salon_id") == salon_id), None)
        if rec is None:
            return None
        if due is not None:
            rec["due"] = due
        if text is not None and text.strip():
            rec["text"] = text.strip()[:500]
        if done is True and not rec.get("done"):
            rec["done"] = {"at": _now().isoformat(), "by": (by or "").strip()[:80]}
        elif done is False:
            rec["done"] = None
        _save(self._file, self._prune(data))
        return rec

    def delete(self, salon_id: str, note_id: str) -> bool:
        data = _load(self._file, [])
        left = [n for n in data if not (n.get("id") == note_id and n.get("salon_id") == salon_id)]
        if len(left) == len(data):
            return False
        _save(self._file, left)
        return True
