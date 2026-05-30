from datetime import datetime, timedelta
import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import RedirectResponse

log = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recruitment import Candidate, RecruitmentSource, Vacancy, VacancyLink, TelegramMessage, UnlinkedTelegramMessage
from app.settings import settings


def _hh_creds() -> tuple[str, str]:
    return settings.hh_client_id, settings.hh_client_secret



# Stored in-process during the brief OAuth redirect roundtrip (seconds)
_pending_hh_redirect_uri: str = ""

router = APIRouter(prefix="/recruitment", tags=["Recruitment"])

VALID_STAGES = ["отклик", "собеседование", "ждем", "ждем_привязки", "общение", "отказ", "нанят"]
VALID_SOURCES = ["hh", "avito", "manual", "other"]


# ── Pydantic schemas ───────────────────────────────────────────────

class VacancyCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    knowledge_base: Optional[str] = ""
    interview_location: Optional[str] = ""
    is_open: bool = True

class VacancyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    knowledge_base: Optional[str] = None
    interview_location: Optional[str] = None
    is_open: Optional[bool] = None

class CandidateCreate(BaseModel):
    vacancy_id: int
    name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = "manual"
    stage: Optional[str] = "отклик"
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
    telegram_chat_id: Optional[str] = None
    telegram_username: Optional[str] = None
    send_telegram: bool = False

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
    v = Vacancy(title=data.title, description=data.description,
                knowledge_base=data.knowledge_base, interview_location=data.interview_location,
                is_open=data.is_open)
    db.add(v); db.commit(); db.refresh(v)
    return v.to_dict()

@router.patch("/vacancies/{vacancy_id}")
def update_vacancy(vacancy_id: int, data: VacancyUpdate, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v:
        raise HTTPException(404, "Vacancy not found")
    if data.title is not None: v.title = data.title
    if data.description is not None: v.description = data.description
    if data.knowledge_base is not None: v.knowledge_base = data.knowledge_base
    if data.interview_location is not None: v.interview_location = data.interview_location
    if data.is_open is not None: v.is_open = data.is_open
    db.commit(); db.refresh(v)
    return v.to_dict()

@router.delete("/vacancies/{vacancy_id}")
def delete_vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v: raise HTTPException(404, "Vacancy not found")
    db.delete(v); db.commit()
    return {"status": "deleted"}

def _get_kb_and_cfg(v):
    """Return (knowledge_base_str, cfg) or raise HTTPException."""
    from app.services.config_service import ConfigService
    from app.services.llm_client import get_client
    cfg = ConfigService().load()
    if not get_client(cfg):
        raise HTTPException(400, "API Key не настроен в Настройках")
    kb = (getattr(v, "knowledge_base", "") or "").strip() or (cfg.get("automation_knowledge_base") or "").strip()
    if not kb:
        raise HTTPException(400, "База знаний пуста. Заполните её сначала.")
    return kb, cfg


@router.post("/vacancies/{vacancy_id}/analyze-kb")
async def analyze_knowledge_base(vacancy_id: int, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v: raise HTTPException(404, "Vacancy not found")

    kb, cfg = _get_kb_and_cfg(v)
    from app.services.llm_client import chat

    prompt = f"""Ты опытный HR-консультант. Проанализируй базу знаний о вакансии «{v.title}».

База знаний:
{kb}

Задача: выяви пробелы. Напиши список конкретных вопросов, которые кандидат СКОРЕЕ ВСЕГО задаст, но ответа на которые в базе знаний НЕТ.

Формат ответа — нумерованный список. Каждый пункт: вопрос кандидата + одно предложение почему его нет в базе. Без вступлений и заключений. Максимум 10 пунктов."""

    try:
        result = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=800)
        return {"result": result or ""}
    except Exception as e:
        raise HTTPException(500, f"Ошибка AI: {e}")


@router.post("/vacancies/{vacancy_id}/calibrate-kb")
async def calibrate_knowledge_base(vacancy_id: int, db: Session = Depends(get_db)):
    v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
    if not v: raise HTTPException(404, "Vacancy not found")

    kb, cfg = _get_kb_and_cfg(v)
    from app.services.llm_client import chat

    prompt = f"""Ты HR-ассистент, который будет отвечать кандидатам на вакансию «{v.title}».
Прочитай базу знаний и подтверди как ты её понял — перефразируй каждый смысловой блок своими словами так, как будешь отвечать кандидатам.

База знаний:
{kb}

Формат: разбей по темам (зарплата, график, требования, условия и т.д.). По каждой теме:
— напиши как ты понял информацию
— если что-то неоднозначно или может быть интерпретировано по-разному — явно отметь это словом [УТОЧНИТЕ]

Без вступлений. Только структурированный разбор."""

    try:
        result = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=1000)
        return {"result": result or ""}
    except Exception as e:
        raise HTTPException(500, f"Ошибка AI: {e}")


