from datetime import datetime, timedelta
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import RedirectResponse

log = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recruitment import Candidate, KnowledgeBaseEntry, RecruitmentSource, Vacancy, VacancyLink
from app.settings import settings

from .dependencies import require_permission


def _hh_creds() -> tuple[str, str]:
    return settings.hh_client_id, settings.hh_client_secret



# Stored in-process during the brief OAuth redirect roundtrip (seconds)
_pending_hh_redirect_uri: str = ""

router = APIRouter(
    prefix="/recruitment",
    tags=["Recruitment"],
    dependencies=[Depends(require_permission("employees"))],
)

from app.services.recruitment_stages import STAGES as VALID_STAGES  # noqa: E402
VALID_SOURCES = ["hh", "avito", "manual", "other"]


# ── Pydantic schemas ───────────────────────────────────────────────

class VacancyCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    is_open: bool = True
    quick_mode_enabled: bool = True
    quick_questions: Optional[List[str]] = None

class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_open: Optional[bool] = None
    quick_mode_enabled: Optional[bool] = None
    quick_questions: Optional[List[str]] = None


class CandidateCreate(BaseModel):
    vacancy_id: int
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = "manual"
    stage: Optional[str] = "новый"
    notes: Optional[str] = ""
    age: Optional[int] = None
    resume_url: Optional[str] = ""
    photo_url: Optional[str] = ""

class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    stage: Optional[str] = None
    notes: Optional[str] = None
    vacancy_id: Optional[int] = None
    age: Optional[int] = None
    resume_url: Optional[str] = None
    photo_url: Optional[str] = None
    rejection_message: Optional[str] = None
    hh_message: Optional[str] = None

class NoAnswerRequest(BaseModel):
    """Не дозвонились. По умолчанию пишем кандидату сами."""
    send_message: bool = True
    text: Optional[str] = None

class CallOutcomeRequest(BaseModel):
    """Результат звонка из режима «Прозвон»."""
    outcome: str
    # Только для outcome="later": локальное время следующего звонка.
    next_at: Optional[datetime] = None
    send_message: bool = True
    text: Optional[str] = None


class CallHoursRequest(BaseModel):
    enabled: bool = False
    days: List[int] = []
    start: str = "10:00"
    end: str = "20:00"


class HHIntervalRequest(BaseModel):
    sync_interval_minutes: int = 15

class AvitoConnectRequest(BaseModel):
    client_id: str
    client_secret: str
    sync_interval_minutes: Optional[int] = 15

class LinkCreate(BaseModel):
    vacancy_id: int
    source: str
    external_vacancy_id: str
    external_vacancy_title: Optional[str] = ""

class LinkUpdate(BaseModel):
    sync_enabled: Optional[bool] = None
    external_vacancy_id: Optional[str] = None
    external_vacancy_title: Optional[str] = None

class SendMessageRequest(BaseModel):
    text: str


def _serialize_questions(questions: Optional[List[str]]) -> Optional[str]:
    """Список вопросов быстрого режима → значение quick_questions_json,
    пустые строки отбрасываются."""
    import json

    if questions is None:
        return None
    cleaned = [q.strip() for q in questions if q.strip()]
    return json.dumps(cleaned, ensure_ascii=False)


# ── Vacancies ──────────────────────────────────────────────────────

@router.get("/vacancies")
def list_vacancies(include_closed: bool = Query(False), db: Session = Depends(get_db)):
    q = db.query(Vacancy)
    if not include_closed:
        q = q.filter(Vacancy.is_open == True)
    result = []
    for v in q.order_by(Vacancy.created_at.desc()).all():
        d = v.to_dict()
        d["candidate_count"] = len(v.candidates)
        result.append(d)
    return result

@router.post("/vacancies")
def create_vacancy(data: VacancyCreate, db: Session = Depends(get_db)):
    v = Vacancy(title=data.title, description=data.description, is_open=data.is_open,
                quick_mode_enabled=data.quick_mode_enabled,
                quick_questions_json=_serialize_questions(data.quick_questions))
    db.add(v); db.commit(); db.refresh(v)
    return v.to_dict()

