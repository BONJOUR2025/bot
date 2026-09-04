"""Проставить отметку «опрос дошёл до конца» тем, кто прошёл его раньше.

quick_screening пишет в состояние `completed`, когда вопросы кончились. По
этой отметке воронка отличает «опрос идёт» от «ответил, но разговор передан
человеку» — иначе кандидат, ответивший на всё и задавший встречный вопрос,
висит в колонке «Опрос» вперемешку с теми, кто ещё не сказал ни слова, и
возвращается туда после каждого обновления страницы.

Отметки нет у тех, чей опрос завершился до её появления. Скрипт ставит её
задним числом: по числу пройденных вопросов, а не по статусу — статус как
раз и не отличает эти два случая.

    python scripts/mark_completed_screenings.py            # только показать
    python scripts/mark_completed_screenings.py --apply    # проставить

Идемпотентен: у кого отметка уже есть, того не трогает.
"""
from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate, Vacancy
from app.services import quick_screening
from app.services import recruitment_stages as rs


def run(apply: bool) -> int:
    init_db()
    db = SessionLocal()
    changed = 0
    try:
        questions_by_vacancy: dict[int, int] = {}
        todo = []
        for c in db.query(Candidate).all():
            state = quick_screening.load_state(c)
            if not state or state.get("completed"):
                continue
            if c.vacancy_id not in questions_by_vacancy:
                vac = (db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first()
                       if c.vacancy_id else None)
                questions_by_vacancy[c.vacancy_id] = len(quick_screening.get_questions(vac))
            total = questions_by_vacancy[c.vacancy_id]
            if not total or int(state.get("idx") or 0) < total:
                continue
            todo.append((c, state, total))

        print(f"пройденных опросов без отметки: {len(todo)}")
        for c, state, total in todo:
            was = rs.derive_stage(c.stage, state)
            becomes = rs.derive_stage(c.stage, {**state, "completed": True})
            arrow = f"{was} → {becomes}" if was != becomes else was
            print(f"  #{c.id:>4} {c.name[:28]:<28} ответов {len(state.get('answers') or [])}/{total}  {arrow}")
            if apply:
                state["completed"] = True
                quick_screening.save_state(db, c, state)
                changed += 1

        if apply:
            print(f"\nпроставлено: {changed}")
        else:
            print("\nНичего не изменено — запустите с --apply.")
        return changed
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="проставить, а не показать")
    args = ap.parse_args()
    sys.exit(0 if run(args.apply) >= 0 else 1)
