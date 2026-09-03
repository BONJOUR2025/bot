"""Запустить опрос по откликам, которые уже лежат в воронке без него.

Обычный импорт намеренно молчит про старые отклики: опрос стартует только
тем, кто написал после прошлой синхронизации (recruitment_sync.is_new_arrival).
Иначе подключение новой площадки рассылало бы «здравствуйте» людям
месячной давности. Но когда вакансию заводят задним числом, накопленные
отклики опросить как раз нужно — это делается здесь и только руками.

    python scripts/start_screening_backlog.py --vacancy 2 3
    python scripts/start_screening_backlog.py --vacancy 2 3 --apply

Пишет живым людям, поэтому по умолчанию только показывает. Берёт лишь тех,
у кого опрос не начинался вовсе, и не трогает поставленных на паузу.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, RecruitmentSource, Vacancy
from app.services import quick_screening

# Пауза между сообщениями: 24 обращения подряд в один API — это заметный
# всплеск, а торопиться здесь некуда.
DELAY_SECONDS = 3.0


async def run(vacancy_ids: list[int], apply: bool, limit: int | None) -> int:
    init_db()
    db = SessionLocal()
    started = failed = 0
    try:
        sources = {s.source: s for s in db.query(RecruitmentSource).all()}
        todo = []
        for vid in vacancy_ids:
            vac = db.query(Vacancy).filter(Vacancy.id == vid).first()
            if not vac:
                print(f"вакансии {vid} нет")
                continue
            if not quick_screening.get_questions(vac):
                print(f"у вакансии {vid} нет вопросов быстрого опроса — пропускаю")
                continue
            for c in db.query(Candidate).filter(Candidate.vacancy_id == vid).all():
                if c.is_paused:
                    continue
                if quick_screening.load_state(c):
                    continue  # опрос уже шёл или идёт
                todo.append((c, vac))
        if limit:
            todo = todo[:limit]

        print(f"{datetime.now():%Y-%m-%d %H:%M} — к опросу: {len(todo)}")
        for c, vac in todo:
            print(f"  #{c.id} {c.name} ({c.source}, {vac.title[:34]})")
        if not apply:
            print("\nНичего не отправлено — запустите с --apply.")
            return len(todo)

        for c, vac in todo:
            src = sources.get(c.source)
            if not src or not src.access_token:
                print(f"  #{c.id}: источник {c.source} не настроен")
                failed += 1
                continue
            try:
                ok = await quick_screening.start_screening(db, c, vac, src, src.access_token)
            except Exception as exc:
                print(f"  #{c.id} {c.name}: ошибка — {exc}")
                failed += 1
                continue
            if ok:
                started += 1
                print(f"  #{c.id} {c.name}: опрос начат")
            else:
                failed += 1
                print(f"  #{c.id} {c.name}: не начат (пауза, нерабочие часы или сбой отправки)")
            await asyncio.sleep(DELAY_SECONDS)

        print(f"\nначато: {started}, не начато: {failed}")
        return started
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vacancy", type=int, nargs="+", required=True,
                    help="id вакансий, по которым запускать опрос")
    ap.add_argument("--apply", action="store_true", help="отправить, а не показать")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    sys.exit(0 if asyncio.run(run(args.vacancy, args.apply, args.limit)) >= 0 else 1)
