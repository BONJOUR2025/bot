"""Слияние карточек одного человека.

Зачем вообще: `external_id` у площадки — это идентификатор ОТКЛИКА, а не
человека. Один кандидат, откликнувшийся на два наших объявления hh, получал
два отклика, два чата и две карточки — и бот вёл с ним два опроса
параллельно, в разных чатах задавая одни и те же вопросы. Тот же эффект
давал отклик на Авито и на hh одновременно.

Ключи, по которым карточки признаются одним человеком, живут в
`duplicate_key_*`: для hh это id резюме (у человека оно одно на все отклики),
между площадками — нормализованный номер телефона. Номера есть не у всех, и
это принято: лучше не склеить двоих, чем склеить разных.

Само слияние — чистая функция над двумя ORM-объектами, без запросов и без
commit: этим управляет вызывающий код (импорт, разовый скрипт, ручное
слияние из карточки).
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from app.services import recruitment_stages as rs

# Кто выживает при слиянии разных площадок. hh выигрывает не потому, что
# «лучше», а потому, что там переписка живёт в отклике и не зависит от
# тарифа: Messenger API Авито доступен только на «Максимальном», и именно
# он отваливался. Бот пишет в основной канал — значит, опрос пойдёт через hh.
SOURCE_RANK = {"hh": 3, "avito": 2, "manual": 1}

# Насколько далеко карточка продвинулась. Ручные этапы стоят выше
# автоматических: если человек перевёл клона в «собеседование», это решение
# и должно пережить слияние.
STAGE_RANK = {
    rs.STAGE_NEW: 0,
    rs.STAGE_SCREENING: 1,
    rs.STAGE_ANSWERED: 2,
    rs.STAGE_THINKING: 3,
    rs.STAGE_INTERVIEW: 4,
    rs.STAGE_RESERVE: 5,
    rs.STAGE_REJECTED: 6,
    rs.STAGE_HIRED: 7,
}

REASON_RESUME = "resume_id"
REASON_PHONE = "phone"


# ── ключи дубликата ──────────────────────────────────────────────────────

def normalize_phone(raw: str | None) -> str:
    """К одиннадцати цифрам с ведущей 7. Пустая строка — «ключа нет»."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits if len(digits) == 11 and digits[0] == "7" else ""


def resume_id_from_url(url: str | None) -> str:
    """`https://hh.ru/resume/<id>?t=...&vacancyId=...` → `<id>`.

    Query-параметры отбрасываются намеренно: в них лежат id отклика и id
    объявления, и именно из-за них две карточки одного человека выглядели
    как разные резюме при сравнении строк целиком.
    """
    m = re.search(r"/resume/([0-9a-zA-Z]+)", url or "")
    return m.group(1) if m else ""


def duplicate_key_hh(candidate) -> str:
    """Ключ «тот же человек на hh»."""
    return (getattr(candidate, "resume_id", "") or "").strip() or resume_id_from_url(
        getattr(candidate, "resume_url", ""))


def duplicate_key_phone(candidate) -> str:
    """Ключ «тот же человек на другой площадке»."""
    return normalize_phone(getattr(candidate, "phone", ""))


# ── выбор победителя ─────────────────────────────────────────────────────

def _answers_count(candidate) -> int:
    from app.services import quick_screening

    state = quick_screening.load_state(candidate) or {}
    return len(state.get("answers") or [])


def _created(candidate) -> datetime:
    return getattr(candidate, "created_at", None) or datetime.max


def pick_winner(a, b):
    """Какая из двух карточек остаётся. Возвращает (winner, loser).

    Порядок сравнения: площадка (hh пишется надёжнее) → продвинутость этапа
    → полнота опроса → более ранний отклик. Последнее — чтобы за
    объединённой карточкой сохранилась настоящая дата отклика, по которой
    считается возраст в канбане.
    """
    def key(c):
        return (
            SOURCE_RANK.get(getattr(c, "source", ""), 0),
            STAGE_RANK.get(getattr(c, "stage", ""), 0),
            _answers_count(c),
            -_created(c).timestamp(),
        )

    return (a, b) if key(a) >= key(b) else (b, a)


# ── само слияние ─────────────────────────────────────────────────────────

def _channel_of(candidate) -> dict:
    return {
        "source": getattr(candidate, "source", "") or "",
        "external_id": getattr(candidate, "external_id", "") or "",
        "platform_chat_id": getattr(candidate, "platform_chat_id", "") or "",
    }


