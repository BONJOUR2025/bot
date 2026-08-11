"""Сообщения кандидату, которые инициирует человек, а не бот.

Два случая, оба про один и тот же момент — рекрутёр разбирает воронку руками:

* **не дозвонился** — вместо того чтобы вслепую перезванивать, пишем в чат
  «когда вам удобно»; кандидат отвечает текстом, и следующий звонок уже по
  назначенному времени;
* **отказ** — кандидату уходит текст отказа, а не молчаливое исчезновение.

Почему это отдельный модуль, а не пара функций в роутере:

* отправка одинакова для hh и Авито, но адресуется по-разному (hh — по
  negotiation id, Авито — по chat id), и эта развилка не должна расползаться
  по вызывающим;
* расписание часов общения (candidate_hours) здесь намеренно **не**
  проверяется. Оно сдерживает автоматическую цепочку бота, а тут человек
  нажал кнопку и ждёт результата — молча придержать его сообщение до утра
  значило бы соврать интерфейсом. Раз рекрутёр работает в 21:00, писать в
  21:00 нормально;
* попытка дозвона фиксируется независимо от отправки: как раз тем, кому
  звонят, чата может не быть вовсе (отклик Авито «by_call» — только телефон),
  и терять из-за этого учёт звонков нельзя.
"""
from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)

DEFAULT_NO_ANSWER_MESSAGE = (
    "Здравствуйте! Пробовали до вас дозвониться, но не получилось. "
    "Подскажите, когда вам удобно поговорить?"
)

DEFAULT_REJECTION_MESSAGE = (
    "Здравствуйте! К сожалению, ваша кандидатура не подошла для данной вакансии. "
    "Спасибо за проявленный интерес, желаем удачи в поиске работы!"
)


def has_chat(candidate) -> bool:
    """Есть ли куда писать. Для Авито чат существует не всегда."""
    if candidate.source == "hh":
        return bool(candidate.external_id)
    if candidate.source == "avito":
        return bool((candidate.platform_chat_id or "").strip())
    return False


async def send_to_candidate(db, candidate, src, token: str, text: str) -> None:
    """Отправить сообщение в переписку на площадке и записать его в карточку.

    Бросает исключение площадки как есть: вызывающий показывает оператору,
    что именно пошло не так, — «отправлено» без отправки хуже ошибки.
    """
    from app.services import avito_api, hh_api, quick_screening

    text = (text or "").strip()
    if not text:
        raise ValueError("Пустой текст сообщения")

    if candidate.source == "avito":
        await avito_api.send_message(token, src.employer_id, candidate.platform_chat_id, text)
    else:
        await hh_api.send_message(token, candidate.external_id, text)

    quick_screening.record_last_message(db, candidate, text, "employer")


def register_call_attempt(db, candidate, *, now: datetime | None = None) -> int:
    """Записать неудачную попытку дозвона. Возвращает их общее число.

    Хранится в follow_up_count/follow_up_last_sent_at — колонках, оставшихся
    от вырезанной телеграм-воронки. Они пустые у всех кандидатов (проверено
    на боевой базе), а смысл «повторный контакт после неудачной попытки»
    совпадает, так что заводить ещё пару колонок того же назначения незачем.
    """
    candidate.follow_up_count = (candidate.follow_up_count or 0) + 1
    candidate.follow_up_last_sent_at = now or datetime.utcnow()
    db.commit()
    return candidate.follow_up_count


def reset_call_attempts(db, candidate) -> None:
    """Дозвонились — счётчик и флаг обнуляются."""
    candidate.follow_up_count = 0
    candidate.follow_up_last_sent_at = None
    db.commit()
