"""Наложение деления услуг (ServiceSplitRepository) на отчёт мастеров.

Отчёт masters.works — дорогой и живёт в кэше; деление туда не зашиваем, а
накладываем при каждом чтении: старший мастер поделил — и в «Мастерах»,
в заработке мастера и в «Цехе» это видно сразу, без пересчёта отчёта.

У поделённой услуги появляется поле `split`: список долей
{user_id, master, share, salary, kredit}. `master` — строка мастера из Агбиса
(USERS.DESCRIPTION), та же, что в out_description: по ней отчёт группирует
зарплату, и доля должна попасть в ту же строку, что и остальные работы
мастера. Всё остальное в строке услуги не меняется — сумма по услуге та же,
меняется только, кому она достаётся.

Зарплата делится только у услуг с выходом (master_salary не пустой): без
выхода её ещё нет, делить нечего — но само деление хранится и применится,
как только выход появится.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

MIN_PARTS = 2
MAX_PARTS = 5


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def agbis_names() -> dict[int, str]:
    """USERS.DESCRIPTION по USER_ID — из прогретого кэша справочника."""
    from app.services import fdb_cache

    try:
        rows = fdb_cache.get_or_compute("employees.users_list", ("",)) or []
    except Exception:
        logger.warning("Справочник пользователей Агбиса недоступен", exc_info=True)
        return {}
    return {int(r["user_id"]): r.get("description") or "" for r in rows if r.get("user_id") is not None}


def _parts_for(svc: dict[str, Any], rec: dict[str, Any]) -> list[dict[str, Any]]:
    salary = svc.get("master_salary")
    kredit = _num(svc.get("kredit"))
    parts = []
    for p in rec.get("parts") or []:
        share = _num(p.get("share"))
        parts.append({
            "user_id": p.get("user_id"),
            "master": p.get("agbis_name") or p.get("name") or "—",
            "name": p.get("name") or p.get("agbis_name") or "—",
            "share": share,
            "salary": round(_num(salary) * share, 2) if salary is not None else None,
            "kredit": round(kredit * share, 2),
        })
    return parts


def apply(services: list[dict[str, Any]], splits: Optional[dict[int, dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Копия списка услуг, где у поделённых есть `split`."""
    if splits is None:
        from app.data.service_split_repository import ServiceSplitRepository

        splits = ServiceSplitRepository().all()
    if not splits:
        return services
    out = []
    for svc in services:
        try:
            rec = splits.get(int(svc.get("service_id")))
        except (TypeError, ValueError):
            rec = None
        if rec:
            svc = {**svc, "split": _parts_for(svc, rec), "split_by": rec.get("by"), "split_at": rec.get("at")}
        out.append(svc)
    return out


def salary_parts(svc: dict[str, Any]) -> list[dict[str, Any]]:
    """Кому и сколько по услуге: доли, если поделена, иначе — мастер выхода."""
    if svc.get("master_salary") is None:
        return []
    if svc.get("split"):
        return svc["split"]
    return [{"user_id": svc.get("out_user_id"), "master": svc.get("out_description") or "Неизвестный мастер",
             "share": 1.0, "salary": _num(svc.get("master_salary")), "kredit": _num(svc.get("kredit"))}]


def apply_result(result: dict[str, Any]) -> dict[str, Any]:
    """Отчёт masters.works с наложенным делением: услуги и сводка по мастерам.

    Сводку пересобираем только если деление в периоде вообще есть — иначе
    отдаём как было, до байта."""
    services = (result or {}).get("services") or []
    applied = apply(services)
    if applied is services or not any(s.get("split") for s in applied):
        return result
    return {**result, "services": applied,
            "salary_summary": _rebuild_summary(applied, result.get("salary_summary") or [])}


def _rebuild_summary(services: list[dict[str, Any]], old: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Та же сводка, что masters_service._build_salary_summary, но по долям.

    Услуга, поделённая на двоих, засчитывается в «услуг сделано» обоим —
    каждый в ней участвовал; сумма работ и зарплата — по доле."""
    rows: dict[str, dict[str, Any]] = {}
    for svc in services:
        for part in salary_parts(svc):
            name = part["master"]
            r = rows.setdefault(name, {"master": name, "services_done": 0, "total_kredit": 0.0,
                                       "total_salary": 0.0, "warnings_count": 0})
            r["services_done"] += 1
            r["total_kredit"] += _num(part["kredit"])
            r["total_salary"] += _num(part["salary"])
            r["warnings_count"] += 1 if svc.get("warnings") else 0
    advances = {r.get("master"): _num(r.get("advances_since_last_salary")) for r in old}
    missing = [n for n in rows if n not in advances]
    if missing:
        try:
            from app.services.masters_service import _advances_since_last_salary_by_master

            advances.update({k: _num(v) for k, v in _advances_since_last_salary_by_master(missing).items()})
        except Exception:
            logger.warning("Авансы для поделённых услуг не получены", exc_info=True)
    # Процент с продаж ключей (masters_service._add_key_sales) к услугам не
    # привязан — переносим его из исходной сводки как есть.
    for o in old:
        if o.get("keys_salary"):
            r = rows.setdefault(o["master"], {"master": o["master"], "services_done": 0, "total_kredit": 0.0,
                                              "total_salary": 0.0, "warnings_count": 0})
            r["keys_revenue"] = o.get("keys_revenue")
            r["keys_salary"] = o["keys_salary"]
            r["total_salary"] += _num(o["keys_salary"])
    out = []
    for r in rows.values():
        r["total_kredit"] = round(r["total_kredit"], 2)
        r["total_salary"] = round(r["total_salary"], 2)
        r["advances_since_last_salary"] = round(advances.get(r["master"], 0.0), 2)
        r["to_pay"] = round(r["total_salary"] - r["advances_since_last_salary"], 2)
        out.append(r)
    return sorted(out, key=lambda r: r["total_salary"], reverse=True)


def validate_parts(parts: list[dict[str, Any]], masters: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Доли от старшего мастера → то, что храним. Проценты целые, в сумме 100.

    Бросает ValueError с понятным текстом — он уходит прямо на экран."""
    if not (MIN_PARTS <= len(parts) <= MAX_PARTS):
        raise ValueError(f"Делить можно на {MIN_PARTS}–{MAX_PARTS} мастеров.")
    seen = set()
    total = 0
    names = agbis_names()
    out = []
    for p in parts:
        uid = int(p["master_uid"])
        pct = int(p["percent"])
        if uid in seen:
            raise ValueError("Один мастер указан дважды.")
        if uid not in masters:
            raise ValueError("Выберите мастеров из списка.")
        if pct <= 0:
            raise ValueError("У каждого мастера доля должна быть больше нуля.")
        seen.add(uid)
        total += pct
        out.append({"user_id": uid, "name": masters[uid]["name"], "agbis_name": names.get(uid) or masters[uid]["name"],
                    "share": round(pct / 100, 4), "percent": pct})
    if total != 100:
        raise ValueError(f"Доли в сумме должны давать 100%, сейчас {total}%.")
    return out