def _same_channel(x: dict, y: dict) -> bool:
    return (x.get("source"), x.get("external_id")) == (y.get("source"), y.get("external_id"))


def _merge_channels(winner, loser, now: datetime) -> list:
    """Каналы победителя + канал проигравшего + всё, что уже было у обоих."""
    out: list = []

    def add(ch: dict) -> None:
        if not (ch.get("external_id") or ch.get("platform_chat_id")):
            return
        if _same_channel(ch, _channel_of(winner)):
            return  # основной канал в списке дополнительных не дублируется
        if any(_same_channel(ch, seen) for seen in out):
            return
        out.append(ch)

    for ch in winner.channels():
        add(ch)
    add({**_channel_of(loser), "added_at": now.isoformat(),
         "from_candidate_id": getattr(loser, "id", None)})
    for ch in loser.channels():
        add(ch)
    return out


def _pick_state(winner, loser):
    """Состояние опроса — то, где ответов больше.

    Если человек отвечал в обоих чатах, склеивать ответы нельзя: у них
    разная нумерация вопросов, и получилась бы каша из ответа на первый
    вопрос и ответа на третий. Берём тот разговор, который дальше зашёл.
    """
    if _answers_count(loser) > _answers_count(winner):
        return loser.quick_state_json
    return winner.quick_state_json


def _updated(candidate) -> datetime:
    return getattr(candidate, "updated_at", None) or getattr(candidate, "created_at", None) \
        or datetime.min


def pick_stage(winner, loser) -> str:
    """Этап объединённой карточки.

    Выбор победителя решает, В КАКОЙ ЧАТ писать, и там hh важнее Авито. Этап —
    вопрос другой: это решение человека, и площадка к нему отношения не имеет.
    Без отдельного правила «отказ», поставленный руками на карточке Авито,
    терялся бы при слиянии с карточкой hh, где этап всё ещё «новый»,— и
    отказанный кандидат возвращался бы в воронку.

    Поэтому: человеческий этап побеждает автоматический; если человеческих
    два — тот, который поставили позже; если ни одного — более продвинутый
    автоматический.
    """
    w_human = winner.stage in rs.HUMAN_STAGES
    l_human = loser.stage in rs.HUMAN_STAGES
    if w_human and not l_human:
        return winner.stage
    if l_human and not w_human:
        return loser.stage
    if w_human and l_human:
        return winner.stage if _updated(winner) >= _updated(loser) else loser.stage
    return max((winner.stage, loser.stage), key=lambda st: STAGE_RANK.get(st, 0))


def _earliest(a, b):
    vals = [v for v in (a, b) if v]
    return min(vals) if vals else None


def _latest(a, b):
    vals = [v for v in (a, b) if v]
    return max(vals) if vals else None