@router.patch("/vacancies/{vacancy_id}")
def update_vacancy(vacancy_id: int, data: VacancyUpdate, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(404, "Vacancy not found")
    if data.title is not None: v.title = data.title
    if data.description is not None: v.description = data.description
    if data.is_open is not None: v.is_open = data.is_open
    if data.quick_mode_enabled is not None:
        v.quick_mode_enabled = data.quick_mode_enabled
    if data.quick_questions is not None:
        v.quick_questions_json = _serialize_questions(data.quick_questions)
    db.commit(); db.refresh(v)
    return v.to_dict()

@router.delete("/vacancies/{vacancy_id}")
def delete_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v: raise HTTPException(404, "Vacancy not found")
    # The model declares ondelete="CASCADE" on KnowledgeBaseEntry.vacancy_id,
    # but SQLite only enforces FK actions when PRAGMA foreign_keys=ON for the
    # connection, which this app never sets — so that CASCADE is inert and a
    # deleted vacancy silently leaves its scoped KB entries orphaned (found
    # via a real 12-row orphan set from earlier deleted vacancies). Delete
    # them explicitly instead of relying on a constraint that isn't active.
    db.query(KnowledgeBaseEntry).filter(
        KnowledgeBaseEntry.scope == "vacancy", KnowledgeBaseEntry.vacancy_id == vacancy_id
    ).delete()
    db.delete(v); db.commit()
    return {"status": "deleted"}

@router.post("/vacancies/{vacancy_id}/duplicate")
def duplicate_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    """Копия вакансии с её вопросами для быстрого режима — чтобы повторная
    публикация не требовала вводить всё заново."""
    src = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not src: raise HTTPException(404, "Vacancy not found")

    new_title = src.title if src.is_open else f"{src.title} (копия)"
    v = Vacancy(
        title=new_title,
        description=src.description,
        is_open=True,
        quick_mode_enabled=src.quick_mode_enabled,
        quick_questions_json=src.quick_questions_json,
    )
    db.add(v); db.commit(); db.refresh(v)

    d = v.to_dict()
    d["candidate_count"] = 0
    return d


@router.get("/candidates")
def list_candidates(
    vacancy_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Candidate)
    if vacancy_id is not None: q = q.filter(Candidate.vacancy_id == vacancy_id)
    # Новые сверху: воронку смотрят, чтобы разобрать свежие отклики, а при
    # старом порядке (asc) они оказывались в самом низу колонки — под сотней
    # уже обработанных.
    candidates = q.order_by(Candidate.created_at.desc()).all()

    from app.services import quick_screening, recruitment_stages as rs

    since_24h = datetime.utcnow() - timedelta(hours=24)
    now = datetime.utcnow()
    # Вопросы кэшируем по вакансии: их парсинг из JSON одинаков для всех
    # кандидатов одной вакансии, а список может быть длинным.
    questions_by_vacancy: dict[int, list] = {}

    result = []
    for c in candidates:
        d = c.to_dict()
        if c.vacancy_id not in questions_by_vacancy:
            questions_by_vacancy[c.vacancy_id] = quick_screening.get_questions(c.vacancy)
        questions = questions_by_vacancy[c.vacancy_id]

        state = quick_screening.load_state(c)
        # Этап считается от состояния опроса, а не читается из БД: так карточка
        # не может разойтись с реальным ходом переписки. Ручные этапы
        # (собеседование/нанят/отказ) при этом сохраняются как есть.
        d["stage"] = rs.derive_stage(c.stage, state)
        d["flags"] = _candidate_flags(c, state, now)
        d["progress"] = rs.progress(state, questions)
        d["answers"] = state.get("answers") or []
        d["is_new"] = bool(c.created_at and c.created_at >= since_24h)
        d["vacancy_title"] = c.vacancy.title if c.vacancy else ""
        result.append(d)

    if stage:
        # Фильтр по этапу применяем уже к вычисленному значению, иначе он бы
        # работал по устаревшему полю в БД.
        result = [d for d in result if d["stage"] == stage]
    return result

@router.post("/candidates")
def create_candidate(data: CandidateCreate, db: Session = Depends(get_db)):
    if data.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Valid: {VALID_STAGES}")
    if not db.query(Vacancy).filter(Vacancy.id == data.vacancy_id).first():
        raise HTTPException(404, "Vacancy not found")
    c = Candidate(
        vacancy_id=data.vacancy_id, name=data.name,
        phone=data.phone or "", email=data.email or "",
        source=data.source or "manual", stage=data.stage or "новый",
        notes=data.notes or "", age=data.age,
        resume_url=data.resume_url or "",
        photo_url=data.photo_url or "",
    )
    db.add(c); db.commit(); db.refresh(c)
    return c.to_dict()

@router.patch("/candidates/{candidate_id}")
async def update_candidate(candidate_id: int, data: CandidateUpdate, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c: raise HTTPException(404, "Candidate not found")
    if data.stage is not None and data.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Valid: {VALID_STAGES}")

    old_stage = c.stage

    for field in ("name", "phone", "email", "source", "stage", "notes", "vacancy_id",
                  "age", "resume_url", "photo_url"):
        val = getattr(data, field)
        if val is not None: setattr(c, field, val)
    c.updated_at = datetime.utcnow()
    db.commit(); db.refresh(c)

    warnings: list[str] = []

    # Отказ на Авито. У hh отказ — это действие в API отклика, и текст уходит
    # вместе с ним (см. ниже sync_negotiation_stage). У Авито такого действия
    # нет вовсе, есть только переписка — поэтому раньше кандидат с Авито
    # просто молча исчезал из воронки, хотя текст отказа рекрутёр вводил.
    # Теперь текст доходит по единственному доступному каналу — в чат.
    if (
        data.stage == "отказ" and data.stage != old_stage
        and c.source == "avito"
        and (data.rejection_message or "").strip()
    ):
        from app.services import candidate_outreach as outreach
        if not outreach.has_chat(c):
            warnings.append("Отказ сохранён, но написать кандидату некуда — у отклика нет чата на Авито.")
        else:
            try:
                _, src_row, token = await _get_platform_chat(candidate_id, db)
                await outreach.send_to_candidate(db, c, src_row, token, data.rejection_message)
            except HTTPException as exc:
                warnings.append(f"Отказ сохранён, но сообщение не отправлено: {exc.detail}")
            except Exception as exc:
                log.warning("avito rejection message failed for candidate %s: %s", candidate_id, exc)
                warnings.append(f"Отказ сохранён, но сообщение не отправлено: {exc}")

    # Push stage change to hh.ru when applicable
    if (
        data.stage and data.stage != old_stage
        and c.source == "hh"
        and c.external_id
    ):
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if src and src.access_token:
            try:
                from app.services import hh_api
                await hh_api.sync_negotiation_stage(
                    src.access_token, c.external_id, data.stage,
                    rejection_message=data.rejection_message or None,
                    hh_message=data.hh_message or None,
                )
            except Exception as exc:
                log.warning("hh stage sync failed for candidate %s: %s", candidate_id, exc)

    result = c.to_dict()
    if warnings:
        result["warnings"] = warnings
    return result


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c: raise HTTPException(404, "Candidate not found")
    db.delete(c); db.commit()
    return {"status": "deleted"}


@router.post("/candidates/{candidate_id}/reset-history")
def reset_candidate_history(candidate_id: int, db: Session = Depends(get_db)):
    """Сбросить опрос кандидата, чтобы бот начал его заново."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")

    c.quick_state_json = None
    c.stage = "новый"
    c.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@router.post("/candidates/{candidate_id}/no-answer")
async def register_no_answer(candidate_id: int, data: NoAnswerRequest,
                             db: Session = Depends(get_db)):
    """Не дозвонились: зафиксировать попытку и (по умолчанию) написать в чат.

    Попытка засчитывается всегда, даже если писать некуда или отправка не
    удалась: те, кому звонят, — как раз чаще всего отклики «только телефон»,
    и терять из-за них учёт звонков нельзя. Поэтому ответ отдельно сообщает,
    ушло сообщение или нет.
    """
    from app.services import candidate_outreach as outreach

    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")

    warning = None
    message_sent = False

    # Здесь, в отличие от режима «Прозвон», send_message выполняется как
    # сказано: это ручное действие оператора с карточки, он видит текст и
    # решает сам. Правило «пишем только после первого недозвона» —
    # про автоматическое поведение очереди, а не про явное нажатие кнопки.
    if data.send_message:
        if not outreach.has_chat(c):
            warning = "Попытка записана. Переписки с этим кандидатом нет — только телефон."
        else:
            try:
                _, src, token = await _get_platform_chat(candidate_id, db)
                await outreach.send_to_candidate(
                    db, c, src, token,
                    (data.text or "").strip() or outreach.DEFAULT_NO_ANSWER_MESSAGE,
                )
                message_sent = True
            except HTTPException as exc:
                warning = f"Попытка записана, но сообщение не отправлено: {exc.detail}"
            except Exception as exc:
                log.warning("no-answer message failed for candidate %s: %s", candidate_id, exc)
                warning = f"Попытка записана, но сообщение не отправлено: {exc}"

    # Счётчик, расписание следующей попытки и журнал — через общую точку,
    # чтобы канбан и «Прозвон» не разошлись в правилах.
    result = outreach.record_outcome(
        db, c, outreach.OUTCOME_NO_ANSWER, message_sent=message_sent)
    result["message_sent"] = message_sent
    result["warning"] = warning
    return result


@router.post("/candidates/{candidate_id}/reached")
def register_reached(candidate_id: int, db: Session = Depends(get_db)):
    """Дозвонились — снять счётчик недозвонов и флаг с карточки."""
    from app.services import candidate_outreach as outreach

    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    return outreach.record_outcome(db, c, outreach.OUTCOME_REACHED)


# ─── Режим «Прозвон» ────────────────────────────────────────────────────────
#
# Очередь нигде не хранится: она вычисляется предикатом call_queue.is_callable
# на каждый запрос — ровно как этап кандидата вычисляется из состояния опроса.
# Поэтому у режима нет ни одной фоновой задачи: наступление next_attempt_at —
# это сравнение с now внутри вот этого обработчика.


def _candidate_flags(c: Candidate, state: dict, now: datetime | None = None) -> list:
    """Флаги карточки. Вынесено, чтобы список и очередь считали их одинаково."""
    from app.services import call_queue
    from app.services import recruitment_stages as rs

    return rs.flags(
        state,
        now=now or datetime.utcnow(),
        call_attempts=c.follow_up_count or 0,
        last_call_at=c.follow_up_last_sent_at,
        awaiting_reply=call_queue.unhandled_inbound(c),
    )


def _queue_rows(db: Session, now=None):
    """(кандидат, этап, причина, ключ сортировки) для всех, кому нужен звонок."""
    from app.services import call_hours, call_queue, quick_screening
    from app.services import recruitment_stages as rs
    from app.services.hours_window import local_now

    now = now or local_now()
    rows = []
    # Закрытая вакансия убирает кандидата из очереди, но оставляет в канбане:
    # звонить по набору, который уже закрыт, незачем.
    candidates = (
        db.query(Candidate)
        .join(Vacancy, Candidate.vacancy_id == Vacancy.id)
        .filter(Vacancy.is_open.is_(True))
        .all()
    )
    for c in candidates:
        state = quick_screening.load_state(c)
        stage = rs.derive_stage(c.stage, state)
        quick_mode = bool(c.vacancy and c.vacancy.quick_mode_enabled)
        if not call_queue.is_callable(c, stage, now, call_hours, quick_mode):
            continue
        _, reason = call_queue.priority(c, now)
        rows.append((c, stage, reason, call_queue.sort_key(c, now)))
    rows.sort(key=lambda r: r[3])
    return rows


async def _queue_card(db: Session, c: Candidate, stage: str, reason: str) -> dict:
    """Полный контекст кандидата для экрана: рекрутёр не должен собирать его
    сам, переключаясь между очередью и канбаном."""
    from app.services import candidate_outreach as outreach
    from app.services import quick_screening
    from app.services import recruitment_stages as rs
    from app.services.task_service import get_task_service

    state = quick_screening.load_state(c)
    d = c.to_dict()
    d["stage"] = stage
    d["reason"] = reason
    d["answers"] = state.get("answers") or []
    d["progress"] = rs.progress(state, quick_screening.get_questions(c.vacancy))
    d["vacancy_title"] = c.vacancy.title if c.vacancy else ""
    d["has_chat"] = outreach.has_chat(c)
    d["flags"] = _candidate_flags(c, state)

    # Связанная задача — чтобы рекрутёр не переключался в «Задачи» проверять,
    # не назначено ли на этого кандидата напоминание.
    tasks = await get_task_service().list_tasks(candidate_id=c.id, include_done=False)
    d["linked_task"] = tasks[0].model_dump(mode="json") if tasks else None
    return d


def _awaiting_reply_rows(db: Session):
    """Кандидаты, которые написали и ждут текстового ответа.

    Терминальные этапы отсеиваются: нанятому и отправленному в резерв мы
    ничего не должны, а без фильтра они раздували счётчик — на боевой базе
    из 42 таких оказалось 8.
    """
    from app.services import call_queue, quick_screening
    from app.services import recruitment_stages as rs

    rows = []
    for c in db.query(Candidate).all():
        if not call_queue.unhandled_inbound(c):
            continue
        state = quick_screening.load_state(c)
        stage = rs.derive_stage(c.stage, state)
        if stage in rs.TERMINAL_STAGES:
            continue
        rows.append((c, stage, state))
    # Свежие сверху: на сообщение, написанное час назад, ответ ещё ждут.
    rows.sort(key=lambda r: r[0].last_message_at or datetime.min, reverse=True)
    return rows


def _upcoming_attempt(db: Session, now) -> datetime | None:
    """Когда в очереди появится следующий кандидат.

    Нужно для пустого экрана: «все обзвонены» без ответа на «а дальше что»
    оставляет рекрутера гадать, заходить ли через час.
    """
    from app.services import call_queue, quick_screening
    from app.services import recruitment_stages as rs

    best = None
    candidates = (
        db.query(Candidate)
        .join(Vacancy, Candidate.vacancy_id == Vacancy.id)
        .filter(Vacancy.is_open.is_(True))
        .filter(Candidate.next_attempt_at.isnot(None))
        .all()
    )
    for c in candidates:
        when = c.next_attempt_at
        if when is None or when <= now:
            continue
        state = quick_screening.load_state(c)
        stage = rs.derive_stage(c.stage, state)
        quick_mode = bool(c.vacancy and c.vacancy.quick_mode_enabled)
        # Тот же предикат, но в момент назначенного времени: кандидат с
        # исчерпанными попытками или на паузе там не появится.
        if not call_queue.is_callable(c, stage, when, call_hours_module(), quick_mode):
            continue
        if best is None or when < best:
            best = when
    return best


def call_hours_module():
    from app.services import call_hours

    return call_hours


@router.get("/call-queue")
async def call_queue_view(db: Session = Depends(get_db)):
    """Очередь звонков: следующий кандидат и счётчики для шапки."""
    from app.services import call_hours, call_queue
    from app.services.hours_window import local_now

    now = local_now()
    rows = _queue_rows(db, now)

    # «Звонков сегодня» — именно исходящие попытки, а не «обработано»:
    # обработать карточку можно и сообщением, и переводом этапа. Считаем по
    # журналу, потому что состоявшийся разговор не трогает счётчик недозвонов
    # и иначе не попал бы в цифру вовсе.
    calls_today = sum(call_queue.calls_made_today(c, now)
                      for c in db.query(Candidate).all())
    awaiting = _awaiting_reply_rows(db)

    next_card = None
    if rows:
        c, stage, reason, _ = rows[0]
        next_card = await _queue_card(db, c, stage, reason)

    within = call_hours.is_within(now)
    schedule = call_hours.load_schedule()
    upcoming_window = None if within else call_hours.next_window_start(now)
    # Выходной отличается от «рано/поздно»: формулировка на экране разная,
    # и определить его можно только по списку рабочих дней.
    is_day_off = bool(schedule["enabled"]) and now.isoweekday() not in schedule["days"]

    return {
        "next": next_card,
        "queue_count": len(rows),
        "calls_today": calls_today,
        "awaiting_reply_count": len(awaiting),
        "within_call_hours": within,
        "is_day_off": is_day_off,
        "next_window_start": upcoming_window.isoformat() if upcoming_window else None,
        "next_candidate_at": (
            _upcoming_attempt(db, now).isoformat()
            if within and not rows and _upcoming_attempt(db, now) else None
        ),
    }


@router.get("/awaiting-reply")
def awaiting_reply_list(db: Session = Depends(get_db)):
    """Кандидаты, ждущие ответа в переписке.

    Отдельный список, а не очередь: этим людям нужен текст, а не звонок, и
    смешивать их с «Прозвоном» было бы ровно той ошибкой, ради исправления
    которой их и разделили.
    """
    from app.services import quick_screening

    result = []
    for c, stage, state in _awaiting_reply_rows(db):
        d = c.to_dict()
        d["stage"] = stage
        d["vacancy_title"] = c.vacancy.title if c.vacancy else ""
        d["flags"] = _candidate_flags(c, state)
        d["progress"] = rs_progress(state, quick_screening.get_questions(c.vacancy))
        result.append(d)
    return result


def rs_progress(state, questions):
    from app.services import recruitment_stages as rs

    return rs.progress(state, questions)


@router.post("/candidates/{candidate_id}/call-outcome")
async def call_outcome(candidate_id: int, data: CallOutcomeRequest,
                       db: Session = Depends(get_db)):
    """Применить результат звонка.

    Сообщение уходит только после ПЕРВОГО недозвона: второе и третье такое же
    подряд выглядит как автоответчик, а кандидат на него уже не отреагировал.
    Попытка при этом засчитывается всегда — даже если писать некуда (отклик
    «только телефон») или отправка не удалась.
    """
    from app.services import candidate_outreach as outreach

    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if data.outcome not in outreach.OUTCOMES:
        raise HTTPException(400, f"Неизвестный результат звонка: {data.outcome}")
    if data.outcome == outreach.OUTCOME_LATER and not data.next_at:
        raise HTTPException(400, "Для «перезвонить позже» нужно указать время")

    # Правила очереди защищены здесь, а не только предикатом на чтении: без
    # этого двойной клик, зависший запрос или повторная отправка формы
    # засчитывали вторую попытку за день и уводили счётчик за три. Ровно эти
    # три отказа — та же логика, по которой кандидат не показывается в
    # очереди, просто применённая к записи.
    #
    # Ручной путь с карточки канбана (/no-answer) сюда не попадает намеренно:
    # там человек осознанно решает позвонить второй раз, и запрещать ему
    # нельзя — так и было согласовано.
    from app.services import call_queue
    from app.services import recruitment_stages as rs
    from app.services.hours_window import local_now

    if data.outcome == outreach.OUTCOME_NO_ANSWER:
        if call_queue.called_today(c, local_now()):
            raise HTTPException(
                409, "Сегодня этому кандидату уже звонили — следующая попытка "
                     "будет доступна завтра.")
        if not call_queue.attempts_left(c):
            raise HTTPException(
                409, "Все три попытки дозвона использованы. Кандидат помечен "
                     "как «не вышел на связь» — нужно решение, а не звонок.")
    if rs.derive_stage(c.stage, None) in rs.TERMINAL_STAGES:
        raise HTTPException(
            409, f"Кандидат уже на этапе «{c.stage}» — результат звонка "
                 f"для него не записывается.")

    warning = None
    message_sent = False
    first_attempt = (c.follow_up_count or 0) == 0

    if data.outcome == outreach.OUTCOME_NO_ANSWER and data.send_message and first_attempt:
        if not outreach.has_chat(c):
            warning = "Попытка записана. Переписки с этим кандидатом нет — только телефон."
        else:
            try:
                _, src, token = await _get_platform_chat(candidate_id, db)
                await outreach.send_to_candidate(
                    db, c, src, token,
                    (data.text or "").strip() or outreach.DEFAULT_NO_ANSWER_MESSAGE,
                )
                message_sent = True
            except HTTPException as exc:
                warning = f"Попытка записана, но сообщение не отправлено: {exc.detail}"
            except Exception as exc:
                log.warning("call-outcome message failed for candidate %s: %s",
                            candidate_id, exc)
                warning = f"Попытка записана, но сообщение не отправлено: {exc}"

    result = outreach.record_outcome(
        db, c, data.outcome, next_at=data.next_at, message_sent=message_sent)
    result["message_sent"] = message_sent
    result["warning"] = warning

    # «Перезвонить позже» — договорённость с человеком, поэтому она попадает
    # ещё и в список дел рекрутера. Тем же путём, что и время, названное самим
    # кандидатом: одна категория, один reminder_minutes, связь по candidate_id.
    # Недозвон задачу НЕ создаёт — системный перенос живёт только в
    # next_attempt_at и засорять список дел не должен.
    if data.outcome == outreach.OUTCOME_LATER and data.next_at:
        result["task"] = await _create_call_task(c, data.next_at)

    return result


async def _create_call_task(c: Candidate, when: datetime) -> Optional[dict]:
    """Задача-напоминание о звонке. Ошибка здесь не должна ронять результат:
    исход звонка уже записан, и терять его из-за списка дел нельзя."""
    from app.schemas.task import TaskCreate
    from app.services.task_service import get_task_service

    try:
        task = await get_task_service().create_task(
            TaskCreate(
                title=f"Позвонить: {c.name}",
                description=(f"Договорились созвониться "
                             f"{when.strftime('%d.%m в %H:%M')}."),
                due_date=when.date(), due_time=when.time().replace(second=0,
                                                                   microsecond=0),
                category="Подбор персонала",
                priority="high",
                reminder_minutes=15,
                candidate_id=c.id,
            ),
            created_by="Прозвон",
        )
        return task.model_dump(mode="json")
    except Exception as exc:
        log.warning("не удалось создать задачу на звонок для кандидата %s: %s",
                    c.id, exc)
        return None


@router.post("/candidates/{candidate_id}/call-outcome/undo")
def call_outcome_undo(candidate_id: int, db: Session = Depends(get_db)):
    """Откатить последний результат.

    Отправленное кандидату сообщение не отзывается — площадки этого не умеют.
    Флаг message_not_recalled в ответе для того и нужен, чтобы интерфейс сказал
    это прямо, а не сделал вид, что откат полный.
    """
    from app.services import candidate_outreach as outreach

    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    try:
        return outreach.undo_last_outcome(db, c)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _call_hours_state() -> dict:
    """Расписание + «а что сейчас». Состояние отдаём вместе с настройкой,
    потому что настраивают её ровно тогда, когда хотят понять, почему
    очередь молчит."""
    from app.services import call_hours
    from app.services.hours_window import local_now

    now = local_now()
    upcoming = call_hours.next_window_start(now)
    return {
        **call_hours.load_schedule(),
        "within_now": call_hours.is_within(now),
        "next_window_start": upcoming.isoformat() if upcoming else None,
    }


@router.get("/call-hours")
def get_call_hours():
    """Окно звонков. Отдельное от часов общения бота: писать в чат можно с
    девяти утра, а звонить в девять уже неловко."""
    return _call_hours_state()


@router.put("/call-hours")
def put_call_hours(data: CallHoursRequest):
    from app.services import call_hours
    from app.services.config_service import ConfigService

    days = []
    for raw in data.days:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 7:
            days.append(n)

    ConfigService().patch({
        call_hours.CFG_ENABLED: bool(data.enabled),
        call_hours.CFG_DAYS: sorted(set(days)),
        call_hours.CFG_START: data.start,
        call_hours.CFG_END: data.end,
    })
    return _call_hours_state()


@router.post("/candidates/{candidate_id}/toggle-pause")
def toggle_pause(candidate_id: int, db: Session = Depends(get_db)):
    """Pause or unpause AI automation for this candidate."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.is_paused = not bool(c.is_paused)
    c.updated_at = datetime.utcnow()
    db.commit()
    return {"id": c.id, "is_paused": bool(c.is_paused)}


@router.get("/interviews")
async def list_interviews(db: Session = Depends(get_db)):
    """Return candidates at 'собеседование' stage with their interview task details."""
    from app.services.task_service import get_task_service

    candidates = db.query(Candidate).filter(
        Candidate.stage == "собеседование"
    ).order_by(Candidate.updated_at.desc()).all()

    try:
        tasks = await get_task_service().list_tasks(category="Подбор персонала")
    except Exception:
        tasks = []

    result = []
    for c in candidates:
        task = next((t for t in tasks if c.name in (t.title or "") and not (t.status == "done")), None)
        entry = c.to_dict()
        entry["interview_date"] = task.due_date if task else None
        entry["interview_time"] = task.due_time if task else None
        raw_desc = (task.description or "") if task else ""
        entry["interview_place"] = raw_desc.replace("📍 Место: ", "").strip() or None
        result.append(entry)
    return result


async def _get_platform_chat(candidate_id: int, db):
    """Resolve a candidate to (candidate, source_row, token) for reading or
    writing their chat on whichever job board they came from.

    Avito needs a freshly-minted token (client_credentials, 24h) rather than a
    stored one, so it is fetched here instead of relying on whatever the last
    sync happened to leave in the row.
    """
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if c.source not in ("hh", "avito"):
        raise HTTPException(400, "Переписка доступна только для откликов с hh.ru или Авито")

    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == c.source).first()
    if not src:
        raise HTTPException(400, f"{c.source} не подключён")

    if c.source == "hh":
        if not c.external_id:
            raise HTTPException(400, "У отклика нет идентификатора переписки hh.ru")
        if not src.access_token:
            raise HTTPException(400, "hh.ru не подключён")
        return c, src, src.access_token

    if not (c.platform_chat_id or "").strip():
        raise HTTPException(400, "У этого отклика нет чата на Авито (кандидат оставил только телефон)")
    if not (src.client_id and src.client_secret):
        raise HTTPException(400, "Авито не подключён — не заданы ключи API")
    from app.services import avito_api
    try:
        token = (await avito_api.get_token(src.client_id, src.client_secret))["access_token"]
    except Exception as exc:
        raise HTTPException(502, f"Авито: не удалось получить токен ({exc})")
    return c, src, token


@router.get("/candidates/{candidate_id}/messages")
async def get_candidate_messages(candidate_id: int, db: Session = Depends(get_db)):
    c, src, token = await _get_platform_chat(candidate_id, db)
    # Clear unread flag when admin opens the chat
    if getattr(c, 'has_unread_hh_msg', False):
        try:
            c.has_unread_hh_msg = False
            db.commit()
        except Exception:
            pass
    from app.services import hh_api, avito_api
    try:
        if c.source == "avito":
            # Normalised to the same shape as hh so the UI renders one list.
            return await avito_api.get_messages(token, src.employer_id, c.platform_chat_id)
        return await hh_api.get_messages(token, c.external_id)
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Ошибка {'Авито' if c.source == 'avito' else 'hh.ru'}: {exc}")


@router.post("/candidates/{candidate_id}/messages")
async def send_candidate_message(candidate_id: int, data: SendMessageRequest, db: Session = Depends(get_db)):
    if not data.text.strip():
        raise HTTPException(400, "Текст сообщения не может быть пустым")
    c, src, token = await _get_platform_chat(candidate_id, db)
    from app.services import hh_api, avito_api
    try:
        if c.source == "avito":
            return await avito_api.send_message(token, src.employer_id, c.platform_chat_id, data.text.strip())
        return await hh_api.send_message(token, c.external_id, data.text.strip())
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Ошибка {'Авито' if c.source == 'avito' else 'hh.ru'}: {exc}")


# ── Quick screening (быстрый режим) for a single candidate ─────────

@router.get("/candidates/{candidate_id}/quick-screening")
def get_quick_screening(candidate_id: int, db: Session = Depends(get_db)):
    """Current screening state for the candidate card."""
    from app.services import quick_screening

    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
    state = quick_screening.load_state(c)
    questions = quick_screening.get_questions(vacancy)
    return {
        "status": state.get("status"),          # None = не запущен
        "phase": state.get("phase", "questions") if state else None,
        "idx": state.get("idx", 0),
        "answers": state.get("answers") or [],
        "questions": questions,
        "can_start": bool(questions) and not state and c.source in ("hh", "avito"),
        "vacancy_quick_mode": bool(vacancy and vacancy.quick_mode_enabled),
    }


@router.post("/candidates/{candidate_id}/quick-screening")
async def start_quick_screening(candidate_id: int, db: Session = Depends(get_db)):
    """Start the screen for this one candidate, regardless of whether the
    vacancy's quick-mode toggle is on — that toggle only governs whether new
    responses start one automatically. Requires the vacancy to have questions."""
    from app.services import quick_screening

    c, src, token = await _get_platform_chat(candidate_id, db)
    vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
    if not quick_screening.get_questions(vacancy):
        raise HTTPException(400, "У вакансии не заданы вопросы быстрого режима — заполните их в карточке вакансии.")
    if quick_screening.load_state(c):
        raise HTTPException(400, "Опрос по этому кандидату уже запущен.")

    ok = await quick_screening.start_screening(db, c, vacancy, src, token)
    if not ok:
        raise HTTPException(502, "Не удалось начать опрос — подробности в уведомлении.")
    return {"status": "started"}


# ── Integration sources ────────────────────────────────────────────

@router.get("/integrations")
def list_integrations(db: Session = Depends(get_db)):
    sources = db.query(RecruitmentSource).all()
    src_map = {s.source: s.to_dict() for s in sources}
    result = []
    for source_key, configured in [
        ("hh",    bool(settings.hh_client_id and settings.hh_client_secret)),
        ("avito", True),  # Avito credentials stored in DB, always show connect button
    ]:
        entry = src_map.get(source_key, {"source": source_key, "is_active": False,
                                         "employer_name": "", "last_error": "",
                                         "sync_interval_minutes": 15})
        entry["env_configured"] = configured
        result.append(entry)
    return result


@router.get("/integrations/hh/auth-url")
async def hh_auth_url(redirect_uri: str = Query(...)):
    """Return OAuth authorization URL. Credentials come from env."""
    global _pending_hh_redirect_uri
    from app.services import hh_api

    hh_id, hh_secret = _hh_creds()
    if not hh_id or not hh_secret:
        raise HTTPException(503, "hh.ru не настроен на сервере (HH_CLIENT_ID / HH_CLIENT_SECRET)")

    _pending_hh_redirect_uri = redirect_uri
    return {"auth_url": hh_api.build_auth_url(hh_id, redirect_uri)}


@router.get("/integrations/hh/callback", include_in_schema=False)
async def hh_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Browser callback after hh.ru OAuth authorization."""
    global _pending_hh_redirect_uri
    from app.services import hh_api

    if error:
        return RedirectResponse(f"/admin/recruitment?hh_error={error}")
    if not code:
        return RedirectResponse("/admin/recruitment?hh_error=no_code")
    hh_id, hh_secret = _hh_creds()
    if not hh_id or not hh_secret:
        return RedirectResponse("/admin/recruitment?hh_error=not_configured")

    redirect_uri = _pending_hh_redirect_uri
    if not redirect_uri:
        return RedirectResponse("/admin/recruitment?hh_error=session_expired")

    try:
        token_data = await hh_api.exchange_code(hh_id, hh_secret, code, redirect_uri)
    except Exception as e:
        src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
        if src:
            src.last_error = str(e)[:500]
            db.commit()
        return RedirectResponse("/admin/recruitment?hh_error=token_exchange")

    try:
        info = await hh_api.verify_token(token_data["access_token"])
    except Exception:
        info = {"employer_id": "", "employer_name": ""}

    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
    if not src:
        src = RecruitmentSource(source="hh")
        db.add(src)

    src.access_token = token_data["access_token"]
    src.refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in")
    if expires_in:
        src.token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
    src.employer_id = info["employer_id"]
    src.employer_name = info["employer_name"]
    src.is_active = True
    src.last_error = ""
    src.updated_at = datetime.utcnow()
    db.commit()

    _pending_hh_redirect_uri = ""
    return RedirectResponse("/admin/recruitment?hh_connected=1")


@router.delete("/integrations/hh/disconnect")
def disconnect_hh(db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
    if src:
        src.is_active = False
        src.access_token = ""
        src.refresh_token = ""
        src.last_error = ""
        db.commit()
    return {"status": "disconnected"}


@router.get("/integrations/hh/vacancies")
async def hh_vacancies(db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "hh",
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        raise HTTPException(400, "hh.ru не подключён")
    from app.services import hh_api
    try:
        return await hh_api.get_vacancies(src.access_token, src.employer_id)
    except Exception as e:
        raise HTTPException(502, f"Ошибка hh.ru: {e}")


@router.post("/integrations/avito/connect")
async def connect_avito(data: AvitoConnectRequest, db: Session = Depends(get_db)):
    """Connect Avito — credentials stored in DB, no env vars needed."""
    from app.services import avito_api
    try:
        tok  = await avito_api.get_token(data.client_id, data.client_secret)
        info = await avito_api.get_user_info(tok["access_token"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Авито недоступен: {e}")

    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "avito").first()
    if not src:
        src = RecruitmentSource(source="avito")
        db.add(src)

    src.client_id    = data.client_id
    src.client_secret = data.client_secret
    src.access_token = tok["access_token"]
    src.employer_id  = info["employer_id"]
    src.employer_name = info["employer_name"]
    src.is_active    = True
    src.last_error   = ""
    src.sync_interval_minutes = max(1, data.sync_interval_minutes or 15)
    src.updated_at   = datetime.utcnow()
    db.commit(); db.refresh(src)
    return src.to_dict()


@router.delete("/integrations/avito/disconnect")
def disconnect_avito(db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "avito").first()
    if src:
        src.is_active    = False
        src.access_token = ""
        src.client_id    = ""
        src.client_secret = ""
        src.last_error   = ""
        db.commit()
    return {"status": "disconnected"}


class CandidateHoursUpdate(BaseModel):
    enabled: bool
    days: List[int]
    start: str
    end: str


@router.get("/candidate-hours")
def get_candidate_hours():
    """Расписание общения с кандидатами + признак, идут ли рабочие часы
    прямо сейчас (чтобы оператор видел, будет бот писать или молчать)."""
    from app.services import candidate_hours

    schedule = candidate_hours.load_schedule()
    nxt = candidate_hours.next_window_start()
    return {
        **schedule,
        "within_now": candidate_hours.is_within(),
        "next_window_start": nxt.isoformat() if nxt else None,
    }


@router.put("/candidate-hours")
def update_candidate_hours(data: CandidateHoursUpdate):
    from app.services import candidate_hours
    from app.services.config_service import ConfigService

    days = sorted({d for d in data.days if 1 <= d <= 7})
    if data.enabled and not days:
        raise HTTPException(400, "Выберите хотя бы один рабочий день.")
    for value in (data.start, data.end):
        try:
            hh, mm = str(value).split(":")[:2]
            if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                raise ValueError
        except Exception:
            raise HTTPException(400, f"Некорректное время: {value!r}. Формат ЧЧ:ММ.")

    ConfigService().patch({
        candidate_hours.CFG_ENABLED: bool(data.enabled),
        candidate_hours.CFG_DAYS: days,
        candidate_hours.CFG_START: data.start,
        candidate_hours.CFG_END: data.end,
    })
    return get_candidate_hours()


@router.get("/integrations/hh/webhook")
async def get_hh_webhook(db: Session = Depends(get_db)):
    """Состояние подписки hh на мгновенные уведомления о сообщениях."""
    from app.api.hh_webhook import webhook_path
    from app.services import hh_api

    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "hh", RecruitmentSource.is_active == True
    ).first()
    if not src or not src.access_token:
        raise HTTPException(400, "hh.ru не подключён")
    our_url = settings.public_base_url.rstrip("/") + webhook_path()
    try:
        subs = await hh_api.list_webhook_subscriptions(src.access_token)
    except Exception as exc:
        raise HTTPException(502, f"hh.ru: не удалось получить подписки ({exc})")
    mine = [s for s in subs if s.get("url") == our_url]
    return {"url": our_url, "subscribed": bool(mine),
            "subscription_id": (mine[0].get("id") if mine else None),
            "all_subscriptions": [s.get("url", "") for s in subs]}


@router.post("/integrations/hh/webhook")
async def subscribe_hh_webhook(db: Session = Depends(get_db)):
    """Подписаться на CHAT_MESSAGE_CREATED — ответ кандидата обрабатывается
    за секунды вместо ожидания цикла синхронизации. Опрос остаётся
    подстраховкой: hh прямо предупреждает, что доставка не гарантируется."""
    from app.api.hh_webhook import webhook_path, EVENT_NEW_MESSAGE
    from app.services import hh_api

    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "hh", RecruitmentSource.is_active == True
    ).first()
    if not src or not src.access_token:
        raise HTTPException(400, "hh.ru не подключён")
    our_url = settings.public_base_url.rstrip("/") + webhook_path()
    if not our_url.startswith("https://"):
        raise HTTPException(
            400,
            f"Вебхук требует публичный https-адрес, а в настройках PUBLIC_BASE_URL сейчас "
            f"{settings.public_base_url!r} — hh.ru не сможет достучаться до такого URL.",
        )
    try:
        await hh_api.subscribe_webhook(src.access_token, our_url, [EVENT_NEW_MESSAGE])
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"hh.ru: не удалось подписаться ({exc})")
    return {"status": "subscribed", "url": our_url}


@router.delete("/integrations/hh/webhook")
async def unsubscribe_hh_webhook(db: Session = Depends(get_db)):
    from app.api.hh_webhook import webhook_path
    from app.services import hh_api

    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "hh", RecruitmentSource.is_active == True
    ).first()
    if not src or not src.access_token:
        raise HTTPException(400, "hh.ru не подключён")
    our_url = settings.public_base_url.rstrip("/") + webhook_path()
    try:
        subs = await hh_api.list_webhook_subscriptions(src.access_token)
        for s in subs:
            if s.get("url") == our_url and s.get("id"):
                await hh_api.delete_webhook_subscription(src.access_token, str(s["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"hh.ru: не удалось отписаться ({exc})")
    return {"status": "unsubscribed"}


async def _avito_source_and_token(db):
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "avito",
        RecruitmentSource.is_active == True,
    ).first()
    if not src or not (src.client_id and src.client_secret):
        raise HTTPException(400, "Авито не подключён")
    from app.services import avito_api
    try:
        token = (await avito_api.get_token(src.client_id, src.client_secret))["access_token"]
    except Exception as exc:
        raise HTTPException(502, f"Авито: не удалось получить токен ({exc})")
    return src, token


@router.get("/integrations/avito/webhook")
async def get_avito_webhook(db: Session = Depends(get_db)):
    """Текущее состояние подписки на мгновенные уведомления о сообщениях."""
    from app.api.avito_webhook import webhook_path
    from app.services import avito_api

    our_url = settings.public_base_url.rstrip("/") + webhook_path()
    _src, token = await _avito_source_and_token(db)
    try:
        subs = await avito_api.list_messenger_subscriptions(token)
    except Exception as exc:
        raise HTTPException(502, f"Авито: не удалось получить подписки ({exc})")
    urls = [s.get("url", "") for s in subs]
    return {"url": our_url, "subscribed": our_url in urls, "all_subscriptions": urls}


@router.post("/integrations/avito/webhook")
async def subscribe_avito_webhook(db: Session = Depends(get_db)):
    """Подписаться на мгновенные уведомления о сообщениях кандидатов.

    Опрос при этом НЕ выключается: недоставленный вебхук (туннель лежал)
    теряется навсегда, а опрос подберёт такое сообщение на следующем круге.
    """
    from app.api.avito_webhook import webhook_path
    from app.services import avito_api

    our_url = settings.public_base_url.rstrip("/") + webhook_path()
    if not our_url.startswith("https://"):
        raise HTTPException(
            400,
            f"Вебхук требует публичный https-адрес, а в настройках PUBLIC_BASE_URL сейчас "
            f"{settings.public_base_url!r} — Авито не сможет достучаться до такого URL.",
        )
    _src, token = await _avito_source_and_token(db)
    try:
        await avito_api.subscribe_messenger_webhook(token, our_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Авито: не удалось подписаться ({exc})")
    return {"status": "subscribed", "url": our_url}


@router.delete("/integrations/avito/webhook")
async def unsubscribe_avito_webhook(db: Session = Depends(get_db)):
    from app.api.avito_webhook import webhook_path
    from app.services import avito_api

    our_url = settings.public_base_url.rstrip("/") + webhook_path()
    _src, token = await _avito_source_and_token(db)
    try:
        await avito_api.unsubscribe_messenger_webhook(token, our_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Авито: не удалось отписаться ({exc})")
    return {"status": "unsubscribed"}


@router.get("/integrations/avito/vacancies")
async def avito_vacancies(db: Session = Depends(get_db)):
    return []


@router.get("/integrations/avito/vacancy/{vacancy_id}")
async def avito_vacancy_by_id(vacancy_id: str, db: Session = Depends(get_db)):
    """Lookup a single Avito vacancy by ID to validate and get its title."""
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == "avito",
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        raise HTTPException(400, "Авито не подключён")
    from app.services import avito_api
    try:
        tok = await avito_api.get_token(src.client_id, src.client_secret)
        result = await avito_api.get_vacancy_by_id(tok["access_token"], vacancy_id)
        if result is None:
            raise HTTPException(404, "Вакансия не найдена")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.error("avito_vacancy_by_id error: %s", e, exc_info=True)
        raise HTTPException(502, f"Ошибка Авито: {e}")


@router.patch("/integrations/{source}/interval")
def update_interval(source: str, interval_minutes: int, db: Session = Depends(get_db)):
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == source).first()
    if not src: raise HTTPException(404, "Source not found")
    src.sync_interval_minutes = max(1, interval_minutes)
    db.commit()
    return src.to_dict()


# ── Vacancy links ──────────────────────────────────────────────────

@router.get("/links")
def list_links(vacancy_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    q = db.query(VacancyLink)
    if vacancy_id: q = q.filter(VacancyLink.vacancy_id == vacancy_id)
    return [link.to_dict() for link in q.all()]


@router.post("/links")
def create_link(data: LinkCreate, db: Session = Depends(get_db)):
    if data.source not in ("hh", "avito"):
        raise HTTPException(400, "source must be 'hh' or 'avito'")
    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == data.source,
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        raise HTTPException(400, f"Источник {data.source} не подключён")
    # A vacancy can carry several external listings on the same platform (see
    # VacancyLink docstring) — only the exact same listing is treated as a
    # no-op update, not "any link for this vacancy+source".
    existing = db.query(VacancyLink).filter(
        VacancyLink.vacancy_id == data.vacancy_id,
        VacancyLink.source == data.source,
        VacancyLink.external_vacancy_id == data.external_vacancy_id,
    ).first()
    if existing:
        # Update instead
        existing.external_vacancy_title = data.external_vacancy_title or ""
        existing.sync_enabled = True
        db.commit(); db.refresh(existing)
        return existing.to_dict()

    link = VacancyLink(
        vacancy_id=data.vacancy_id,
        source=data.source,
        source_id=src.id,
        external_vacancy_id=data.external_vacancy_id,
        external_vacancy_title=data.external_vacancy_title or "",
        sync_enabled=True,
    )
    db.add(link); db.commit(); db.refresh(link)
    return link.to_dict()


@router.patch("/links/{link_id}")
def update_link(link_id: int, data: LinkUpdate, db: Session = Depends(get_db)):
    link = db.query(VacancyLink).filter(VacancyLink.id == link_id).first()
    if not link: raise HTTPException(404, "Link not found")
    if data.sync_enabled is not None: link.sync_enabled = data.sync_enabled
    if data.external_vacancy_id is not None: link.external_vacancy_id = data.external_vacancy_id
    if data.external_vacancy_title is not None: link.external_vacancy_title = data.external_vacancy_title
    db.commit(); db.refresh(link)
    return link.to_dict()


@router.delete("/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.query(VacancyLink).filter(VacancyLink.id == link_id).first()
    if not link: raise HTTPException(404, "Link not found")
    db.delete(link); db.commit()
    return {"status": "deleted"}


# ── Сводка по воронке ──────────────────────────────────────────────

@router.get("/notifications")
def get_notifications(db: Session = Depends(get_db)):
    """Счётчики для бейджей: сколько кандидатов ждут внимания.

    Считается из состояния опроса теми же функциями, что и карточки в списке,
    поэтому бейдж не может разойтись с тем, что видно на странице.
    """
    from app.services import quick_screening, recruitment_stages as rs

    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    counts = {"new_candidates": 0, "needs_reply": 0, "silent": 0, "undelivered": 0}
    by_stage = {stage: 0 for stage in rs.STAGES}

    for c in db.query(Candidate).all():
        state = quick_screening.load_state(c)
        by_stage[rs.derive_stage(c.stage, state)] = by_stage.get(rs.derive_stage(c.stage, state), 0) + 1
        if c.created_at and c.created_at >= since:
            counts["new_candidates"] += 1
        for flag in rs.flags(state, now=now):
            code = flag["code"]
            if code == rs.FLAG_NEEDS_REPLY:
                counts["needs_reply"] += 1
            elif code == rs.FLAG_SILENT:
                counts["silent"] += 1
            elif code == rs.FLAG_UNDELIVERED:
                counts["undelivered"] += 1

    return {**counts, "by_stage": by_stage}


@router.get("/stages")
def get_stages():
    """Этапы воронки в порядке движения — чтобы фронт не хранил свою копию."""
    from app.services import recruitment_stages as rs
    return {"stages": rs.STAGES, "bot_stages": sorted(rs.BOT_STAGES),
            "human_stages": sorted(rs.HUMAN_STAGES)}


@router.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    from app.services import recruitment_sync
    background_tasks.add_task(recruitment_sync.run_now)
    return {"status": "sync_started"}
