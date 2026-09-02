"""Разовое схлопывание дублей кандидатов.

Зачем: `external_id` площадки — это id ОТКЛИКА, а не человека. Пока
дедупликация шла по нему, один кандидат, откликнувшийся на два наших
объявления, получал две карточки, два чата и два параллельных опроса. Импорт
это уже не допускает (см. recruitment_sync._find_twin), но накопленные
дубли надо разобрать отдельно.

Порядок: сначала проставляем `resume_id` тем, кто импортирован до появления
колонки, потом склеиваем по нему внутри hh, потом по нормализованному
телефону между площадками.

    python -m scripts.merge_duplicate_candidates            # только показать
    python -m scripts.merge_duplicate_candidates --apply    # выполнить

Без `--apply` не меняется ничего: скрипт печатает, что бы он сделал.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from app.db.session import SessionLocal, init_db
from app.models.recruitment import Candidate
from app.services import candidate_merge as cm

LABEL = {"hh": "hh.ru", "avito": "Авито", "manual": "вручную"}


def _line(c: Candidate) -> str:
    return (f"#{c.id} {c.name} [{LABEL.get(c.source, c.source)}/{c.stage}] "
            f"тел={c.phone or '—'} отклик={c.created_at:%Y-%m-%d}")


def backfill_resume_ids(db, apply: bool) -> int:
    """Проставить resume_id тем, у кого он пуст, а ссылка на резюме есть."""
    todo = []
    for c in db.query(Candidate).filter(Candidate.source == "hh").all():
        if (c.resume_id or "").strip():
            continue
        rid = cm.resume_id_from_url(c.resume_url)
        if rid:
            todo.append((c, rid))
    print(f"resume_id к проставлению: {len(todo)}")
    if apply:
        for c, rid in todo:
            c.resume_id = rid
        db.flush()
    return len(todo)


def _groups(db) -> list[tuple[str, str, list[Candidate]]]:
    """Группы карточек одного человека: (причина, ключ, карточки)."""
    out: list[tuple[str, str, list[Candidate]]] = []
    everyone = db.query(Candidate).all()

    by_resume: dict[tuple, list[Candidate]] = defaultdict(list)
    for c in everyone:
        if c.source != "hh":
            continue
        key = cm.duplicate_key_hh(c)
        if key:
            by_resume[(c.vacancy_id, key)].append(c)
    for (vac, key), group in by_resume.items():
        if len(group) > 1:
            out.append((cm.REASON_RESUME, f"резюме {key}", group))

    # Телефон — уже с учётом того, что часть карточек схлопнется по резюме:
    # группы пересекаются, поэтому слияние идёт последовательно и вторая
    # проходка работает с тем, что осталось.
    merged_ids = {c.id for _, _, g in out for c in g[1:]}
    by_phone: dict[tuple, list[Candidate]] = defaultdict(list)
    for c in everyone:
        if c.id in merged_ids:
            continue
        key = cm.duplicate_key_phone(c)
        if key:
            by_phone[(c.vacancy_id, key)].append(c)
    for (vac, key), group in by_phone.items():
        if len(group) > 1:
            out.append((cm.REASON_PHONE, f"телефон +{key}", group))
    return out


def run(apply: bool) -> int:
    init_db()
    db = SessionLocal()
    removed = 0
    try:
        backfill_resume_ids(db, apply)
        groups = _groups(db)
        if not groups:
            print("Дублей не найдено.")
            return 0

        print(f"\nГрупп дублей: {len(groups)}\n")
        for reason, key, group in groups:
            # Победитель выбирается попарно тем же правилом, что и в импорте:
            # hh важнее Авито, дальше — этап, полнота опроса, дата отклика.
            winner = group[0]
            for other in group[1:]:
                winner, _ = cm.pick_winner(winner, other)
            losers = [c for c in group if c is not winner]

            stage = winner.stage
            for l in losers:
                stage = cm.pick_stage(
                    type("S", (), {"stage": stage, "updated_at": winner.updated_at,
                                   "created_at": winner.created_at})(), l)

            print(f"— {key} ({reason})")
            print(f"    остаётся  {_line(winner)}")
            for l in losers:
                print(f"    вливается {_line(l)}")
            if stage != winner.stage:
                print(f"    этап после слияния: «{stage}» (решение человека с другой карточки)")

            if apply:
                for l in losers:
                    cm.merge(winner, l, reason)
                db.flush()
                for l in losers:
                    db.delete(l)
                db.flush()
            removed += len(losers)

        print(f"\nКарточек к удалению: {removed}")
        if apply:
            db.commit()
            print("Применено.")
        else:
            db.rollback()
            print("Ничего не изменено — запустите с --apply.")
    finally:
        db.close()
    return removed


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="выполнить слияние, а не показать")
    args = ap.parse_args()
    sys.exit(0 if run(args.apply) >= 0 else 1)
