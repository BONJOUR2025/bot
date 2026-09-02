"""Background sync: pulls new candidates from hh.ru and Avito into the CRM."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_deferred_task: asyncio.Task | None = None
_DEFAULT_INTERVAL = 15 * 60  # fallback 15 min; actual per-source interval used inside loop

# How many candidates to name in a "новые отклики" notification before
# summarising the rest (Telegram caps a message at 4096 characters).
_NOTIFY_LIST_LIMIT = 15


async def _sync_once() -> None:
    from app.db.session import SessionLocal
    from app.models.recruitment import RecruitmentSource, VacancyLink, Candidate
    from app.services import hh_api, avito_api

    db = SessionLocal()
    try:
        sources = db.query(RecruitmentSource).filter(RecruitmentSource.is_active == True).all()
        for src in sources:
            links = db.query(VacancyLink).filter(
                VacancyLink.source_id == src.id,
                VacancyLink.sync_enabled == True,
            ).all()
            if not links:
                continue

            token = src.access_token
            if src.source == "avito" and src.client_id and src.client_secret:
                try:
                    tok_data = await avito_api.get_token(src.client_id, src.client_secret)
                    token = tok_data["access_token"]
                    src.access_token = token
                    db.commit()
                except Exception as e:
                    logger.warning(f"[Sync] Avito token refresh failed: {e}")
                    continue
            elif src.source == "hh":
                token = await _refresh_hh_token_if_needed(db, src) or token

            for link in links:
                try:
                    # Captured before _sync_link stamps it: on the very first
                    # run everything imported is a backlog, not today's news,
                    # and saying "+67 новых откликов" about two-year-old chats
                    # would be plainly misleading.
                    is_first_sync = link.last_synced_at is None
                    new_candidates = await _sync_link(db, src, link, token)
                    new_count = len(new_candidates)
                    link.last_synced_at = datetime.utcnow()
                    link.last_sync_count = new_count
                    src.last_error = ""
                    db.commit()
                    if new_count:
                        logger.info(f"[Sync] {src.source} vacancy={link.external_vacancy_id}: +{new_count} candidates")
                        await _notify_new_candidates(src.source, link, new_candidates, backlog=is_first_sync)
                except Exception as e:
                    logger.warning(f"[Sync] {src.source} link {link.id} error: {e}")
                    src.last_error = str(e)
                    db.commit()

            # Poll hh.ru messages for active candidates
            if src.source == "hh" and token:
                try:
                    await _check_hh_messages(db, src, token)
                except Exception as e:
                    logger.warning(f"[Sync] hh message check failed: {e}")

            # Poll Avito chats, but only for candidates in an active quick screen
            if src.source == "avito" and token:
                try:
                    await _check_avito_messages(db, src, token)
                except Exception as e:
                    logger.warning(f"[Sync] avito message check failed: {e}")

        # Проверки «TG не привязан 24ч» здесь больше нет: она искала этап
        # «ждем_привязки», которого в воронке не существует с тех пор, как
        # привязку к Telegram вырезали вместе со старым интервью-флоу. То
        # есть код отрабатывал вхолостую на каждом цикле и не мог сработать
        # никогда.

        # Alert on quick-screen candidates who went silent for 24h
        try:
            from app.services import quick_screening
            await quick_screening.check_silence(db)
        except Exception as e:
            logger.warning(f"[Sync] quick screening silence check error: {e}")
    finally:
        db.close()


# Refresh this far ahead of the recorded expiry. hh access tokens live ~14 days,
# so a 1-day margin means a normally-running sync always renews well before the
# token dies, and a box that was off for a few days still recovers on first run.
_HH_REFRESH_MARGIN = timedelta(days=1)

# Re-notify guard: without it a source whose refresh_token is genuinely dead
# (needs manual re-auth) would alert on every single sync cycle.
_hh_refresh_failure_notified = False


async def _refresh_hh_token_if_needed(db, src) -> str | None:
    """Renew the hh access token before it expires, returning the token to use.

    hh_api.refresh_access_token() existed from the start but was never called
    anywhere — so the token simply died every ~2 weeks and the whole hh
    integration went silent (found in production as a 403 on every sync, with
    a token that had expired a month earlier and nobody noticed). Returns None
    if nothing was refreshed, so the caller keeps the existing token.
    """
    global _hh_refresh_failure_notified
    from app.services import hh_api
    from app.services.notify import send_notification

    if not src.refresh_token:
        return None
    expires_at = src.token_expires_at
    if expires_at and expires_at - _HH_REFRESH_MARGIN > datetime.utcnow():
        return None  # still comfortably valid

    try:
        data = await hh_api.refresh_access_token(
            src.client_id or "", src.client_secret or "", src.refresh_token
        )
    except Exception as e:
        logger.warning("[Sync] hh token refresh failed: %s", e)
        src.last_error = f"Не удалось обновить токен hh.ru: {e}"
        db.commit()
        if not _hh_refresh_failure_notified:
            _hh_refresh_failure_notified = True
            await send_notification(
                "🛠 <b>СБОЙ · hh.ru не обновил токен</b>\n"
                "Отклики с hh.ru не загружаются. Переподключите hh.ru в разделе «Подбор» "
                f"— требуется повторная авторизация.\n\nОшибка: {e}"
            )
        return None

    _hh_refresh_failure_notified = False
    token = data.get("access_token")
    if not token:
        return None
    src.access_token = token
    # hh rotates the refresh token on every use — keeping the old one would
    # make the *next* refresh fail with an already-used token.
    if data.get("refresh_token"):
        src.refresh_token = data["refresh_token"]
    if data.get("expires_in"):
        src.token_expires_at = datetime.utcnow() + timedelta(seconds=int(data["expires_in"]))
    src.last_error = ""
    db.commit()
    logger.info("[Sync] hh token refreshed, valid until %s", src.token_expires_at)
    return token


async def _notify_new_candidates(source: str, link, candidates: list[dict], backlog: bool = False) -> None:
    from app.services.notify import send_notification
    src_label = "hh.ru" if source == "hh" else "Авито"
    vac_title = (getattr(link, "external_vacancy_title", "") or "") or \
                (link.vacancy.title if getattr(link, "vacancy", None) else "") or \
                f"#{link.external_vacancy_id}"
    count = len(candidates)
    word = "кандидат" if count == 1 else "кандидата" if count < 5 else "кандидатов"
    if backlog:
        lines = [
            f"⚪ <b>Импорт истории ({src_label})</b>\n{vac_title}: загружено {count} {word}\n"
            f"Это накопившиеся отклики, а не новые — бот им не писал.\n"
        ]
    else:
        lines = [f"⚪ <b>Новые отклики ({src_label})</b>\n{vac_title}: +{count} {word}\n"]
    # The first sync of a link imports the whole backlog at once — 76 chats on
    # the live Avito account. Listing every one of them blows past Telegram's
    # 4096-character message limit, so the message would simply fail to send
    # and the admin would learn nothing. Show a sample and state the rest.
    for c in candidates[:_NOTIFY_LIST_LIMIT]:
        age_str = f", {c['age']} лет" if c.get("age") else ""
        phone_str = f"\n📞 {c['phone']}" if c.get("phone") else ""
        resume_str = f"\n🔗 <a href=\"{c['resume_url']}\">Резюме</a>" if c.get("resume_url") else ""
        lines.append(f"• <b>{c['name']}</b>{age_str}{phone_str}{resume_str}")
    if count > _NOTIFY_LIST_LIMIT:
        lines.append(f"\n…и ещё {count - _NOTIFY_LIST_LIMIT} — смотрите в разделе «Подбор».")
    await send_notification("\n".join(lines))


def _naive_utc(dt):
    """Дата без часового пояса, в UTC.

    hh отдаёт даты со смещением («2026-08-12T16:59:01+0300»), Авито — без
    него, а last_synced_at пишется как datetime.utcnow(), то есть тоже без.
    Сравнение aware с naive в Python — это TypeError, и он утопил весь
    импорт hh: исключение ловилось общим `except` уровнем выше и оседало
    строчкой «hh link 3 error: can't compare offset-naive and offset-aware
    datetimes», после чего кандидаты успевали создаться, а опрос им уже не
    запускался. Поэтому приводим к общему виду, а не надеемся на удачу.
    """
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def is_new_arrival(applied_at, last_synced_at) -> bool:
    """Действительно ли этот человек написал только что.

    «Новый для базы» и «новый вообще» — разные вещи, и путать их дорого:
    задним числом в импорт может влиться пласт старых людей (так вышло, когда
    источники Авито объединили и к формальным откликам добавились 40 чатов
    месячной давности). Рассылать им приветствие только потому, что мы
    поменяли импорт, нельзя.

    Без даты отклика считаем человека старым: доказать обратное нечем, а
    цена ошибки несимметрична — промолчать не страшно, написать зря стыдно.
    """
    if not applied_at:
        return False
    if not last_synced_at:
        return False
    return _naive_utc(applied_at) >= _naive_utc(last_synced_at)


def should_poll_messages(candidate) -> bool:
    """Нужно ли тянуть новые сообщения по этому кандидату.

    Отбор строится на состоянии переписки, а не на названии этапа: этапы уже
    один раз переименовали, и опрос из-за этого замолчал целиком (см. большой
    комментарий в _check_hh_messages).

    Опрашиваем три случая, и все три — это «от человека ещё может прийти
    сообщение»: опрос идёт (`asking`), опрос завершён (`done` — как раз
    «Ответил»/«Думает», где и ждёшь «я согласен»), опрос не запускался
    (`None` — переписку ведут руками). Не опрашиваем только промежуточные
    состояния вроде `queued`/`waiting_admin`, где ход не за кандидатом.

    Живёт отдельной функцией, потому что раньше тест держал у себя копию
    этого условия — и такая копия уже однажды позволила боевому багу
    проехать мимо зелёных тестов.
    """
    from app.services import quick_screening

    return quick_screening.load_state(candidate).get("status") in ("asking", "done", None)


async def _check_hh_messages(db, src, token: str) -> None:
    """Poll hh.ru messages for active candidates, notify on new applicant messages."""
    from app.models.recruitment import Candidate
    from app.services import hh_api
    from app.services.notify import send_notification
    from app.db.session import SessionLocal

    from app.services import quick_screening, recruitment_stages as rs

    cutoff = datetime.utcnow() - timedelta(days=60)
    # Раньше здесь стоял фильтр по этапу (_ACTIVE_STAGES со старыми названиями
    # «отклик»/«ждем»). После перехода на воронку «5 этапов» новые кандидаты
    # получают этап «новый», в старый список он не входит — и опрос сообщений
    # hh замолчал полностью: 27 кандидатов с запущенным опросом ждали ответа,
    # а лог невинно писал «0 active candidates to poll». У Авито поломку
    # маскировали вебхук и отдельный путь опроса, у hh других путей нет.
    #
    # Поэтому фильтруем по состоянию переписки, а не по названию этапа: так
    # это переживёт любое следующее переименование этапов.
    candidates = db.query(Candidate).filter(
        Candidate.source == "hh",
        Candidate.external_id.isnot(None),
        Candidate.stage.notin_(rs.TERMINAL_STAGES),
        Candidate.created_at >= cutoff,
    ).all()
    # Опрашиваем тех, у кого идёт быстрый опрос, либо тех, у кого переписка
    # ведётся вручную (опрос не запускался или уже завершён) — во втором
    # случае входящее превращается в обычное уведомление админу.
    #
    # Условие «завершён» тут раньше отсутствовало: код проверял только
    # «не запускался», хотя комментарий обещал оба случая. Из-за этого
    # кандидаты в «Ответил» выпадали из опроса совсем — а это ровно те, от
    # кого ждёшь «я согласен» после звонка. С этапом «Думает» цена такой
    # тишины стала очевидной, поэтому фильтр приведён к обещанному смыслу:
    # не опрашиваем только тех, кто прямо сейчас в середине опроса и ждёт
    # своей очереди в другом состоянии.
    candidates = [c for c in candidates if should_poll_messages(c)]

    logger.info("[Sync] hh message check: %d active candidates to poll", len(candidates))

    sem = asyncio.Semaphore(3)

    async def check_one(cand_id: int, neg_id: str, name: str, last_id: str | None) -> None:
        async with sem:
            try:
                messages = await hh_api.get_messages(token, neg_id)
                logger.info("[Sync] hh messages neg=%s candidate=%s: %d messages, last_msg_id=%r",
                            neg_id, name, len(messages), last_id)
                if not messages:
                    return
                latest = max(messages, key=lambda m: m["created_at"])
                latest_id = latest["id"]
                latest_type = latest["author_type"]
                logger.info("[Sync] hh latest msg: id=%s type=%s text=%r",
                            latest_id, latest_type, latest["text"][:60])

                # Update last_msg_id in its own session to avoid concurrency issues
                own_db = SessionLocal()
                try:
                    c = own_db.query(Candidate).filter(Candidate.id == cand_id).first()
                    if not c:
                        return
                    if latest_type != "applicant":
                        c.last_msg_id = latest_id
                        own_db.commit()
                        return
                    if c.last_msg_id == latest_id:
                        logger.debug("[Sync] hh msg already seen: %s", latest_id)
                        return
                    # New message from applicant — save ID before notifying
                    c.last_msg_id = latest_id
                    own_db.commit()
                finally:
                    own_db.close()

                msg_text = latest["text"].strip()
                if not msg_text:
                    logger.info("[Sync] hh new applicant message from %s has empty text, skipping notification", name)
                    return

                # A candidate mid-quick-screen gets their reply consumed by the
                # screening state machine (which sends its own, richer alerts)
                # instead of the generic "новое сообщение" ping.
                if await _route_to_quick_screening(cand_id, src, token, msg_text, latest_id):
                    return

                logger.warning("[Sync] hh NEW applicant message from %s (neg=%s), attempting notification", name, neg_id)
                ok = await send_notification(
                    f"🔴 <b>НУЖЕН ОТВЕТ · Сообщение от кандидата (hh.ru)</b>\n"
                    f"<b>{name}</b>: {msg_text[:200]}"
                )
                if ok:
                    logger.info("[Sync] hh notification sent for %s", name)
                else:
                    logger.warning("[Sync] hh notification FAILED for %s — check notification_chat_id and bot token", name)
            except Exception as exc:
                logger.warning("[Sync] hh message check failed for neg=%s (%s): %s", neg_id, name, exc)

    await asyncio.gather(*[
        check_one(c.id, c.external_id, c.name, c.last_msg_id)
        for c in candidates
    ])


async def _route_to_quick_screening(cand_id: int, src, token: str,
                                     msg_text: str, msg_id: str) -> bool:
    """Feed an incoming candidate message to the quick-screening state machine.

    Returns True if the message was consumed there, so the caller skips its own
    generic notification — the screening sends its own, more useful alerts.
    Runs in its own session, matching the surrounding polling code.
    """
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate, Vacancy
    from app.services import quick_screening
    from app.services.config_service import ConfigService

    db = SessionLocal()
    try:
        c = db.query(Candidate).filter(Candidate.id == cand_id).first()
        # Только идущий опрос действительно поглощает сообщение. Раньше здесь
        # проверялось лишь наличие состояния — и ответ кандидата с уже
        # завершённым опросом уходил в handle_incoming, тот молча выходил
        # (status != "asking"), а вызывающий, увидев True, пропускал своё
        # уведомление. Сообщение исчезало целиком: ни ответа, ни алерта.
        if not c or quick_screening.load_state(c).get("status") != "asking":
            return False
        vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
        # Continuation is keyed on the candidate already having a running
        # screen, NOT on the vacancy's toggle: the toggle governs whether new
        # responses start one automatically, and a screen started by hand on a
        # single candidate must still advance when they reply.
        if not quick_screening.get_questions(vacancy):
            return False
        await quick_screening.handle_incoming(
            db, c, vacancy, src, token, msg_text, msg_id, ConfigService().load()
        )
        return True
    except Exception as e:
        logger.warning("[Sync] quick screening failed for candidate %s: %s", cand_id, e)
        return False
    finally:
        db.close()


def _iso_to_ts(raw: str | None) -> float | None:
    """Naive-UTC ISO 8601 строка → unix-время, или None если разобрать нечего.

    Общий парсер и для asked_at (пишется через datetime.utcnow().isoformat()),
    и для created_at сообщений Авито (avito_api.get_messages конвертирует их
    так же, через datetime.utcfromtimestamp(...).isoformat() — до 1fc3f0b это
    было сырое unix-время, и код ниже сравнивал числа напрямую; после смены
    формата сравнение float > str падало на каждом сообщении молча, в try/
    except, так что ни один ответ кандидата в Авито не долетал до опроса)."""
    from datetime import datetime, timezone

    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _asked_at_ts(state: dict) -> float | None:
    """Момент отправки текущего вопроса в виде unix-времени. None, если
    времени нет (старое состояние, записанное до появления отсечки) —
    тогда фильтровать не по чему и лучше вести себя как раньше, чем молча
    игнорировать все сообщения."""
    return _iso_to_ts((state or {}).get("asked_at"))


_SOURCE_LABEL = {"avito": "Авито", "hh": "hh.ru"}


async def _schedule_call_if_named(cand_id: int, name: str, text: str) -> str | None:
    """Кандидат назвал время звонка — завести задачу с напоминанием.

    Возвращает человекочитаемое время или None. Нужно потому, что назначенные
    самим кандидатом звонки держались исключительно на памяти: Бугай написал
    «Завтра в 14:00», никто не позвонил, и обнаружилось это через сутки при
    чтении переписок.

    Ошибка здесь не должна ронять уведомление: сообщить о письме важнее, чем
    завести задачу.
    """
    from app.services import call_time
    from app.services.config_service import ConfigService

    try:
        found = call_time.extract(text, ConfigService().load())
        if not found:
            return None
        d, t = found
        from app.schemas.task import TaskCreate
        from app.services.task_service import get_task_service

        await get_task_service().create_task(
            TaskCreate(
                title=f"Позвонить: {name}",
                description=f"Кандидат сам назвал время: «{text[:300]}»",
                due_date=d, due_time=t,
                category="Подбор персонала",
                priority="high",
                reminder_minutes=15,
                # Связь с кандидатом: по ней перенос задачи двигает и время
                # звонка в очереди, а очередь показывает связанную задачу.
                candidate_id=cand_id,
            ),
            created_by="Быстрый режим",
        )

        # Названное кандидатом время — это ещё и время в очереди «Прозвона».
        # Через normalize, а не напрямую: если сегодня мы уже звонили, «сегодня
        # в 18:00» уезжает на следующий допустимый день. Вето сильнее
        # договорённости — второй автоматический звонок в тот же календарный
        # день невозможен.
        from app.services import candidate_outreach

        candidate_outreach.schedule_from_task(cand_id, d, t)
        return f"{d.strftime('%d.%m')} в {t.strftime('%H:%M')}"
    except Exception as exc:
        logger.warning("не удалось завести задачу на звонок для кандидата %s: %s", cand_id, exc)
        return None


async def notify_unhandled_message(cand_id: int, name: str, text: str,
                                   msg_id: str, source: str) -> bool:
    """Сообщение, которое опрос не забрал, — довести до админа.

    Нужно потому, что «опрос закончен» не значит «разговор закончен»:
    кандидат отвечает на приглашение, пишет «когда удобно», уточняет адрес.
    Раньше у Авито такого уведомления не было вовсе — ни строчки кода, — и
    подобное сообщение оседало только в карточке. Пять человек просидели так
    полдня, включая тех, кому мы сами написали «когда вам удобно поговорить?».

    Дедупликация по Candidate.last_msg_id: помечаем ДО отправки, поэтому
    вебхук и опрос, увидев одно и то же сообщение, уведомят один раз.
    Возвращает True, если уведомление ушло.
    """
    from app.db.session import SessionLocal
    from app.models.recruitment import Candidate
    from app.services.notify import send_notification

    text = (text or "").strip()
    if not text:
        return False

    own = SessionLocal()
    try:
        c = own.query(Candidate).filter(Candidate.id == cand_id).first()
        if not c:
            return False
        if msg_id and c.last_msg_id == msg_id:
            return False  # уже уведомляли об этом сообщении
        c.last_msg_id = msg_id or c.last_msg_id
        own.commit()
    finally:
        own.close()

    label = _SOURCE_LABEL.get(source, source)
    when = await _schedule_call_if_named(cand_id, name, text)
    ok = await send_notification(
        f"🔴 <b>НУЖЕН ОТВЕТ · Сообщение от кандидата ({label})</b>\n"
        f"<b>{name}</b>: {text[:200]}"
        # Не «напоминание создано»: доставка напоминаний по задачам сейчас
        # не работает (вынесено в отдельную задачу), а обещать её в
        # уведомлении значит ровно то, из-за чего звонки и терялись.
        # Кандидат всплывёт в «Прозвоне» сам, когда наступит это время.
        + (f"\n\n📞 Договорились созвониться: <b>{when}</b>"
           f"\nКандидат появится в «Прозвоне» к этому времени."
           if when else "")
    )
    if not ok:
        logger.warning("[Sync] %s notification FAILED for %s", source, name)
    return ok


async def _check_avito_messages(db, src, token: str) -> None:
    """Poll Avito chats for candidates we may still owe an answer.

    Раньше здесь опрашивались только кандидаты с ИДУЩИМ опросом, а всё
    остальное отбрасывалось строкой `if status != "asking": continue`. Но
    разговор не заканчивается вместе с опросом, и такие сообщения не получали
    ни ответа, ни уведомления — в отличие от hh, где уведомление админу было
    с самого начала. Теперь опрашиваем по общему предикату
    should_poll_messages, а то, что опрос не забрал, уходит админу.
    """
    from app.models.recruitment import Candidate, Vacancy
    from app.services import avito_api, quick_screening

    from app.services import recruitment_stages as rs

    cutoff = datetime.utcnow() - timedelta(days=60)
    candidates = db.query(Candidate).filter(
        Candidate.source == "avito",
        Candidate.platform_chat_id.isnot(None),
        Candidate.platform_chat_id != "",
        Candidate.stage.notin_(rs.TERMINAL_STAGES),
        Candidate.created_at >= cutoff,
    ).all()
    if not candidates:
        return

    # Кого опрашивать — тем же предикатом, что и hh: опрос идёт, опрос
    # завершён, опроса не было. Раньше здесь стояло жёсткое «только asking»,
    # из-за чего половина живых разговоров была невидима.
    #
    # Отсечка по времени и по терминальным этапам — потому что Messenger API
    # Авито и лимитирован по частоте, и доступен только на «Максимальном»
    # тарифе: перебирать все 45 чатов, включая прошлогодние, ни к чему.
    watched = []
    for c in candidates:
        if not should_poll_messages(c):
            continue
        state = quick_screening.load_state(c)
        if state.get("status") == "asking":
            vacancy = db.query(Vacancy).filter(Vacancy.id == c.vacancy_id).first() if c.vacancy_id else None
            # See _route_to_quick_screening: a running screen is polled regardless
            # of the vacancy toggle, so manually-started ones keep working.
            if not quick_screening.get_questions(vacancy):
                continue
        watched.append((c.id, c.name, state.get("status") == "asking"))

    logger.info("[Sync] avito message check: %d chats to poll", len(watched))

    for cand_id, cand_name, screening in watched:
        try:
            c = db.query(Candidate).filter(Candidate.id == cand_id).first()
            messages = await avito_api.get_messages(token, src.employer_id, c.platform_chat_id)
            incoming = [m for m in messages if m["author_type"] == "applicant"]
            # Только то, что написано ПОСЛЕ заданного вопроса. Без этой отсечки
            # берётся просто последнее сообщение кандидата в чате — а переписка
            # на Авито часто тянется с прошлых откликов, и старое «Актуально?»
            # или вовсе номер телефона годичной давности засчитывались как
            # ответ на первый вопрос: кандидат молчит, а опрос едет дальше.
            # Витрина для карточки — по последнему сообщению вообще, без
            # отсечки по времени вопроса ниже: показать в воронке нужно то,
            # что реально написано последним, даже если как ответ на текущий
            # вопрос оно не засчитывается.
            if messages:
                newest = max(messages, key=lambda m: _iso_to_ts(m.get("created_at")) or 0)
                quick_screening.record_last_message(
                    db, c, newest.get("text", ""),
                    "applicant" if newest.get("author_type") == "applicant" else "employer",
                )

            if not incoming:
                continue
            newest_in = max(incoming, key=lambda m: _iso_to_ts(m.get("created_at")) or 0)

            if not screening:
                # Опрос не идёт — разговор ведёт человек, наше дело сообщить.
                # Уведомляем, только если последнее слово в чате за кандидатом:
                # если после его реплики уже ответили мы, дёргать админа не за
                # чем. get_messages отдаёт по возрастанию времени, поэтому
                # «последнее слово» — это просто последний элемент.
                if messages[-1]["author_type"] != "applicant":
                    continue
                await notify_unhandled_message(
                    cand_id, cand_name, newest_in.get("text", ""), newest_in["id"], "avito")
                continue

            asked_ts = _asked_at_ts(quick_screening.load_state(c))
            if asked_ts is not None:
                incoming = [m for m in incoming if (_iso_to_ts(m.get("created_at")) or 0) > asked_ts]
            if not incoming:
                continue
            latest = max(incoming, key=lambda m: _iso_to_ts(m.get("created_at")) or 0)
            await _route_to_quick_screening(cand_id, src, token, latest["text"], latest["id"])
        except Exception as e:
            logger.warning("[Sync] avito message check failed for candidate %s: %s", cand_id, e)


def _find_twin(db, vacancy_id: int, source: str, item: dict):
    """Карточка того же человека, заведённая по другому отклику.

    Два ключа, оба узкие намеренно:

    * `resume_id` — внутри hh. У человека одно резюме на все отклики, так
      что совпадение здесь означает того же человека наверняка.
    * нормализованный телефон — между площадками. Работает только когда
      номер известен обеим сторонам, а он есть примерно у двух третей
      карточек. Это принято сознательно: не склеить двоих дешевле, чем
      склеить разных людей.

    Имена не сравниваются вообще: тёзки на одной вакансии встречаются — в
    базе есть две «Латышевы Татьяны» с разными резюме и разными телефонами.
    """
    from app.models.recruitment import Candidate
    from app.services import candidate_merge as cm

    if source == "hh":
        resume_id = item.get("resume_id") or cm.resume_id_from_url(item.get("resume_url"))
        if resume_id:
            twin = db.query(Candidate).filter(
                Candidate.vacancy_id == vacancy_id,
                Candidate.source == "hh",
                Candidate.resume_id == resume_id,
            ).first()
            if twin is not None:
                return twin

    phone = cm.normalize_phone(item.get("phone"))
    if not phone:
        return None
    # Сравнение по нормализованному номеру не переложить в SQL: в базе
    # номера лежат как пришли, «+7 953 158-85-64» и «79531588564» — одно и
    # то же. Кандидатов на вакансию сотни, не миллионы.
    for c in db.query(Candidate).filter(Candidate.vacancy_id == vacancy_id).all():
        if cm.normalize_phone(c.phone) == phone:
            return c
    return None


def _attach_channel(candidate, source: str, external_id: str, item: dict, reason: str) -> None:
    """Записать второй отклик как дополнительную переписку карточки.

    Основной канал обычно не меняется: бот продолжает писать туда, где уже
    идёт разговор. Исключение — приход hh к карточке Авито: тогда hh
    становится основным, потому что Messenger API Авито доступен только на
    «Максимальном» тарифе и уже отваливался, а переписка в отклике hh не
    зависит ни от тарифа, ни от лимитов.
    """
    import json
    from datetime import datetime as _dt

    from app.services import candidate_merge as cm

    chat_id = item.get("platform_chat_id") or ""
    now = _dt.utcnow()
    promote = source == "hh" and candidate.source == "avito"

    if promote:
        new_channel = {
            "source": candidate.source,
            "external_id": candidate.external_id or "",
            "platform_chat_id": candidate.platform_chat_id or "",
            "added_at": now.isoformat(),
        }
        candidate.source = "hh"
        candidate.external_id = external_id
        candidate.platform_chat_id = chat_id
        if not (candidate.resume_id or "").strip():
            candidate.resume_id = (item.get("resume_id")
                                   or cm.resume_id_from_url(item.get("resume_url")))
    else:
        new_channel = {
            "source": source,
            "external_id": external_id,
            "platform_chat_id": chat_id,
            "added_at": now.isoformat(),
        }

    channels = candidate.channels()
    known = {(c.get("source"), c.get("external_id")) for c in channels}
    known.add((candidate.source, candidate.external_id or ""))
    is_new = (new_channel["source"], new_channel["external_id"]) not in known and bool(
        new_channel["external_id"] or new_channel["platform_chat_id"])
    if is_new:
        channels.append(new_channel)
        candidate.channels_json = json.dumps(channels, ensure_ascii=False)

    # Пустые поля дозаполняем: второй отклик часто несёт телефон или
    # возраст, которых в первом не было.
    for field in ("phone", "email", "resume_url", "photo_url"):
        if not (getattr(candidate, field, "") or "").strip() and item.get(field):
            setattr(candidate, field, item[field])
    if candidate.age is None and item.get("age") is not None:
        candidate.age = item["age"]

    if not is_new:
        # Импорт приходит каждые 15 минут и приносит те же отклики снова.
        # Раньше запись в аудит добавлялась безусловно, и подпись
        # «объединено откликов: N» росла на каждом синке: у Моисеева она
        # показывала 3 при двух реально объединённых откликах.
        return

    audit = candidate.merged_from()
    audit.append({
        "at": now.isoformat(),
        # Карточки не было: отклик пришёл вторым и сразу подшит, сливать
        # было нечего. Отличается от записи разового скрипта, где id есть.
        "candidate_id": None,
        "source": source,
        "external_id": external_id,
        "platform_chat_id": chat_id,
        "name": item.get("name") or "",
        "stage": "",
        "created_at": item.get("applied_at") or None,
        "reason": reason,
    })
    candidate.merged_json = json.dumps(audit, ensure_ascii=False)
    logger.info("[Sync] %s: второй отклик подшит к карточке %s (%s), причина %s",
                source, candidate.id, candidate.name, reason)


async def _sync_link(db, src, link, token: str) -> list[dict]:
    from app.models.recruitment import Candidate
    from app.services import hh_api, avito_api, recruitment_stages as rs
    from app.services import candidate_merge as cm

    if src.source == "hh":
        new_items = await _collect_hh(token, link.external_vacancy_id)
    elif src.source == "avito":
        new_items = await _collect_avito(token, src.employer_id, link.external_vacancy_id)
    else:
        return []

    new_candidates = []
    new_candidate_objs = []
    for item in new_items:
        ext_id = item["external_id"]
        exists = db.query(Candidate).filter(
            Candidate.vacancy_id == link.vacancy_id,
            Candidate.source == src.source,
            Candidate.external_id == ext_id,
        ).first()
        # У Авито два источника с разными external_id: формальный отклик
        # адресуется id заявки, чат — id чата. Один и тот же человек,
        # пришедший обоими путями, без этой проверки получил бы две карточки.
        # Совпадение по чату надёжнее: чат у пары «мы ↔ кандидат» один.
        if not exists and (item.get("platform_chat_id") or "").strip():
            exists = db.query(Candidate).filter(
                Candidate.vacancy_id == link.vacancy_id,
                Candidate.source == src.source,
                Candidate.platform_chat_id == item["platform_chat_id"],
            ).first()
            if exists and exists.external_id == exists.platform_chat_id and ext_id != exists.external_id:
                # Пришёл формальный отклик к карточке, заведённой из чата
                # (у такой external_id совпадает с id чата). Переносим на неё
                # данные, которых в мессенджере нет.
                #
                # Имя тоже: мессенджер отдаёт имя аккаунта, а отклик —
                # настоящие ФИО. Из-за этого «Бутте Роман Валерьевич» лежал
                # в воронке как «Олег», и найти его по фамилии было нельзя.
                if item.get("name"):
                    exists.name = item["name"]
                exists.external_id = ext_id
                exists.phone = exists.phone or item.get("phone", "")
                exists.age = exists.age or item.get("age")
                exists.resume_url = exists.resume_url or item.get("resume_url", "")
                exists.notes = item.get("notes") or exists.notes
                logger.info("[Sync] avito: карточка из чата дополнена откликом — %s", exists.name)
        # Тот же человек, но с другого нашего объявления. external_id —
        # это id ОТКЛИКА: откликнувшись на две наши вакансии, кандидат
        # получал два отклика, два чата и две карточки, и бот вёл с ним два
        # опроса сразу, задавая одни и те же вопросы в разных чатах.
        # Ключи, по которым это ловится, — в candidate_merge.
        if not exists:
            twin = _find_twin(db, link.vacancy_id, src.source, item)
            if twin is not None:
                _attach_channel(
                    twin, src.source, ext_id, item,
                    cm.REASON_RESUME if src.source == twin.source else cm.REASON_PHONE)
                exists = twin
        if exists:
            # Дозаполняем chat_id у уже импортированных: без него вебхук hh
            # (он приходит с chat_id, а не с id отклика) не сопоставить с
            # кандидатом, а все существующие записи созданы до того, как мы
            # начали его сохранять.
            if not (exists.platform_chat_id or "").strip() and item.get("platform_chat_id"):
                exists.platform_chat_id = item["platform_chat_id"]
            # Ключ дедупликации проставляем и задним числом: карточки,
            # импортированные до появления колонки, иначе продолжали бы
            # плодить близнецов.
            if src.source == "hh" and not (exists.resume_id or "").strip():
                exists.resume_id = (item.get("resume_id")
                                    or cm.resume_id_from_url(item.get("resume_url")))
            # Анкету перезаписываем на каждом синке: кандидат правит резюме,
            # и снимок месячной давности хуже свежего.
            if item.get("resume_profile"):
                exists.resume_profile_json = json.dumps(item["resume_profile"],
                                                        ensure_ascii=False)
        if not exists:
            applied_at = None
            raw_applied = item.get("applied_at")
            if raw_applied:
                try:
                    applied_at = datetime.fromisoformat(raw_applied.replace("Z", "+00:00"))
                except Exception:
                    pass

            c = Candidate(
                vacancy_id=link.vacancy_id,
                name=item["name"],
                phone=item.get("phone", ""),
                email=item.get("email", ""),
                source=src.source,
                external_id=ext_id,
                resume_url=item.get("resume_url", ""),
                photo_url=item.get("photo_url", ""),
                age=item.get("age"),
                # Название этапа берём из воронки, а не строкой: раньше здесь
                # был «отклик» из старой воронки, и каждый импортированный
                # кандидат до ближайшего рестарта (когда отрабатывает миграция
                # этапов) лежал в БД с этапом, которого в воронке уже нет.
                stage=rs.STAGE_NEW,
                notes=item.get("notes", ""),
                # Куда отвечать (Авито) и по чему искать кандидата из вебхука
                # (обе площадки). У hh ответ уходит в negotiation по
                # external_id, но chat_id всё равно нужен для вебхука.
                platform_chat_id=item.get("platform_chat_id", ""),
                resume_id=(item.get("resume_id")
                           or cm.resume_id_from_url(item.get("resume_url"))),
                resume_profile_json=(json.dumps(item["resume_profile"], ensure_ascii=False)
                                     if item.get("resume_profile") else None),
                created_at=applied_at or datetime.utcnow(),
            )
            db.add(c)
            new_candidates.append({
                "name": item["name"],
                "age": item.get("age"),
                "phone": item.get("phone", ""),
                "resume_url": item.get("resume_url", ""),
            })
            new_candidate_objs.append(c)
    db.flush()

    if not new_candidate_objs:
        return new_candidates

    # A vacancy in "быстрый режим" is screened right here on the job board and
    # never invited to Telegram, so it must not also go through the automation
    # that sends the Telegram-link message — the two flows would talk over each
    # other in the same chat.
    from app.models.recruitment import Vacancy
    from app.services import quick_screening

    vacancy = db.query(Vacancy).filter(Vacancy.id == link.vacancy_id).first() if link.vacancy_id else None
    if quick_screening.is_quick_mode(vacancy):
        # First sync of a link imports the entire existing backlog — on Avito
        # that is every open chat on the vacancy (44 real people at the time
        # this was written). Writing to all of them because we happened to
        # connect the integration today would be indefensible, so the first
        # pass only records them; screening starts with genuinely new arrivals.
        if link.last_synced_at is None:
            logger.info(
                "[Sync] first sync for link %s: imported %d existing candidates without screening",
                link.id, len(new_candidate_objs),
            )
            return new_candidates

        # «Новый для базы» и «новый вообще» — разные вещи, и путать их дорого.
        # Проверка выше ловит только самый первый синк связки; но задним
        # числом в импорт может влиться и целый пласт старых людей — так
        # случилось, когда источники Авито объединили и к формальным откликам
        # добавились 40 чатов месячной давности, включая организации и чат с
        # именем «пользователь». Разослать им «вы ещё в поиске работы?» было
        # бы ровно тем, что запрещает абзац выше, просто на другом поводе.
        #
        # Поэтому опрос начинаем только тем, кто написал ПОСЛЕ прошлой
        # синхронизации: остальные просто появляются в воронке, и решение по
        # ним принимает человек.
        fresh = [c for c in new_candidate_objs
                 if is_new_arrival(c.created_at, link.last_synced_at)]
        backlog = len(new_candidate_objs) - len(fresh)
        if backlog:
            logger.info("[Sync] link %s: %d кандидатов из прошлого импортированы без опроса",
                        link.id, backlog)
        for cand_obj in fresh:
            try:
                await quick_screening.start_screening(db, cand_obj, vacancy, src, token)
            except Exception as e:
                logger.warning("[Sync] quick screening start failed for candidate %s: %s", cand_obj.id, e)
        return new_candidates

    return new_candidates


async def _collect_avito(token: str, employer_id: str, vacancy_id: str) -> list[dict]:
    """Applicants for an Avito vacancy: формальные отклики ПЛЮС чаты.

    Раньше здесь стоял выбор одного источника: пробуем платный API откликов,
    а при 402 откатываемся на чаты мессенджера. Это оказалось ловушкой.
    Пока подписки не было, импорт шёл по чатам и заводил карточку каждому,
    кто написал. Как только «Максимальный» включили, импорт молча перешёл
    на API откликов — а тот отдаёт только формальные отклики: 7 против 67
    чатов по одному и тому же объявлению. Люди, которые просто пишут в чат
    по вакансии, перестали попадать в воронку вовсе, и заметили это лишь
    когда живые кандидаты остались без ответа.

    Поэтому теперь источники объединяются, а не выбираются. Отклик даёт
    телефон, возраст и резюме; чат даёт полноту. Дедупликация по chat_id,
    и запись из API откликов побеждает — она богаче.

    Падение платного пути больше не лишает нас чатов, и наоборот.
    """
    from app.services import avito_api

    applications: list[dict] = []
    try:
        applications = await avito_api.get_applications_for_vacancy(token, employer_id, vacancy_id)
    except ValueError as e:
        if "Максимальной подписки" not in str(e):
            raise
        logger.info("[Sync] Avito applications API unavailable (%s) — только чаты", e)
    except Exception as e:
        # Сеть или пятисотка на стороне Авито не должна стоить нам чатов.
        logger.warning("[Sync] Avito applications API failed (%s) — только чаты", e)

    try:
        chats = await avito_api.get_job_chats(token, employer_id, vacancy_id)
    except Exception as e:
        logger.warning("[Sync] Avito job chats failed (%s) — только отклики", e)
        return applications

    by_chat = {(a.get("platform_chat_id") or "").strip(): a for a in applications}
    merged = list(applications)
    added = 0
    for ch in chats:
        key = (ch.get("platform_chat_id") or "").strip()
        if key and key in by_chat:
            continue  # тот же человек, но с откликом — берём богатую запись
        merged.append(ch)
        added += 1

    logger.info("[Sync] avito vacancy=%s: откликов %d, чатов без отклика %d, всего %d",
                vacancy_id, len(applications), added, len(merged))
    return merged


async def _collect_hh(token: str, vacancy_id: str) -> list[dict]:
    from app.services import hh_api
    items = []
    page = 0
    while True:
        result = await hh_api.get_negotiations(token, vacancy_id, page=page)
        items.extend(result["items"])
        if page + 1 >= result.get("pages", 1):
            break
        page += 1
    return items


async def _run() -> None:
    while True:
        try:
            await _sync_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[Sync] Unexpected error: {e}")

        interval = _DEFAULT_INTERVAL
        try:
            from app.db.session import SessionLocal
            from app.models.recruitment import RecruitmentSource
            db = SessionLocal()
            try:
                rows = db.query(RecruitmentSource.sync_interval_minutes).filter(
                    RecruitmentSource.is_active == True
                ).all()
                if rows:
                    interval = min(r[0] for r in rows) * 60
            finally:
                db.close()
        except Exception:
            pass

        await asyncio.sleep(interval)


async def _resolve_source_and_token(db, source: str):
    """(src, token) для площадки — или None, если она не подключена."""
    from app.models.recruitment import RecruitmentSource
    from app.services import avito_api

    src = db.query(RecruitmentSource).filter(
        RecruitmentSource.source == source,
        RecruitmentSource.is_active == True,
    ).first()
    if not src:
        return None
    if source == "avito":
        if not (src.client_id and src.client_secret):
            return None
        try:
            token = (await avito_api.get_token(src.client_id, src.client_secret))["access_token"]
        except Exception as exc:
            logger.warning("[Hours] avito token failed: %s", exc)
            return None
        return src, token
    if not src.access_token:
        return None
    return src, src.access_token


# Проверяем чаще, чем идёт синхронизация: отложенное должно уходить в начале
# рабочего окна, а не через час после него.
_DEFERRED_CHECK_INTERVAL = 60


async def _deferred_run() -> None:
    """Доигрывает отложенное на нерабочие часы.

    Отдельная задача, а не часть цикла синхронизации: тот ходит раз в час,
    а обещание «продолжим, как только наступят рабочие часы» требует минутной
    точности. Первый проход — сразу при старте процесса: именно он
    восстанавливает цепочки после падения сервера.
    """
    from app.db.session import SessionLocal
    from app.services import candidate_hours, quick_screening

    while True:
        try:
            if candidate_hours.is_within():
                db = SessionLocal()
                try:
                    # Токены резолвим лениво и по одному разу на площадку.
                    cache: dict = {}

                    def resolve(source: str):
                        return cache.get(source)

                    for source in ("avito", "hh"):
                        resolved = await _resolve_source_and_token(db, source)
                        if resolved:
                            cache[source] = resolved
                    if cache:
                        done = await quick_screening.flush_deferred(db, resolve)
                        if done:
                            logger.info("[Hours] доиграно отложенных диалогов: %d", done)
                finally:
                    db.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Hours] deferred flush error: %s", exc)
        await asyncio.sleep(_DEFERRED_CHECK_INTERVAL)


def start() -> None:
    global _task, _deferred_task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run())
    _deferred_task = asyncio.create_task(_deferred_run())
    logger.info("[Sync] Recruitment sync task started")


def stop() -> None:
    global _task, _deferred_task
    if _task and not _task.done():
        _task.cancel()
    if _deferred_task and not _deferred_task.done():
        _deferred_task.cancel()


async def run_now() -> None:
    """Manual trigger: runs one sync cycle immediately."""
    await _sync_once()
