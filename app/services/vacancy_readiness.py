"""Check vacancy knowledge base for gaps needed for structured AI screening."""
import json
import logging
import re

log = logging.getLogger(__name__)

REQUIRED_SECTIONS = [
    ("deal-breakers", "Deal-breakers — конкретные условия без которых кандидат точно не подходит "
     "(локация, формат работы, гражданство, минимальный опыт). Сформулируй как вопрос рекрутеру."),
    ("salary", "Зарплатная вилка — минимум и максимум для скрининга ожиданий кандидата."),
    ("first_tasks", "Реальные задачи первых 3 месяцев — конкретно, не 'развитие продукта'."),
    ("next_steps", "Следующие шаги после AI-скрининга и сроки ответа кандидату."),
]


async def get_missing_questions(vacancy, cfg: dict) -> list[str]:
    """Analyze vacancy KB and return list of specific questions for the recruiter."""
    from app.services.llm_client import chat

    kb = (getattr(vacancy, "knowledge_base", "") or "").strip()
    title = getattr(vacancy, "title", "Вакансия")

    prompt = (
        f"Вакансия: {title}\n"
        f"База знаний:\n{kb or '(пусто)'}\n\n"
        "Для качественного AI-скрининга мне нужны следующие данные. "
        "Проверь каждый пункт — если информации нет или она слишком расплывчата, "
        "сформулируй конкретный вопрос рекрутеру. Если есть — пропусти.\n\n"
        "Проверяй:\n"
        "1. Deal-breakers (условия без которых кандидат точно не подходит)\n"
        "2. Зарплатная вилка (мин и макс)\n"
        "3. Реальные задачи первых 3 месяцев (конкретно)\n"
        "4. Следующие шаги после скрининга и сроки ответа\n\n"
        "Верни ТОЛЬКО JSON: {\"questions\": [\"вопрос 1\", \"вопрос 2\"]}\n"
        "Максимум 4 вопроса. Если всё есть — пустой список."
    )

    raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=300)
    if not raw:
        return []
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group()).get("questions", [])
    except Exception:
        return []


async def notify_admin_if_incomplete(vacancy_id: int):
    """Check vacancy and notify admin via Telegram if KB is incomplete."""
    from app.db.session import SessionLocal
    from app.models.recruitment import Vacancy
    from app.services.config_service import ConfigService
    from app.services.notify import send_notification_with_keyboard

    db = SessionLocal()
    try:
        v = db.query(Vacancy).filter(Vacancy.id == vacancy_id).first()
        if not v or not v.is_open:
            return
        cfg = ConfigService().load()
    finally:
        db.close()

    questions = await get_missing_questions(v, cfg)
    if not questions:
        return

    q_text = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    await send_notification_with_keyboard(
        f"📋 <b>Вакансия «{v.title}» — нужны данные для скрининга</b>\n\n"
        f"Чтобы правильно собеседовать кандидатов, мне нужно знать:\n\n"
        f"{q_text}\n\n"
        f"Ответьте на вопросы — и я обновлю сценарий.",
        [[{"text": "✏️ Ответить", "callback_data": f"vsetup_{v.id}"}]],
    )
    log.info("Vacancy readiness check: sent gap questions for vacancy_id=%s", vacancy_id)
