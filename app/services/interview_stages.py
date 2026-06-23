"""Data-driven interview stages (replaces the old hardcoded phase list).

Each stage is a dict: {"id", "title", "instructions", "transitions": [{"condition", "next"}, ...]}.
"id" is what gets stored in Candidate.interview_phase. "next" in a transition
is either another stage's id or the special terminal value "done", which ends
the interview and triggers profile generation.

DEFAULT_STAGES is the original built-in flow, used whenever a strategy has no
custom stages_json (i.e. every existing strategy, and any new one until an
admin edits its stage builder).
"""
import json

DEFAULT_STAGES = [
    {
        "id": "greeting",
        "title": "Приветствие",
        "instructions": (
            "Представься как HR-ассистент компании, упомяни название роли, скажи что задашь "
            "несколько вопросов для первичного знакомства (10–15 минут). Спроси готов ли кандидат."
        ),
        "transitions": [{"condition": "кандидат выразил готовность", "next": "screening"}],
    },
    {
        "id": "screening",
        "title": "Deal-breaker скрининг",
        "instructions": (
            "Проверь 2–3 критичных параметра из базы знаний (локация, формат работы, зарплатные "
            "ожидания). Задавай по одному вопросу. Если кандидат не подходит — вежливо заверши."
        ),
        "transitions": [
            {"condition": "все deal-breakers проверены и кандидат подходит", "next": "experience"},
            {"condition": "кандидат не соответствует", "next": "rejected"},
        ],
    },
    {
        "id": "experience",
        "title": "Опыт и стек",
        "instructions": (
            "Задавай открытые ситуационные вопросы: «Расскажите о проекте где...», «Что именно было "
            "сложно и как справились?» Уточняй по ответам. Задай 2–3 вопроса суммарно."
        ),
        "transitions": [{"condition": "после 2–3 вопросов", "next": "motivation"}],
    },
    {
        "id": "motivation",
        "title": "Мотивация",
        "instructions": (
            "Спроси почему меняет работу, что важно в следующем месте, цели на 1–2 года. "
            "Нейтральная позиция без осуждения."
        ),
        "transitions": [{"condition": "после ответа", "next": "candidate_questions"}],
    },
    {
        "id": "candidate_questions",
        "title": "Вопросы кандидата",
        "instructions": (
            "Скажи: «Что вам важно узнать о роли или команде?» Отвечай честно на всё что есть в "
            "базе знаний. Чего нет — «Зафиксирую, рекрутер ответит отдельно»."
        ),
        "transitions": [{"condition": "вопросы исчерпаны", "next": "closing"}],
    },
    {
        "id": "closing",
        "title": "Финал",
        "instructions": (
            "Поблагодари за время. Скажи чёткий следующий шаг: «Передам ваш профиль рекрутеру, ответ "
            "получите до [срок из базы знаний или \"в течение 2–3 рабочих дней\"]. Если появятся "
            "вопросы — пишите сюда.»"
        ),
        "transitions": [{"condition": "", "next": "done"}],
    },
    {
        "id": "rejected",
        "title": "Отказ по deal-breaker",
        "instructions": "Вежливо и честно объясни что вакансия не совпадает с условиями кандидата. Без осуждения.",
        "transitions": [{"condition": "", "next": "done"}],
    },
]


def get_stages(strategy) -> list:
    """Returns the effective stage list for a strategy: its own custom
    stages if set, otherwise the built-in default flow."""
    raw = getattr(strategy, "stages_json", None) if strategy else None
    if raw and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass
    return DEFAULT_STAGES


def render_stages_block(stages: list) -> str:
    """Render the stage list into the "ФАЗА ..." prompt block the AI reads."""
    blocks = []
    for s in stages:
        lines = [f"ФАЗА {s['id']} — {s.get('title', '')}:", (s.get('instructions') or '').strip()]
        for t in s.get("transitions") or []:
            cond = (t.get("condition") or "").strip()
            nxt = t.get("next") or "done"
            if cond:
                lines.append(f'→ next_phase: "{nxt}" когда {cond}')
            else:
                lines.append(f'→ next_phase: "{nxt}"')
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def validate_stages(stages: list) -> None:
    """Raises ValueError with a human-readable message if the stage list is malformed.

    Beyond structural checks (unique ids, valid transition targets), this also
    rejects graphs that could trap a candidate forever: every stage must have
    at least one transition, and at least one transition anywhere must lead
    to "done" — otherwise the AI is never told how to leave some stage, or
    the interview can never actually finish (no candidate profile is ever
    generated, since that's only triggered by reaching "done")."""
    if not stages:
        raise ValueError("Должен быть хотя бы один этап.")
    ids = [s.get("id", "").strip() for s in stages]
    if any(not i for i in ids):
        raise ValueError("У каждого этапа должен быть идентификатор.")
    if len(set(ids)) != len(ids):
        raise ValueError("Идентификаторы этапов должны быть уникальными.")
    valid_targets = set(ids) | {"done"}
    reaches_done = False
    for s in stages:
        if not (s.get("title") or "").strip():
            raise ValueError(f"У этапа «{s.get('id')}» должно быть название.")
        transitions = s.get("transitions") or []
        if not transitions:
            raise ValueError(
                f"У этапа «{s.get('id')}» нет ни одного перехода — разговор зависнет "
                f"на нём навсегда. Добавьте хотя бы один переход."
            )
        for t in transitions:
            nxt = (t.get("next") or "").strip()
            if not nxt:
                raise ValueError(f"У перехода в этапе «{s.get('id')}» не указан следующий этап.")
            if nxt not in valid_targets:
                raise ValueError(f"Переход на неизвестный этап «{nxt}» (в этапе «{s.get('id')}»).")
            if nxt == "done":
                reaches_done = True
    if not reaches_done:
        raise ValueError(
            "Ни один переход во всём сценарии не ведёт к завершению диалога — "
            "интервью никогда не закончится. Добавьте переход «Завершить диалог» хотя бы где-то."
        )
