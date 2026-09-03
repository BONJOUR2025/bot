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

# Разбор резюме идёт не на общей модели бота. По умолчанию в конфиге стоит
# gpt-4.1-nano — она дёшева и годится для реплик в чате, но рубрику из пяти
# полос не удерживает: «готова обучиться» клала в 0 вместо 20-39, швейное
# дело — в 10 при том, что сама называла его профильным, и выдумывала
# нарушения жёстких условий. На тех же шести кандидатах nano/mini/4.1 дали
# 10/20/60, 0/30/45 и 70/60/90 — с ростом модели ответы сходятся к рубрике.
# Кандидатов единицы в день, поэтому дороже здесь дешевле.
MODEL = "openai/gpt-4.1"

# Хватает на сводку, сильные стороны, риски и вопросы к звонку. Было 900 —
# с появлением to_ask ответ перестал помещаться и обрывался на середине
# JSON, а недоразобранный ответ означает карточку вообще без сводки.
MAX_TOKENS = 1400

RECOMMENDATIONS = ("invite", "reserve", "reject")

# Вердикт выводится из балла, а не берётся у модели. Своим вердиктом она
# распоряжалась плохо и независимо от собственного же балла: сапожнику из
# Петербурга поставила 0 и «нарушено условие по месту проживания», другому
# кандидату — reject за «отсутствие гражданства РФ», хотя в жёстких
# условиях вакансии стоит только город. Балл при этом ложится в полосы
# рубрики предсказуемо, поэтому решает он.
# «Звонить» — это короткий список, а не половина воронки. На пороге 60
# приглашённых оказалось 54 из 104: полосу 60-79 занимает любой смежный
# ручной труд, а на вакансию с обучением такой опыт есть почти у всех.
# 75 отсекает по профильному опыту и оставляет два десятка.
INVITE_FROM = 75
RESERVE_FROM = 25  # ниже — человек не хочет работать руками

