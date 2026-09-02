"""Разовая догрузка сводок ИИ для тех, кто уже прошёл опрос.

Сводка теперь собирается автоматически по завершении быстрого опроса, но
кандидаты, ответившие раньше, её не имеют — а именно они и лежат сейчас в
воронке. Скрипт проходит по ним один раз.

    python scripts/backfill_candidate_profiles.py            # только показать
    python scripts/backfill_candidate_profiles.py --apply    # выполнить

Берутся только те, у кого опрос действительно завершён и есть хотя бы один
ответ: собирать сводку по пустой анкете незачем. Уже собранные сводки не
перезаписываются.
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, Vacancy
from app.services import candidate_profile as cp
from app.services import quick_screening
from app.services.config_service import ConfigService

VERDICT = {"invite": "звонить", "reserve": "в резерв", "reject": "не подходит"}


def run(apply: bool, limit: int | None) -> int:
    init_db()
    cfg = ConfigService().load()
    db = SessionLocal()
    done = failed = 0
    try:
        todo = []
        for c in db.query(Candidate).all():
            if c.profile_json:
                continue
            state = quick_screening.load_state(c)
            if state.get("status") != "done" or not (state.get("answers") or []):
                continue
            todo.append((c, state))
        if limit:
            todo = todo[:limit]

        print(f"кандидатов с завершённым опросом и без сводки: {len(todo)}")
        if not apply:
            for c, state in todo:
                print(f"  #{c.id} {c.name}: ответов {len(state['answers'])},"
                      f" анкета {'есть' if c.resume_profile() else 'нет'}")
            print("\nНичего не изменено — запустите с --apply.")
            return len(todo)

        for c, state in todo:
            vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first()
            profile = cp.generate(db, c, vacancy, state["answers"], cfg)
            if not profile:
                print(f"  #{c.id} {c.name}: не получилось")
                failed += 1
                continue
            done += 1
            print(f"  #{c.id} {c.name}: {profile.get('score')}/100"
                  f" · {VERDICT.get(profile.get('recommendation'), '—')}"
                  f" · {(profile.get('summary') or '')[:80]}")

        print(f"\nсобрано: {done}, не удалось: {failed}")
    finally:
        db.close()
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="собрать сводки, а не показать")
    ap.add_argument("--limit", type=int, default=None, help="обработать не больше N кандидатов")
    args = ap.parse_args()
    sys.exit(0 if run(args.apply, args.limit) >= 0 else 1)