def merge(winner, loser, reason: str, now: datetime | None = None) -> dict:
    """Перенести всё ценное с `loser` на `winner`. Строку loser НЕ удаляет —
    это делает вызывающий код после commit'а победителя.

    Возвращает запись аудита, которая уже добавлена в `winner.merged_json`.
    """
    now = now or datetime.utcnow()

    # Контакты и анкета: заполняем пустое, ничего не перетираем.
    for field in ("phone", "email", "resume_url", "photo_url", "telegram_chat_id",
                  "telegram_username", "resume_id"):
        if not (getattr(winner, field, "") or "").strip():
            value = getattr(loser, field, "") or ""
            if value:
                setattr(winner, field, value)
    if winner.age is None and loser.age is not None:
        winner.age = loser.age

    # Заметки — обе, и видно, откуда какая.
    notes = [n for n in ((winner.notes or "").strip(), (loser.notes or "").strip()) if n]
    if len(notes) == 2 and notes[0] != notes[1]:
        src_label = {"hh": "hh.ru", "avito": "Авито"}.get(loser.source, loser.source or "?")
        winner.notes = f"{notes[0]}\n\n— из объединённого отклика ({src_label}) —\n{notes[1]}"
    elif notes:
        winner.notes = notes[0]

    # Опрос — тот разговор, который дальше зашёл.
    winner.quick_state_json = _pick_state(winner, loser)
    # Этап — по своему правилу, см. pick_stage: победа в выборе канала не
    # даёт права затирать решение человека, принятое на другой карточке.
    winner.stage = pick_stage(winner, loser)

    # Переписка: показываем последнее по времени из обеих.
    if (loser.last_message_at or datetime.min) > (winner.last_message_at or datetime.min):
        winner.last_message_text = loser.last_message_text
        winner.last_message_at = loser.last_message_at
        winner.last_message_from = loser.last_message_from

    # Прозвон. Журнал append-only — склеиваем и сортируем по времени;
    # счётчик попыток берём больший, иначе слияние подарило бы кандидату
    # лишние попытки дозвона.
    log = (winner.call_log() or []) + (loser.call_log() or [])
    if log:
        log.sort(key=lambda e: str(e.get("at") or ""))
        winner.call_log_json = json.dumps(log, ensure_ascii=False)
    winner.follow_up_count = max(winner.follow_up_count or 0, loser.follow_up_count or 0)
    winner.follow_up_last_sent_at = _latest(winner.follow_up_last_sent_at,
                                            loser.follow_up_last_sent_at)
    winner.last_inbound_handled_at = _latest(winner.last_inbound_handled_at,
                                             loser.last_inbound_handled_at)
    # Раньше из двух назначенных времён — обещание кандидату, которое
    # нельзя потерять.
    winner.next_attempt_at = _earliest(winner.next_attempt_at, loser.next_attempt_at)

    # Пауза заразна: если человека попросили не беспокоить в одном из
    # откликов, это про человека, а не про отклик.
    winner.is_paused = bool(winner.is_paused or loser.is_paused)
    winner.has_unread_hh_msg = int(bool(winner.has_unread_hh_msg or loser.has_unread_hh_msg))

    # Дата отклика — самая ранняя: возраст карточки должен считаться от
    # первого обращения человека, а не от того отклика, который выжил.
    if _created(loser) < _created(winner):
        winner.created_at = loser.created_at

    winner.channels_json = json.dumps(_merge_channels(winner, loser, now), ensure_ascii=False)

    entry = {
        "at": now.isoformat(),
        "candidate_id": getattr(loser, "id", None),
        "source": loser.source or "",
        "external_id": loser.external_id or "",
        "platform_chat_id": loser.platform_chat_id or "",
        "name": loser.name or "",
        "stage": loser.stage or "",
        "created_at": loser.created_at.isoformat() if loser.created_at else None,
        "reason": reason,
    }
    winner.merged_json = json.dumps((winner.merged_from() or []) + [entry], ensure_ascii=False)
    return entry


def describe(candidate) -> str:
    """Короткая подпись для уведомлений и логов."""
    merged = candidate.merged_from() or []
    if not merged:
        return ""
    labels = {"hh": "hh.ru", "avito": "Авито"}
    srcs = [labels.get(m.get("source"), m.get("source") or "?") for m in merged]
    return f"объединено откликов: {len(merged) + 1} ({', '.join(srcs)})"


# ── поиск по переписке ───────────────────────────────────────────────────

def find_by_chat(db, source: str, chat_id: str):
    """Кандидат, которому принадлежит этот чат: основной канал или один из
    дополнительных. Возвращает (candidate, is_primary).

    Второе значение важно для вебхуков: в основном канале идёт опрос и
    входящее надо подать в него, а сообщение из дополнительного чата — это
    тот же человек, но в другой переписке, и опрос там не ведётся.
    """
    from app.models.recruitment import Candidate

    chat_id = (chat_id or "").strip()
    if not chat_id:
        return None, False

    primary = db.query(Candidate).filter(
        Candidate.source == source,
        Candidate.platform_chat_id == chat_id,
    ).first()
    if primary is not None:
        return primary, True

    # LIKE по JSON — грубо, но это лишь предварительный отбор: точное
    # совпадение проверяется разбором. Кандидатов с дополнительными
    # каналами единицы, полный скан таблицы тут ни к чему.
    for c in db.query(Candidate).filter(
            Candidate.channels_json.isnot(None),
            Candidate.channels_json.like(f"%{chat_id}%")).all():
        for ch in c.channels():
            if ch.get("source") == source and ch.get("platform_chat_id") == chat_id:
                return c, False
    return None, False


def channel_by_key(candidate, key: str) -> dict | None:
    """Канал карточки по ключу «source:external_id». Пустой ключ — основной."""
    primary = {
        "source": candidate.source or "",
        "external_id": candidate.external_id or "",
        "platform_chat_id": candidate.platform_chat_id or "",
        "primary": True,
    }
    if not key or key == channel_key(primary):
        return primary
    for ch in candidate.channels():
        if channel_key(ch) == key:
            return {**ch, "primary": False}
    return None


def channel_key(channel: dict) -> str:
    return f"{channel.get('source', '')}:{channel.get('external_id', '')}"
