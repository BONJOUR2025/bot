"""Resolves the effective HiringStrategy + AI knowledge-base context for a vacancy.

Once a vacancy has strategy_id set, the strategy is the sole source of truth
for filters/follow-up/hh-templates/away-message/ai_model — there is no
fallback to global config for those fields. This avoids a dual-config-path
where the admin can't tell which value is actually in effect.
"""
from typing import Optional


def get_strategy(db, vacancy):
    """Return the HiringStrategy assigned to vacancy, or None."""
    if not vacancy or not vacancy.strategy_id:
        return None
    from app.models.recruitment import HiringStrategy
    return db.query(HiringStrategy).filter(HiringStrategy.id == vacancy.strategy_id).first()


def build_ai_context_block(db, vacancy) -> str:
    """Build the structured, explicitly-scoped knowledge-base text block fed
    to the AI prompt. Returns "" if nothing is configured anywhere, so the
    caller's "no KB configured — notify admin" path keeps working."""
    import json
    from app.models.recruitment import KnowledgeBaseEntry

    global_entries = db.query(KnowledgeBaseEntry).filter(KnowledgeBaseEntry.scope == "global").all()
    vacancy_entries = []
    if vacancy:
        vacancy_entries = db.query(KnowledgeBaseEntry).filter(
            KnowledgeBaseEntry.scope == "vacancy",
            KnowledgeBaseEntry.vacancy_id == vacancy.id,
        ).all()

    parts = []

    # Structured deal-breakers go first — a stage instruction like "проверь
    # deal-breakers" only reliably produces the right questions if the AI is
    # handed concrete label/value facts to check against, not just told
    # "look in the knowledge base" and left to infer which entries are relevant.
    deal_breakers = []
    if vacancy and getattr(vacancy, "deal_breakers_json", None):
        try:
            deal_breakers = json.loads(vacancy.deal_breakers_json) or []
        except Exception:
            deal_breakers = []
    db_lines = "\n".join(
        f"- {d.get('label', '').strip()}: {d.get('value', '').strip()}"
        for d in deal_breakers if d.get("label") and d.get("value")
    )
    if db_lines:
        parts.append(
            "Критичные условия вакансии (deal-breakers) — обязательно сверь каждое из них с кандидатом:\n" + db_lines
        )

    # Note: the vacancy's custom_questions are NOT injected here — they're
    # pinned to a specific stage instead (see interview_stages.render_stages_block
    # + Stage.ask_custom_questions), so the admin controls exactly when in the
    # script they get asked, rather than leaving the AI to pick a moment.

    if global_entries:
        lines = "\n".join(f"- {e.question.strip()}: {e.answer.strip()}" for e in global_entries if e.answer)
        if lines:
            parts.append("Общая база знаний компании (верно для всех вакансий):\n" + lines)
    if vacancy_entries:
        lines = "\n".join(f"- {e.question.strip()}: {e.answer.strip()}" for e in vacancy_entries if e.answer)
        if lines:
            title = vacancy.title if vacancy else ""
            parts.append(f"База знаний вакансии «{title}» (приоритет выше общей базы):\n" + lines)

    extra = (getattr(vacancy, "extra_instructions", "") or "").strip() if vacancy else ""
    if extra:
        parts.append(
            "Особые инструкции именно для этой вакансии (наивысший приоритет, "
            "применяй их даже при противоречии с базой знаний выше):\n" + extra
        )

    return "\n\n".join(parts)


def get_interview_location(vacancy, cfg: dict) -> str:
    if vacancy and (vacancy.interview_location or "").strip():
        return vacancy.interview_location.strip()
    return (cfg.get("automation_interview_location") or "").strip()


def get_ai_model(strategy) -> Optional[str]:
    return (strategy.ai_model or None) if strategy else None


def get_away_message(strategy, cfg: dict) -> str:
    if strategy and (strategy.away_message or "").strip():
        return strategy.away_message.strip()
    return (cfg.get("automation_away_message") or "").strip()
