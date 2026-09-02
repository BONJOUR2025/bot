"""Разовая догрузка анкет резюме для уже импортированных откликов hh.

Импорт теперь сохраняет анкету (должность, ожидания по зарплате, стаж,
места работы, образование, навыки — см. hh_api.build_resume_profile), но
карточки, заведённые раньше, её не имеют, а следующий синк принесёт только
новые отклики. Этот скрипт добирает недостающее.

    python scripts/backfill_hh_resume_profiles.py            # только показать
    python scripts/backfill_hh_resume_profiles.py --apply    # выполнить

Резюме запрашивается по одному, с паузой: у hh есть лимиты, а спешить
некуда. Удалённое или скрытое резюме отдаёт 404 — это не ошибка скрипта,
у карточки просто не будет анкеты.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, RecruitmentSource
from app.services import candidate_merge as cm
from app.services import hh_api

PAUSE_SECONDS = 0.4


async def fetch(client: httpx.AsyncClient, token: str, resume_id: str) -> dict | None:
    r = await client.get(
        f"{hh_api.HH_BASE}/resumes/{resume_id}",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "bonjour-bot/1.0"},
    )
    if r.status_code != 200:
        return None
    return r.json()


async def run(apply: bool) -> int:
    init_db()
    db = SessionLocal()
    filled = missing = 0
    try:
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if not src or not src.access_token:
            print("hh.ru не подключён — токена нет.")
            return 0

        todo = [c for c in db.query(Candidate).filter(Candidate.source == "hh").all()
                if not c.resume_profile_json]
        print(f"карточек hh без анкеты: {len(todo)}")
        if not todo:
            return 0

        async with httpx.AsyncClient(timeout=30) as client:
            for c in todo:
                resume_id = (c.resume_id or "").strip() or cm.resume_id_from_url(c.resume_url)
                if not resume_id:
                    print(f"  #{c.id} {c.name}: id резюме неизвестен")
                    missing += 1
                    continue
                full = await fetch(client, src.access_token, resume_id)
                await asyncio.sleep(PAUSE_SECONDS)
                if not full:
                    print(f"  #{c.id} {c.name}: резюме недоступно (удалено или скрыто)")
                    missing += 1
                    continue

                # Списка откликов здесь нет — собираем из одного полного
                # резюме. Оно богаче списка везде, кроме `photo`, которое
                # у карточки и так уже есть.
                profile = hh_api.build_resume_profile(full, full)
                salary = (profile.get("salary") or {}).get("amount")
                print(f"  #{c.id} {c.name}: {profile.get('title') or '—'}"
                      f" | стаж {profile.get('total_months') or 0} мес"
                      f" | зп {salary or '—'} | навыков {len(profile.get('skills') or [])}")
                if apply:
                    import json

                    c.resume_profile_json = json.dumps(profile, ensure_ascii=False)
                filled += 1

        print(f"\nанкет собрано: {filled}, недоступно: {missing}")
        if apply:
            db.commit()
            print("Применено.")
        else:
            db.rollback()
            print("Ничего не изменено — запустите с --apply.")
    finally:
        db.close()
    return filled


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="сохранить, а не показать")
    args = ap.parse_args()
    sys.exit(0 if asyncio.run(run(args.apply)) >= 0 else 1)