# ── Candidates ─────────────────────────────────────────────────────

@router.get("/candidates")
def list_candidates(
    vacancy_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Candidate)
    if vacancy_id is not None: q = q.filter(Candidate.vacancy_id == vacancy_id)
    if stage: q = q.filter(Candidate.stage == stage)
    candidates = q.order_by(Candidate.created_at.asc()).all()

    # Compute per-candidate flags
    since_24h = datetime.utcnow() - timedelta(hours=24)
    # Collect candidate IDs with unread TG messages
    try:
        unread_tg_ids = {
            row[0] for row in db.query(TelegramMessage.candidate_id).filter(
                TelegramMessage.direction == "in",
                TelegramMessage.is_read == False,
            ).all()
        }
    except Exception:
        unread_tg_ids = set()

    result = []
    for c in candidates:
        d = c.to_dict()
        d["is_new"] = bool(c.created_at and c.created_at >= since_24h)
        d["has_unread_hh_msg"] = bool(getattr(c, "has_unread_hh_msg", False))
        d["has_unread_tg"] = c.id in unread_tg_ids
        d["vacancy_title"] = c.vacancy.title if c.vacancy else ""
        result.append(d)
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
        source=data.source or "manual", stage=data.stage or "отклик",
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
                  "age", "resume_url", "photo_url", "telegram_chat_id", "telegram_username"):
        val = getattr(data, field)
        if val is not None: setattr(c, field, val)
    c.updated_at = datetime.utcnow()
    db.commit(); db.refresh(c)

    warnings: list[str] = []

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

    # Send via Telegram Secretary Mode if requested
    tg_chat_id = c.telegram_chat_id or ""
    tg_text = data.hh_message or data.rejection_message or ""
    if data.send_telegram and tg_chat_id and tg_text:
        from app.services.notify import send_secretary_message
        err = await send_secretary_message(tg_chat_id, tg_text)
        if err:
            warnings.append(err)

    result = c.to_dict()
    if warnings:
        result["warnings"] = warnings
    return result


