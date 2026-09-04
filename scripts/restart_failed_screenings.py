"""Перезапустить опрос тем, кому бот так и не смог написать.

Когда площадка отказывает в отправке приветствия, quick_screening ставит
состояние {"status": "waiting_admin", "reason": "send_failed"} и больше к
этому кандидату не возвращается. Так и задумано: повторять отправку на
каждой синхронизации, пока площадка отвечает отказом, — это бесконечный цикл
запросов, а человеку всё равно нужно вмешаться.

Но отказ бывает и временным. 04.09.2026 рассылка по двум вакансиям
администратора упёрлась в лимит hh: первые 15 сообщений ушли, следующие 9
подряд получили 403 disabled_by_employer, а через час те же самые отклики
приняли сообщение как ни в чём не бывало. Вакансия при этом была активна.
Девять человек остались в тупике навсегда — вот его и разбирает этот скрипт.

    python scripts/restart_failed_screenings.py                     # показать
    python scripts/restart_failed_screenings.py --apply             # написать
    python scripts/restart_failed_screenings.py --vacancy 3 --apply

Берёт только тех, кто ещё не сказал ни слова: состояние send_failed без
единого записанного ответа. Кандидата, с которым переписка уже началась,
трогать нельзя — он получит «Здравствуйте!» посреди разговора.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, RecruitmentSource, Vacancy
from app.services import quick_screening

# Та же пауза, что и в start_screening_backlog.py, и по той же причине —
# именно частота обращений и уронила рассылку 04.09.2026.
DELAY_SECONDS = 3.0


def _is_stuck(candidate) -> bool:
    state = quick_screening.load_state(candidate)
    return (state.get("status") == "waiting_admin"
            and state.get("reason") == "send_failed"
            and not (state.get("answers") or []))


async def run(vacancy_ids: list[int] | None, apply: bool, limit: int | None) -> int:
    init_db()
    db = SessionLocal()
    started = failed = 0
    try:
        sources = {s.source: s for s in db.query(RecruitmentSource).all()}
        vacancies = {v.id: v for v in db.query(Vacancy).all()}

        todo = []
        for c in db.query(Candidate).all():
            if vacancy_ids and c.vacancy_id not in vacancy_ids:
                continue
            if c.is_paused or not _is_stuck(c):
                continue
            vac = vacancies.get(c.vacancy_id)
            if not vac or not quick_screening.get_questions(vac):
                continue
            todo.append((c, vac))
        if limit:
            todo = todo[:limit]

        print(f"{datetime.now():%Y-%m-%d %H:%M} — застряло на сбое отправки: {len(todo)}")
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
            # start_screening отказывается стартовать поверх существующего
            # состояния — снимаем его прямо перед попыткой. Если отправка
            # снова не удастся, скрипт запишет то же самое send_failed.
            c.quick_state_json = None
            db.commit()
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
                print(f"  #{c.id} {c.name}: снова не начат — см. алерт в Telegram")
            await asyncio.sleep(DELAY_SECONDS)

        print(f"\nначато: {started}, не начато: {failed}")
        return started
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vacancy", type=int, nargs="+", default=None,
                    help="ограничиться этими вакансиями (по умолчанию — все)")
    ap.add_argument("--apply", action="store_true", help="отправить, а не показать")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    sys.exit(0 if asyncio.run(run(args.vacancy, args.apply, args.limit)) >= 0 else 1)
