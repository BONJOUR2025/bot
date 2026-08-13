"""Auto-learning: extract Q&A from escalated exchanges and add to knowledge base."""
import json
import logging
import re

log = logging.getLogger(__name__)


async def learn_from_escalation(candidate_id: int, question: str, admin_answer: str) -> bool:
    """
    Use Claude to format the Q&A as a knowledge entry and save it.
    Returns True if a new entry was created.
    """
    try:
        from app.services.config_service import ConfigService
        from app.db.session import SessionLocal
        from app.models.knowledge import KnowledgeDocument
        from app.services.notify import send_notification
        from app.models.recruitment import Candidate

        cfg = ConfigService().load()
        from app.services.llm_client import chat
        prompt = (
            "Кандидат задал вопрос HR-менеджеру, менеджер ответил. "
            "Сформулируй это как запись в базу знаний для HR-бота.\n\n"
            f"Вопрос кандидата: {question}\n"
            f"Ответ менеджера: {admin_answer}\n\n"
            "Ответь ТОЛЬКО в формате JSON (без markdown, без пояснений):\n"
            '{"title": "краткий заголовок вопроса (до 80 символов)", '
            '"content": "чёткий, полный ответ на этот вопрос (2-5 предложений)", '
            '"quality": 3, '
            '"is_useful": true}'
            "\n\nПравила для поля quality (1-5): насколько полезна эта запись для будущих кандидатов.\n"
            "Правила для is_useful=false:\n"
            "- Персональная информация конкретного кандидата\n"
            "- Разовая ситуация, нерелевантная другим\n"
            "- Пустой/слишком короткий ответ менеджера\n"
            "- Уже очевидная информация"
        )

        raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=400)
        if not raw:
            log.warning("learning_service: no API key configured, skipping auto-learn")
            return False

        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            log.warning("learning_service: Claude returned unexpected format: %s", raw[:200])
            return False

        data = json.loads(m.group())
        title = (data.get("title") or "").strip()
        content = (data.get("content") or "").strip()
        quality = int(data.get("quality") or 0)
        is_useful = bool(data.get("is_useful", True))

        if not title or not content:
            log.warning("learning_service: empty title or content from Claude")
            return False

        # Quality gate: skip if not useful or quality too low
        if not is_useful or quality < 3:
            log.info("learning_service: skipping entry '%s' (is_useful=%s, quality=%s)", title, is_useful, quality)
            return False

        db = SessionLocal()
        try:
            # Check for duplicate (same title already exists)
            existing = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.title == title
            ).first()
            if existing:
                log.info("learning_service: entry '%s' already exists, skipping", title)
                return False

            doc = KnowledgeDocument(
                title=title,
                category="Авто-обучение",
                content=content,
                order_idx=0,
            )
            db.add(doc)
            db.commit()
            log.info("learning_service: saved new KB entry '%s'", title)

            # Get candidate name for notification
            c = db.query(Candidate).filter(Candidate.id == candidate_id).first()
            cand_name = c.name if c else f"#{candidate_id}"
        finally:
            db.close()

        # Уведомления здесь намеренно нет: пополнение базы знаний действия не
        # требует, а в общей ленте оно тонуло вперемешку с сообщениями
        # кандидатов, которые ответа как раз ждут. Запись видна в разделе
        # базы знаний.
        log.info("learning_service: knowledge base updated from dialog with %s: %s",
                 cand_name, title)
        return True

    except Exception as e:
        log.warning("learning_service error: %s", e)
        return False