@router.post("/candidates/{candidate_id}/resolve-telegram")
async def resolve_telegram_username(candidate_id: int, db: Session = Depends(get_db)):
    """Resolve candidate's telegram_username → chat_id via getChat API."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    username = (c.telegram_username or "").strip().lstrip("@")
    if not username:
        raise HTTPException(400, "telegram_username не заполнен")

    import httpx
    from app.config import TOKEN
    if not TOKEN:
        raise HTTPException(500, "Telegram bot token не настроен")

    from app.settings import settings as _settings
    proxy = getattr(_settings, "telegram_proxy", None)
    client_kwargs: dict = {"timeout": 10.0}
    if proxy:
        client_kwargs["proxy"] = proxy

    async with httpx.AsyncClient(**client_kwargs) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TOKEN}/getChat",
            json={"chat_id": f"@{username}"},
        )

    if r.status_code != 200:
        data = r.json() if r.content else {}
        raise HTTPException(400, data.get("description") or f"Telegram: HTTP {r.status_code}")

    chat = r.json().get("result", {})
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        raise HTTPException(400, "Не удалось получить chat_id")

    c.telegram_chat_id = chat_id
    db.commit()
    db.refresh(c)
    return {"chat_id": chat_id, "candidate": c.to_dict()}


@router.get("/candidates/{candidate_id}/telegram-messages")
def get_telegram_messages(candidate_id: int, db: Session = Depends(get_db)):
    msgs = db.query(TelegramMessage).filter(
        TelegramMessage.candidate_id == candidate_id
    ).order_by(TelegramMessage.created_at).all()
    # Mark incoming messages as read when admin opens TG chat
    try:
        updated = False
        for m in msgs:
            if m.direction == "in" and not getattr(m, 'is_read', True):
                m.is_read = True
                updated = True
        if updated:
            db.commit()
    except Exception:
        pass
    return [m.to_dict() for m in msgs]


@router.post("/candidates/{candidate_id}/telegram-messages")
async def send_telegram_message(candidate_id: int, data: SendMessageRequest, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if not c.telegram_chat_id:
        raise HTTPException(400, "Telegram chat_id не найден. Укажите username и нажмите Найти.")

    from app.services.notify import send_secretary_message
    err = await send_secretary_message(c.telegram_chat_id, data.text)
    if err:
        # Add config diagnostics to help debug
        try:
            from app.services.config_service import ConfigService
            cfg = ConfigService().load()
            conn_id = cfg.get("tg_business_connection_id", "")
            can_reply = cfg.get("tg_business_can_reply", "NOT SET")
            log.warning("Secretary send failed. config: connection_id=%r can_reply=%r", conn_id, can_reply)
            raise HTTPException(400, f"{err} [diag: connection_id={'set' if conn_id else 'EMPTY'}, can_reply={can_reply!r}]")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, err)

    msg = TelegramMessage(candidate_id=candidate_id, direction="out", text=data.text)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg.to_dict()


@router.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)):
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c: raise HTTPException(404, "Candidate not found")
    db.delete(c); db.commit()
    return {"status": "deleted"}


@router.post("/candidates/{candidate_id}/reset-history")
def reset_candidate_history(candidate_id: int, db: Session = Depends(get_db)):
    """Delete all Telegram messages and reset automation state for a clean test."""
    from datetime import datetime
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")

    deleted = db.query(TelegramMessage).filter(
        TelegramMessage.candidate_id == candidate_id
    ).delete(synchronize_session=False)

    c.follow_up_count = 0
    c.follow_up_last_sent_at = None
    c.pending_interview_date = None
    c.pending_interview_time = None
    c.pending_interview_place = None
    c.stage = "отклик"
    c.updated_at = datetime.utcnow()
    db.commit()

    return {"status": "reset", "messages_deleted": deleted}


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


def _get_hh_candidate(candidate_id: int, db):
    """Return (candidate, hh_token) or raise HTTPException."""
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if c.source != "hh" or not c.external_id:
        raise HTTPException(400, "Переписка доступна только для кандидатов с hh.ru")
    src = db.query(RecruitmentSource).filter(RecruitmentSource.source == "hh").first()
    if not src or not src.access_token:
        raise HTTPException(400, "hh.ru не подключён")
    return c, src.access_token


@router.get("/candidates/{candidate_id}/messages")
async def get_candidate_messages(candidate_id: int, db: Session = Depends(get_db)):
    c, token = _get_hh_candidate(candidate_id, db)
    # Clear unread flag when admin opens hh chat
    if getattr(c, 'has_unread_hh_msg', False):
        try:
            c.has_unread_hh_msg = False
            db.commit()
        except Exception:
            pass
    from app.services import hh_api
    try:
        return await hh_api.get_messages(token, c.external_id)
    except Exception as exc:
        raise HTTPException(502, f"Ошибка hh.ru: {exc}")


@router.post("/candidates/{candidate_id}/messages")
async def send_candidate_message(candidate_id: int, data: SendMessageRequest, db: Session = Depends(get_db)):
    if not data.text.strip():
        raise HTTPException(400, "Текст сообщения не может быть пустым")
    c, token = _get_hh_candidate(candidate_id, db)
    from app.services import hh_api
    try:
        return await hh_api.send_message(token, c.external_id, data.text.strip())
    except ValueError as exc:
        raise HTTPException(502, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"Ошибка hh.ru: {exc}")


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
    # Check uniqueness (one source per vacancy)
    existing = db.query(VacancyLink).filter(
        VacancyLink.vacancy_id == data.vacancy_id,
        VacancyLink.source == data.source,
    ).first()
    if existing:
        # Update instead
        existing.external_vacancy_id = data.external_vacancy_id
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


# ── Telegram link code ─────────────────────────────────────────────

@router.get("/candidates/{candidate_id}/telegram-link")
def get_telegram_link(candidate_id: int, db: Session = Depends(get_db)):
    """Generate or return existing link code + t.me deep link for candidate."""
    import secrets, string
    from urllib.parse import quote
    c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    if not getattr(c, 'telegram_link_code', None):
        alphabet = string.ascii_uppercase + string.digits
        token = ''.join(secrets.choice(alphabet) for _ in range(6))
        code = f"CAND-{candidate_id}-{token}"
        try:
            c.telegram_link_code = code
            db.commit()
        except Exception:
            pass
    else:
        code = c.telegram_link_code

    # Build t.me deep link if personal username is configured
    from app.services.config_service import ConfigService
    cfg = ConfigService().load()
    personal_username = (cfg.get("tg_personal_username") or "").strip().lstrip("@")
    tg_link = None
    if personal_username:
        tg_link = f"https://t.me/{personal_username}?text={quote(code)}"

    return {"code": code, "tg_link": tg_link, "personal_username": personal_username}


# ── Unlinked Telegram messages ─────────────────────────────────────

@router.get("/unlinked-tg")
def list_unlinked_tg(db: Session = Depends(get_db)):
    try:
        msgs = db.query(UnlinkedTelegramMessage).order_by(
            UnlinkedTelegramMessage.created_at.desc()
        ).limit(100).all()
        return [m.to_dict() for m in msgs]
    except Exception:
        return []


class LinkTgRequest(BaseModel):
    candidate_id: int

@router.post("/unlinked-tg/{msg_id}/link")
def link_unlinked_tg(msg_id: int, data: LinkTgRequest, db: Session = Depends(get_db)):
    try:
        msg = db.query(UnlinkedTelegramMessage).filter(
            UnlinkedTelegramMessage.id == msg_id
        ).first()
        if not msg:
            raise HTTPException(404, "Message not found")
        c = db.query(Candidate).filter(Candidate.id == data.candidate_id).first()
        if not c:
            raise HTTPException(404, "Candidate not found")
        # Link chat_id to candidate
        c.telegram_chat_id = msg.chat_id
        db.commit()
        # Move message to TelegramMessage
        tg_msg = TelegramMessage(
            candidate_id=c.id,
            direction="in",
            text=msg.text,
            tg_message_id=msg.tg_message_id,
        )
        db.add(tg_msg)
        db.delete(msg)
        db.commit()
        return {"status": "linked", "candidate": c.to_dict()}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.delete("/unlinked-tg/{msg_id}")
def delete_unlinked_tg(msg_id: int, db: Session = Depends(get_db)):
    try:
        msg = db.query(UnlinkedTelegramMessage).filter(
            UnlinkedTelegramMessage.id == msg_id
        ).first()
        if msg:
            db.delete(msg)
            db.commit()
    except Exception:
        pass
    return {"status": "deleted"}


# ── Notifications summary ──────────────────────────────────────────

@router.get("/notifications")
def get_notifications(db: Session = Depends(get_db)):
    """Return unread counts for dashboard badges."""
    from sqlalchemy import text
    since = datetime.utcnow() - timedelta(hours=24)
    new_candidates = db.query(Candidate).filter(Candidate.created_at >= since).count()

    try:
        unread_hh = db.query(Candidate).filter(Candidate.has_unread_hh_msg == True).count()
    except Exception:
        try:
            unread_hh = db.execute(
                text("SELECT COUNT(*) FROM candidates WHERE has_unread_hh_msg = 1")
            ).scalar() or 0
        except Exception:
            unread_hh = 0

    try:
        unread_tg = db.query(TelegramMessage).filter(
            TelegramMessage.direction == "in",
            TelegramMessage.is_read == False,
        ).count()
    except Exception:
        try:
            unread_tg = db.execute(
                text("SELECT COUNT(*) FROM telegram_messages WHERE direction='in' AND is_read=0")
            ).scalar() or 0
        except Exception:
            unread_tg = 0

    try:
        unlinked_tg = db.execute(text("SELECT COUNT(*) FROM unlinked_telegram_messages")).scalar() or 0
    except Exception:
        unlinked_tg = 0

    try:
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        pending_tg = db.query(Candidate).filter(
            Candidate.stage == "ждем_привязки",
            Candidate.updated_at <= cutoff_24h,
        ).count()
    except Exception:
        pending_tg = 0

    return {
        "new_candidates": new_candidates,
        "unread_hh": unread_hh,
        "unread_tg": unread_tg,
        "unlinked_tg": unlinked_tg,
        "pending_tg_24h": pending_tg,
    }


# ── Automation ────────────────────────────────────────────────────

@router.get("/automation/status")
def get_automation_status():
    from app.services.automation import is_enabled
    return {"enabled": is_enabled()}

@router.post("/automation/toggle")
def toggle_automation(data: dict = Body({})):
    from app.services.automation import set_enabled, is_enabled
    val = data.get("enabled")
    if val is None:
        val = not is_enabled()
    set_enabled(bool(val))
    return {"enabled": is_enabled()}

@router.post("/candidates/{candidate_id}/test-automation")
async def test_automation(candidate_id: int):
    from app.services.automation import trigger_for_candidate
    result = await trigger_for_candidate(candidate_id, force=True)
    return {"result": result}


# ── Manual sync trigger ────────────────────────────────────────────

@router.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    from app.services import recruitment_sync
    background_tasks.add_task(recruitment_sync.run_now)
    return {"status": "sync_started"}
