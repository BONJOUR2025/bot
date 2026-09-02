"""Сводка по кандидату: ответы на опрос плюс резюме с площадки.

Опрос даёт три-четыре ответа своими словами, резюме — должность, стаж,
ожидания по зарплате и места работы. По отдельности ни то, ни другое не
отвечает на вопрос «звонить ему или нет»: в анкете «шью изделия из кожи»
без указания, сколько лет и где, а в резюме «Начинающий специалист» без
понимания, готов ли человек учиться именно у нас. Здесь эти два источника
сводятся в одну карточку, которую рекрутер читает за десять секунд.

Формат ответа — тот же, что рисует вкладка «Профиль» в админке: она
осталась от вырезанного телеграм-интервью, полностью написана и до сих пор
не показывала ничего. Заводить второй формат ради того же смысла незачем.

Модель может быть не настроена, ответить мусором или упасть — во всех трёх
случаях сводки просто не будет. Это подпись к карточке, а не часть
воронки: опрос уже завершён, кандидат уже уведомлён, и падать здесь не из-за
чего.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime

log = logging.getLogger(__name__)

# Хватает на сводку, три-четыре сильные стороны и столько же рисков.
MAX_TOKENS = 900

RECOMMENDATIONS = ("invite", "reserve", "reject")

# Запрет на возраст, пол и гражданство в минусах стоит в промпте не для
# порядка: без него модель поставила «возраст» красным флагом 65-летнему
# мастеру с 26 годами стажа по профилю — ровно тому кандидату, которого и
# надо звать. Рекрутер читает эту сводку перед звонком, и подсказывать ему
# такое основание нельзя.
SYSTEM = """Ты — помощник рекрутера в мастерской по ремонту обуви и сумок.
Тебе дают анкету кандидата с работного сайта и его ответы на вопросы бота.
Составь короткую сводку для рекрутера, который решает, звонить ли этому
человеку.

Правила:
- Опирайся ТОЛЬКО на приведённые данные. Ничего не додумывай: если чего-то
  нет, так и напиши «не указано».
- Ответы кандидата важнее анкеты: анкета описывает прошлое, ответы — то,
  что человек говорит про эту вакансию сейчас.
- Пиши по-русски, по делу, без канцелярита и без похвал.
- Никогда не пиши в минусы возраст, пол, гражданство, национальность,
  семейное положение и внешность: это не свойства работника, а признаки,
  по которым отбирать нельзя.
- score — от 0 до 100, насколько кандидат подходит на ручную работу с кожей.
- recommendation — ровно одно из: invite (звонить), reserve (в резерв),
  reject (не подходит).

