"""Разовый перенос условно мёртвых кандидатов в резерв.

Кого переносим — ровно две группы, обе появились из объединённого импорта
Авито (он подтянул все чаты по объявлению, а не только формальные отклики):

1. **Не люди** — организации и безымянные чаты. Кандидатами не были никогда.
2. **Отклики старше 90 дней без единого сообщения.** Человек написал два
   года назад, ни разу не ответил, опрос ему не запускался.

Кого НЕ трогаем, даже если подходит под фильтр:
* всех, у кого шёл или шёл ранее опрос (есть quick_state) — там велась
  работа, и решение по ним принимает человек;
* всех, кто уже не в воронке (нанят/отказ/резерв);
* дубли — там есть риск склеить разных людей с частым именем.

Запуск из боевого каталога:

    python -m scripts.move_dead_candidates_to_reserve          # показать
    python -m scripts.move_dead_candidates_to_reserve --apply  # перенести

Без --apply не меняет ничего. Перенос обратим: в интерфейсе есть «Вернуть
в воронку», а в заметке остаётся причина и дата.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime

# Организации, сервисы и заглушки вместо имени. Держим отдельным списком, а
# не «угадываем по слову ремонт» — на этом уже один раз ошибочно попал живой
# кандидат (Осипов Алексей, прошедший опрос 4/4).
ORG_PATTERN = re.compile(
    r"(ООО|ИП\b|заборы|мастерская|lab\b|second|studio|студия|shop|магазин|доставка|сервис)",
    re.I,
)
PLACEHOLDER_NAMES = {"пользователь", "gro", "max", "user", "клиент"}

STALE_DAYS = 90


def classify(c, now: datetime) -> str | None:
    """Причина переноса или None, если кандидата трогать нельзя."""
    from app.services import quick_screening, recruitment_stages as rs

    if c.stage in rs.TERMINAL_STAGES:
        return None

    # Организация остаётся организацией, даже если по ней «прошёл опрос».
    # У «Заборы от профи» и «heirloom-second» стоит status=done с четырьмя
    # ответами — это massовый запуск зачёл за ответы старые реплики из чата,
    # а не диалог с кандидатом. Поэтому проверка имени идёт ДО проверки
    # состояния опроса.
    name = (c.name or "").strip()
    if not name or name.lower() in PLACEHOLDER_NAMES or ORG_PATTERN.search(name):
        return "не человек (организация или чат без имени)"

    if quick_screening.load_state(c):
        return None  # с человеком работали — решает оператор

    has_chat_history = bool((c.last_message_text or "").strip())
    age_days = (now - c.created_at).days if c.created_at else 0
    if age_days > STALE_DAYS and not has_chat_history:
        return f"отклик {age_days} дн. назад, переписки не было"
    return None


def main(apply: bool) -> int:
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate
    from app.services import recruitment_stages as rs

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        picked = []
        for c in db.query(Candidate).all():
            reason = classify(c, now)
            if reason:
                picked.append((c, reason))

        for c, reason in sorted(picked, key=lambda x: x[0].id):
            print(f"  #{c.id:<4} {(c.name or '')[:32]:32} {c.source:<6} {reason}")

        if not apply:
            print(f"\nБудет перенесено в резерв: {len(picked)} (запустите с --apply)")
            return 0

        stamp = now.strftime("%d.%m.%Y")
        for c, reason in picked:
            note = f"В резерв {stamp}: {reason}."
            c.notes = f"{c.notes}\n{note}".strip() if c.notes else note
            c.stage = rs.STAGE_RESERVE
            c.updated_at = now
        db.commit()
        print(f"\nПеренесено в резерв: {len(picked)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
