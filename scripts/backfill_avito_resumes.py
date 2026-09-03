"""Разовая догрузка анкет для карточек, пришедших с Авито.

Резюме Авито отдаёт отдельным документом по `resume_id` из отклика, а
забирать его синхронизация научилась только сейчас. Карточки, заведённые
раньше, анкеты не имеют — и сводка ИИ по ним писалась вслепую: «Мастер по
коже» с восемью годами стажа получил 30/100 и вердикт «не подходит» с
формулировкой «не указано исправление обуви».

    python scripts/backfill_avito_resumes.py            # только показать
    python scripts/backfill_avito_resumes.py --apply    # выполнить

Сопоставление идёт по id отклика, а при его отсутствии — по id чата:
карточки, заведённые из чата, а не из платного API откликов, знают только
второе. Уже заполненные анкеты не перезаписываются: свежий снимок принесёт
обычная синхронизация.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, RecruitmentSource, VacancyLink
from app.services import avito_api


async def collect_resume_ids(token: str, employer_id: str,
                             vacancy_ids: list[str]) -> tuple[dict, dict]:
    """Карты «отклик → resume_id» и «чат → resume_id» по всем связкам."""
    by_external: dict[str, str] = {}
    by_chat: dict[str, str] = {}
    for vid in vacancy_ids:
        try:
            items = await avito_api.get_applications_for_vacancy(token, employer_id, vid)
        except Exception as exc:
            print(f"  вакансия {vid}: отклики недоступны ({exc})")
            continue
        for it in items:
            rid = (it.get("resume_id") or "").strip()
            if not rid:
                continue
            if it.get("external_id"):
                by_external[str(it["external_id"])] = rid
            if it.get("platform_chat_id"):
                by_chat[str(it["platform_chat_id"])] = rid
    return by_external, by_chat


def avito_keys(candidate: Candidate) -> list[tuple[str, str]]:
    """Пары (external_id, chat_id) всех авито-каналов карточки.

    После объединения дублей отклик Авито может лежать не в основном
    канале, а в channels — тогда id отклика есть только там.
    """
    keys = []
    if candidate.source == "avito":
        keys.append((candidate.external_id or "", candidate.platform_chat_id or ""))
    for ch in candidate.channels():
        if ch.get("source") == "avito":
            keys.append((ch.get("external_id") or "", ch.get("platform_chat_id") or ""))
    return keys


async def run(apply: bool, limit: int | None) -> int:
    init_db()
    db = SessionLocal()
    try:
        src = db.query(RecruitmentSource).filter(
            RecruitmentSource.source == "avito").first()
        if not src or not src.access_token:
            print("Источник Авито не настроен.")
            return 0
        vacancy_ids = [l.external_vacancy_id for l in
                       db.query(VacancyLink).filter(VacancyLink.source == "avito").all()]
        print(f"связок с Авито: {len(vacancy_ids)}")

        by_external, by_chat = await collect_resume_ids(
            src.access_token, src.employer_id, vacancy_ids)
        print(f"откликов с резюме на площадке: {len(by_external)}")

        todo = []
        for c in db.query(Candidate).all():
            if c.resume_profile():
                continue
            rid = ""
            for ext, chat in avito_keys(c):
                rid = by_external.get(ext) or by_chat.get(chat) or ""
                if rid:
                    break
            if rid:
                todo.append((c, rid))
        if limit:
            todo = todo[:limit]

        print(f"карточек без анкеты, для которых резюме нашлось: {len(todo)}")
        if not apply:
            for c, rid in todo:
                print(f"  #{c.id} {c.name} → резюме {rid}")
            print("\nНичего не изменено — запустите с --apply.")
            return len(todo)

        done = missing = 0
        for c, rid in todo:
            profile = await avito_api.get_resume(src.access_token, rid)
            if not profile:
                print(f"  #{c.id} {c.name}: резюме {rid} недоступно")
                missing += 1
                continue
            c.resume_profile_json = json.dumps(profile, ensure_ascii=False)
            done += 1
            months = profile.get("total_months")
            print(f"  #{c.id} {c.name}: {profile.get('title') or '—'}"
                  f" · стаж {months // 12 if months else 0} г.")
        db.commit()
        print(f"\nанкет добавлено: {done}, недоступно: {missing}")
        return done
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="сохранить анкеты, а не показать")
    ap.add_argument("--limit", type=int, default=None, help="обработать не больше N карточек")
    args = ap.parse_args()
    sys.exit(0 if asyncio.run(run(args.apply, args.limit)) >= 0 else 1)