Ответь ТОЛЬКО валидным JSON без пояснений и без markdown:
{"score": 0-100,
 "score_reason": "одно предложение, почему такой балл",
 "recommendation": "invite|reserve|reject",
 "recommendation_reason": "одно предложение",
 "summary": "2-4 предложения: кто это и что умеет",
 "strengths": ["..."],
 "red_flags": ["..."],
 "salary_expectation": "строка или пустая",
 "availability": "строка или пустая",
 "tags": ["короткие метки, до 5"]}"""


def _months_label(months) -> str:
    if not months:
        return ""
    years, rest = divmod(int(months), 12)
    parts = []
    if years:
        parts.append(f"{years} г.")
    if rest:
        parts.append(f"{rest} мес.")
    return " ".join(parts)


def format_resume(profile: dict | None) -> str:
    """Анкета в виде текста для модели и для уведомления админу."""
    if not profile:
        return ""
    lines = []
    if profile.get("title"):
        lines.append(f"Желаемая должность: {profile['title']}")
    salary = profile.get("salary") or {}
    if salary.get("amount"):
        lines.append(f"Ожидания по зарплате: {salary['amount']} {salary.get('currency') or ''}".strip())
    exp = _months_label(profile.get("total_months"))
    if exp:
        lines.append(f"Общий стаж: {exp}")
    if profile.get("area"):
        lines.append(f"Город: {profile['area']}")
    if profile.get("education_level"):
        schools = "; ".join(
            " — ".join(x for x in (e.get("name"), e.get("result")) if x)
            for e in (profile.get("education") or [])[:3])
        lines.append(f"Образование: {profile['education_level']}"
                     + (f" ({schools})" if schools else ""))
    if profile.get("skills"):
        lines.append("Навыки: " + ", ".join(profile["skills"][:20]))
    if profile.get("languages"):
        lines.append("Языки: " + ", ".join(profile["languages"]))
    for field, label in (("employment", "Занятость"), ("schedule", "График")):
        if profile.get(field):
            lines.append(f"{label}: {profile[field]}")

    jobs = profile.get("experience") or []
    if jobs:
        lines.append("Опыт работы:")
        for e in jobs[:5]:
            period = f"{e.get('start') or '?'} — {e.get('end') or 'по настоящее время'}"
            head = f"  • {period}, {e.get('company') or 'без названия'}: {e.get('position') or '—'}"
            lines.append(head)
            desc = (e.get("description") or "").strip()
            if desc:
                lines.append("    " + re.sub(r"\s+", " ", desc)[:400])
    return "\n".join(lines)


def format_answers(answers: list) -> str:
    out = []
    for a in answers or []:
        q = (a.get("q") or "").strip()
        ans = (a.get("a") or "").strip()
        if q or ans:
            out.append(f"— {q}\n  {ans or '(без ответа)'}")
    return "\n".join(out)


def build_prompt(candidate, vacancy, answers: list) -> str:
    parts = []
    if vacancy is not None and getattr(vacancy, "title", ""):
        parts.append(f"ВАКАНСИЯ: {vacancy.title}")
    head = [f"Имя: {getattr(candidate, 'name', '') or '—'}"]
    if getattr(candidate, "age", None):
        head.append(f"Возраст: {candidate.age}")
    parts.append("КАНДИДАТ:\n" + "\n".join(head))

    resume = format_resume(candidate.resume_profile())
    parts.append("АНКЕТА С САЙТА:\n" + (resume or "нет — кандидат пришёл без резюме"))

    replies = format_answers(answers)
    parts.append("ОТВЕТЫ НА ВОПРОСЫ БОТА:\n" + (replies or "нет"))
    return "\n\n".join(parts)


def _parse(raw: str) -> dict | None:
    """JSON из ответа модели. Она любит обернуть его в ```json — поэтому
    ищем фигурные скобки, а не разбираем строку целиком."""
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    score = data.get("score")
    try:
        score = max(0, min(100, int(score)))
    except Exception:
        score = None
    rec = data.get("recommendation")
    return {
        "score": score,
        "score_reason": str(data.get("score_reason") or "")[:400],
        "recommendation": rec if rec in RECOMMENDATIONS else None,
        "recommendation_reason": str(data.get("recommendation_reason") or "")[:400],
        "summary": str(data.get("summary") or "")[:1500],
        "strengths": [str(x)[:200] for x in (data.get("strengths") or [])][:6],
        "red_flags": [str(x)[:200] for x in (data.get("red_flags") or [])][:6],
        "salary_expectation": str(data.get("salary_expectation") or "")[:120],
        "availability": str(data.get("availability") or "")[:120],
        "tags": [str(x)[:40] for x in (data.get("tags") or [])][:5],
        # Из чего собрано — чтобы по карточке было видно, была ли анкета.
        "source": "quick_screening",
    }


def generate(db, candidate, vacancy, answers: list, cfg: dict) -> dict | None:
    """Собрать сводку и сохранить в карточке. None — если не получилось."""
    from app.services.llm_client import chat, get_client

    if not get_client(cfg):
        log.info("candidate_profile: LLM не настроен, сводка по %s не собрана", candidate.id)
        return None

    try:
        raw = chat(
            cfg,
            [{"role": "user", "content": build_prompt(candidate, vacancy, answers)}],
            system=SYSTEM,
            max_tokens=MAX_TOKENS,
            # Та же псевдо-статья расхода, что и у остального быстрого
            # режима: в «Расходе AI» это одна строка, а не две.
            employee_id="quick_screening",
            employee_name="Быстрый режим (кандидаты)",
            feature="candidate_profile",
        )
    except Exception as exc:
        log.warning("candidate_profile: запрос к модели не удался для %s: %s", candidate.id, exc)
        return None

    profile = _parse(raw or "")
    if not profile:
        log.warning("candidate_profile: модель вернула неразбираемый ответ для %s: %r",
                    candidate.id, (raw or "")[:200])
        return None

    try:
        candidate.profile_json = json.dumps(profile, ensure_ascii=False)
        candidate.profile_generated_at = datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()
        log.warning("candidate_profile: не удалось сохранить сводку по %s", candidate.id,
                    exc_info=True)
        return None
    return profile


def format_for_notification(profile: dict | None) -> str:
    """Короткий блок для телеграм-уведомления админу."""
    if not profile:
        return ""
    label = {"invite": "✅ звонить", "reserve": "🔶 в резерв",
             "reject": "❌ не подходит"}.get(profile.get("recommendation"), "")
    head = " · ".join(x for x in (
        f"{profile['score']}/100" if profile.get("score") is not None else "", label) if x)
    lines = [f"<b>Оценка ИИ:</b> {head}" if head else "<b>Оценка ИИ</b>"]
    if profile.get("summary"):
        lines.append(profile["summary"])
    for mark, key in (("+", "strengths"), ("⚠", "red_flags")):
        for item in (profile.get(key) or [])[:3]:
            lines.append(f"{mark} {item}")
    return "\n".join(lines)