# Возраст, пол, гражданство и национальность в промпт не попадают вовсе —
# см. build_prompt. Раньше они подавались на вход, а на выходе стоял запрет
# их упоминать: запрет держал формулировки, но не балл, и возраст всё равно
# открывал сводку («кандидат 36 лет»). Один раз модель поставила «возраст»
# красным флагом 65-летнему мастеру с 26 годами стажа по профилю — ровно
# тому, кого надо звать. Проще не давать эти поля, чем запрещать выводы.
SYSTEM = """Ты — помощник рекрутера. Тебе дают текст вакансии, анкету
кандидата с работного сайта и его ответы на вопросы бота. Составь короткую
сводку для рекрутера, который решает, звонить ли этому человеку.

ЧЕМ РУКОВОДСТВОВАТЬСЯ
- Требования берёшь из текста вакансии, а не из её заголовка. Если вакансия
  обещает обучение — отсутствие профильного опыта не является недостатком.
- Опирайся ТОЛЬКО на приведённые данные, ничего не додумывай.
- Отличай «нет опыта» от «про опыт не сказано». Про второе никогда не пиши,
  что опыта нет, и не снижай за это балл — вместо этого добавь пункт в
  to_ask, чтобы рекрутер спросил на звонке.
- Ответы кандидата важнее анкеты: анкета описывает прошлое, ответы — то,
  что человек говорит про эту вакансию сейчас.
- Пиши по-русски, по делу, без канцелярита и без похвал.

КАК СЧИТАТЬ БАЛЛ (0-100)
Сначала выбери полосу по самому сильному опыту ручной работы. Опыт,
названный кандидатом в ответах, — такое же свидетельство, как строка в
анкете: «ремонтировал сумки» означает профильный опыт, даже если в анкете
этого нет.
- 80-100 — профильный опыт от двух лет;
- 60-79 — профильный опыт меньше двух лет ИЛИ смежный ручной труд плюс
  готовность учиться;
- 40-59 — ручной труд есть, но далёкий от профиля;
- 20-39 — ручного труда нет, но человек готов учиться;
- 0-19 — нарушено жёсткое условие вакансии либо человек не хочет работать
  руками.
Профильное — это работа руками с кожей, обувью, сумками, тканью: швея,
закройщик, сапожник, мастер по коже, реставратор, скорняк, обувщик, а
также ремонт сумок, рюкзаков и чемоданов. Не требуй, чтобы где-то
буквально стояло «ремонт обуви»: мастер по коже с восемью годами стажа —
это профильный опыт, а не его отсутствие.
Если работа явно профильная, но сколько лет — неизвестно, ставь середину
полосы 60-79 и спроси про стаж в to_ask. Неизвестный срок не повод
опускать человека в нижние полосы.
«Желаемая должность» в анкете — это кем человек хочет работать, а не его
опыт. Опыт бери только из мест работы и из ответов: анкета с желаемой
должностью «Сапожник», пустым списком работ и подписью «малярные работы»
означает человека без профильного опыта, а не сапожника.
Затем сдвинь балл внутри полосы, не больше чем на 10 в каждую сторону:
- вверх — держится на местах работы годами, ответы показывают интерес
  именно к этой работе;
- вниз — работы меняются каждые несколько месяцев, зарплатные ожидания
  заметно выше вакансии.
Если опроса не было, не снижай за это балл: ставь по анкете и вынеси
недостающее в to_ask.

ЖЁСТКИЕ УСЛОВИЯ
Жёсткие условия — это ТОЛЬКО те, что перечислены в блоке ВАКАНСИЯ под
таким заголовком. Больше ничто жёстким условием не является: ни нехватка
опыта, ни отсутствие профильного образования, ни смена профессии. Не
называй жёстким условием то, чего в этом списке нет.
Сам ты жёсткие условия не проверяешь и отказ по ним не выставляешь. Если
видишь расхождение — например, город в анкете не тот, — напиши об этом в
red_flags, вынеси в to_ask и оставь вердикт reserve. Решает человек: он
видит анкету целиком и знает случаи, которых нет в данных.

ВЕРДИКТ
Поле recommendation заполняется по баллу, поэтому просто повтори в нём то,
что следует из полосы: 60 и выше — invite, 25-59 — reserve, ниже 25 —
reject. Ни нехватка опыта, ни город, ни смена профессии основанием для
reject не являются: они влияют на балл ровно так, как описано выше, и
больше никак. В recommendation_reason объясни балл, а не отказ.

ЧЕГО НЕ ДЕЛАТЬ
- Не выводи в red_flags то, чего просто нет в данных: пустая анкета — это
  не риск, а вопрос к звонку.
- Не рассуждай о возрасте, поле, гражданстве, национальности, семейном
  положении и внешности: по этим признакам отбирать нельзя, и в данных их
  нет.

Ответь ТОЛЬКО валидным JSON без пояснений и без markdown:
{"score": 0-100,
 "score_reason": "одно предложение, из чего сложился балл",
 "recommendation": "invite|reserve|reject",
 "recommendation_reason": "одно предложение",
 "summary": "2-4 предложения: кто это и что умеет",
 "strengths": ["подтверждённое данными, до 4"],
 "red_flags": ["реальные риски, до 4; пусто, если их нет"],
 "to_ask": ["что уточнить на звонке, до 4"],
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


def format_vacancy(vacancy) -> str:
    """Вакансия так, как её читает кандидат, плюс жёсткие условия.

    Раньше уходил только заголовок — «Мастер по ремонту обуви и сумок», — и
    модель сверялась с ним буквально: 34 отказа из 63 звучали как «нет
    опыта ремонта обуви». В описании при этом прямым текстом стоит
    «Предоставляем обучение» и «приглашаем кандидатов с опытом ручной
    работы, которые хотят освоить профессию». Критерий отбора оказывался
    строже самой вакансии.
    """
    if vacancy is None:
        return ""
    parts = []
    if getattr(vacancy, "title", ""):
        parts.append(f"Должность: {vacancy.title}")
    desc = re.sub(r"\n{3,}", "\n\n", str(getattr(vacancy, "description", "") or "")).strip()
    if desc:
        parts.append("Текст вакансии:\n" + desc[:4000])

    breakers = []
    raw = getattr(vacancy, "deal_breakers_json", None)
    if raw:
        try:
            for b in json.loads(raw) or []:
                label = str(b.get("label") or "").strip()
                value = str(b.get("value") or "").strip()
                if label and value:
                    breakers.append(f"- {label}: {value}")
                elif label or value:
                    breakers.append(f"- {label}{value}")
        except (ValueError, TypeError, AttributeError):
            pass
    if breakers:
        parts.append("Жёсткие условия (их нарушение — единственная причина "
                     "для reject):\n" + "\n".join(breakers))
    return "\n\n".join(parts)


def build_prompt(candidate, vacancy, answers: list) -> str:
    """Вход модели.

    Возраст, пол и гражданство сюда не кладутся сознательно: это признаки,
    по которым отбирать нельзя, и убрать их из входа надёжнее, чем
    запрещать выводы на выходе.
    """
    parts = []
    vac = format_vacancy(vacancy)
    if vac:
        parts.append("ВАКАНСИЯ:\n" + vac)
    parts.append("КАНДИДАТ:\n" + f"Имя: {getattr(candidate, 'name', '') or '—'}")

    resume = format_resume(candidate.resume_profile())
    parts.append("АНКЕТА С САЙТА:\n"
                 + (resume or "не получена — на площадке анкеты нет. Это отсутствие "
                              "сведений, а не отсутствие опыта."))

    replies = format_answers(answers)
    parts.append("ОТВЕТЫ НА ВОПРОСЫ БОТА:\n"
                 + (replies or "опрос не пройден — оценивай по одной анкете и отметь "
                               "в to_ask, что мотивацию надо выяснить на звонке."))
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
    if score is not None:
        rec = ("invite" if score >= INVITE_FROM
               else "reserve" if score >= RESERVE_FROM
               else "reject")
    return {
        "score": score,
        "score_reason": str(data.get("score_reason") or "")[:400],
        "recommendation": rec if rec in RECOMMENDATIONS else None,
        "recommendation_reason": str(data.get("recommendation_reason") or "")[:400],
        "summary": str(data.get("summary") or "")[:1500],
        "strengths": [str(x)[:200] for x in (data.get("strengths") or [])][:6],
        "red_flags": [str(x)[:200] for x in (data.get("red_flags") or [])][:6],
        # Неизвестное вместо красного флага: пустая анкета — это вопрос к
        # звонку, а не риск, и раньше модель писала «опыт не подтверждён» в
        # минусы кандидату, у которого просто не было резюме.
        "to_ask": [str(x)[:200] for x in (data.get("to_ask") or [])][:4],
        "salary_expectation": str(data.get("salary_expectation") or "")[:120],
        "availability": str(data.get("availability") or "")[:120],
        "tags": [str(x)[:40] for x in (data.get("tags") or [])][:5],
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
            model=MODEL,
            max_tokens=MAX_TOKENS,
            # Балл должен быть воспроизводим: на провайдерской температуре
            # одно и то же резюме получало 30, 53, 50, 60 и 39 в пяти
            # прогонках подряд, и сравнивать кандидатов по такому числу
            # нельзя.
            temperature=0,
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

    # На чём собрана сводка. Оценка по одной анкете — не то же самое, что
    # оценка после опроса, и в карточке это должно быть видно: иначе
    # уверенный балл по кандидату, который не сказал ни слова, читается
    # так же, как балл по прошедшему опрос.
    profile["basis"] = {
        (True, True): "resume+answers",
        (True, False): "resume",
        (False, True): "answers",
        (False, False): "none",
    }[(bool(candidate.resume_profile()), bool(answers))]

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
