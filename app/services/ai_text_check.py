"""AI pre-check gate: every piece of AI-facing text must be checked by the
AI before it can be saved, so an admin can never blindly save text the AI
will later use to talk to candidates without first seeing what the AI
understood from it (and whether it looks mis-scoped)."""
import json
import logging
import re

log = logging.getLogger(__name__)


def check_text(cfg: dict, text: str, scope: str, vacancy_title: str = None,
                field_label: str = "запись базы знаний") -> dict:
    """Returns {"ai_available": bool, "summary": str, "scope_mismatch": bool, "concerns": [str]}"""
    from app.services.llm_client import chat

    text = (text or "").strip()
    if not text:
        return {"ai_available": True, "summary": "", "scope_mismatch": False, "concerns": ["Текст пуст."]}

    scope_label = "общая (для всех вакансий)" if scope == "global" else f"только для вакансии «{vacancy_title or ''}»"
    prompt = (
        f"Ты проверяешь {field_label} перед сохранением в базу знаний HR-ассистента.\n"
        f"Заявленная область действия: {scope_label}.\n\n"
        f"Текст:\n{text}\n\n"
        "Сделай три вещи:\n"
        "1. Перескажи своими словами в 1-3 предложениях, как ты понял этот текст "
        "(чтобы автор мог проверить, правильно ли ИИ понял).\n"
        "2. Если область действия 'общая', но текст похож на специфику конкретной вакансии "
        "(конкретная зарплата, конкретный адрес/график, условия именно одной роли) — "
        "поставь scope_mismatch=true.\n"
        "3. Перечисли любые другие проблемы: противоречия, расплывчатость, обрывочность.\n\n"
        'Верни ТОЛЬКО JSON: {"summary": "...", "scope_mismatch": false, "concerns": ["..."]}'
    )

    try:
        raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=400)
    except Exception as e:
        log.warning("ai_text_check failed: %s", e)
        raw = None

    if not raw:
        return {
            "ai_available": False,
            "summary": "",
            "scope_mismatch": False,
            "concerns": ["ИИ-проверка недоступна (не настроен API-ключ или ошибка запроса). "
                         "Сохранение всё равно требует вашего явного подтверждения."],
        }

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"ai_available": True, "summary": raw.strip()[:500], "scope_mismatch": False, "concerns": []}
    try:
        data = json.loads(m.group())
    except Exception:
        return {"ai_available": True, "summary": raw.strip()[:500], "scope_mismatch": False, "concerns": []}

    return {
        "ai_available": True,
        "summary": (data.get("summary") or "").strip(),
        "scope_mismatch": bool(data.get("scope_mismatch")),
        "concerns": data.get("concerns") or [],
    }


def generate_candidate_questions(cfg: dict, title: str, description: str) -> list:
    """Returns [{"category": str, "question": str}, ...] — likely candidate
    questions for this vacancy, to seed the vacancy-creation wizard's KB step.

    Raises RuntimeError with a human-readable reason on any failure (no API
    key, API error, unparseable response) instead of returning an empty list
    — the caller surfaces this to the admin so a misconfiguration doesn't
    look like "AI decided there are no questions"."""
    from app.services.llm_client import chat

    if not (cfg.get("anthropic_api_key") or "").strip():
        raise RuntimeError("Не задан Anthropic API Key (Настройки → Автоматизация).")

    prompt = (
        f"Вакансия: {title}\n"
        f"Описание: {description or '(не заполнено)'}\n\n"
        "Составь расширенный список вопросов, которые с высокой вероятностью задаст кандидат "
        "при отклике на эту вакансию. Сгруппируй по категориям: "
        "«График и оплата», «Требования и опыт», «Процесс найма», «Условия работы». "
        "По 3-6 вопросов на категорию, конкретно и по делу, без воды.\n\n"
        'Верни ТОЛЬКО JSON: {"questions": [{"category": "...", "question": "..."}]}'
    )
    try:
        raw = chat(cfg, [{"role": "user", "content": prompt}], max_tokens=900)
    except Exception as e:
        log.warning("generate_candidate_questions failed: %s", e)
        raise RuntimeError(f"Ошибка запроса к Anthropic: {e}") from e

    if not raw:
        raise RuntimeError("Anthropic не вернул ответ (проверьте API-ключ и логи сервера).")
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise RuntimeError("Не удалось распознать JSON в ответе ИИ.")
    try:
        data = json.loads(m.group())
    except Exception as e:
        raise RuntimeError(f"Ответ ИИ не похож на валидный JSON: {e}") from e
    return data.get("questions") or []
