"""Сборка сводок ИИ для тех, у кого их нет, и пересборка устаревших.

Сводка собирается автоматически по завершении быстрого опроса. Этого мало
в двух случаях, и оба закрывает этот скрипт:

* кандидат ответил раньше, чем сводки появились вообще;
* кандидат не отвечал, но анкета с площадки есть — оценить по одному
  резюме можно, и это лучше пустой карточки. Такие сводки помечаются
  basis="resume", чтобы в карточке было видно, что опроса не было.

    python scripts/backfill_candidate_profiles.py            # только показать
    python scripts/backfill_candidate_profiles.py --apply    # выполнить
    python scripts/backfill_candidate_profiles.py --apply --force   # пересобрать всё

`--force` нужен после правки промпта: старые сводки собирались по одному
заголовку вакансии, без её текста, и отказывали за отсутствие профильного
опыта там, где вакансия обещает обучение. С ним печатается сравнение
«было → стало», чтобы изменения можно было просмотреть до того, как они
станут рабочей выдачей.
"""
from __future__ import annotations

import argparse
import json
import sys

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, Vacancy
from app.services import candidate_profile as cp
from app.services import quick_screening
from app.services.config_service import ConfigService

VERDICT = {"invite": "звонить", "reserve": "в резерв", "reject": "не подходит"}


def _answers(candidate, vacancy=None) -> list:
    """Ответы опроса, если он действительно завершён.

    Завершённость — это пройденные вопросы, а не статус. Статус "done"
    ставится, только когда бот сам закрыл разговор; если на последнем ответе
    он решил, что кандидат задал встречный вопрос, статус остаётся
    "waiting_admin" — при том что отвечено всё. Пока здесь проверялся только
    статус, такие анкеты не собирались вовсе: к 04.09.2026 накопилось пять
    кандидатов, ответивших на все вопросы и оставшихся без сводки.
    """
    state = quick_screening.load_state(candidate)
    if state.get("status") == "done":
        return state.get("answers") or []
    total = len(quick_screening.get_questions(vacancy)) if vacancy else 0
    if total and int(state.get("idx") or 0) >= total:
        return state.get("answers") or []
    return []


def run(apply: bool, force: bool, limit: int | None) -> int:
    init_db()
    cfg = ConfigService().load()
    db = SessionLocal()
    done = failed = 0
    try:
        todo = []
        for c in db.query(Candidate).all():
            if c.profile_json and not force:
                continue
            vacancy = (db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first()
                       if c.vacancy_id else None)
            answers = _answers(c, vacancy)
            # Оценивать нечего, только если нет ни анкеты, ни ответов.
            if not answers and not c.resume_profile():
                continue
            todo.append((c, answers))
        if limit:
            todo = todo[:limit]

        print(f"кандидатов к обработке: {len(todo)}")
        if not apply:
            for c, answers in todo:
                basis = "анкета+опрос" if (answers and c.resume_profile()) else (
                    "только опрос" if answers else "только анкета")
                print(f"  #{c.id} {c.name}: {basis}")
            print("\nНичего не изменено — запустите с --apply.")
            return len(todo)

        moved = []
        for c, answers in todo:
            before = None
            if c.profile_json:
                try:
                    before = json.loads(c.profile_json)
                except (ValueError, TypeError):
                    before = None
            vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first()
            profile = cp.generate(db, c, vacancy, answers, cfg)
            if not profile:
                print(f"  #{c.id} {c.name}: не получилось")
                failed += 1
                continue
            done += 1
            after = f"{profile.get('score')} {VERDICT.get(profile.get('recommendation'), '—')}"
            if before:
                was = f"{before.get('score')} {VERDICT.get(before.get('recommendation'), '—')}"
                mark = "  →" if was != after else "   "
                print(f"{mark} #{c.id} {c.name[:30]:30s} {was:18s} → {after}")
                if before.get("recommendation") != profile.get("recommendation"):
                    moved.append((c.name, was, after,
                                  profile.get("recommendation_reason") or ""))
            else:
                print(f"   #{c.id} {c.name[:30]:30s} {'—':18s} → {after}")

        print(f"\nсобрано: {done}, не удалось: {failed}")
        if moved:
            print(f"\nсменили вердикт: {len(moved)}")
            for name, was, after, why in moved:
                print(f"  {name[:32]:32s} {was:18s} → {after:18s} {why[:70]}")
        return done
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="собрать сводки, а не показать")
    ap.add_argument("--force", action="store_true",
                    help="пересобрать и те, у которых сводка уже есть")
    ap.add_argument("--limit", type=int, default=None, help="обработать не больше N кандидатов")
    args = ap.parse_args()
    sys.exit(0 if run(args.apply, args.force, args.limit) >= 0 else 1)
