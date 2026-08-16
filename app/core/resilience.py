"""Сетевой сбой не должен ронять шаг диалога.

Обработчик диалога устроен так: сначала `await message.reply_text(...)`,
потом `return СОСТОЯНИЕ`. Если отправка падает, исключение улетает в общий
error_handler, до `return` дело не доходит, и ConversationHandler не получает
новое состояние.

Для шага внутри диалога это переживаемо: состояние просто не меняется,
человек повторит действие. А вот на входе в диалог состояния ещё нет —
и диалог не открывается вовсе. Пользователь при этом не видит ни ошибки,
ни подсказки: для него бот просто промолчал. Дальше он делает то, что
собирался (например, присылает фото), а бот это уже не ждёт и обрабатывает
как случайное сообщение.

Ровно так 16.08.2026 потерялось открытие смены: фото чека дошло и сохранилось
в медиа-архив, но отметки об открытии не появилось.

Корень лечится повтором запроса (см. app/utils/tg_request.py), здесь —
страховка на случай, когда и повторы не помогли.
"""

from __future__ import annotations

from functools import wraps

from telegram.error import NetworkError

from ..utils.logger import log

# TimedOut, BadRequest и прочие — наследники TelegramError; сетевые из них
# только NetworkError и его потомки (в т.ч. TimedOut).
TRANSIENT = (NetworkError,)


def step(callback):
    """Шаг внутри диалога.

    При обрыве связи возвращаем None — PTB трактует это как «состояние
    не менять», человек остаётся на том же шаге и может повторить.
    Поведение то же, что и при необработанном исключении, но в лог попадает
    имя обработчика, а не безымянная строка из error_handler.
    """

    @wraps(callback)
    async def wrapper(update, context):
        try:
            return await callback(update, context)
        except TRANSIENT as exc:
            log(f"⚠️ [{callback.__name__}] сеть отвалилась, шаг диалога сохранён: {exc!r}")
            return None

    return wrapper


def entry(callback, state):
    """Вход в диалог.

    При обрыве связи всё равно открываем диалог в ``state``. Подсказку
    человек не увидит, но то, что он пришлёт следом, будет обработано
    по назначению, а не потеряется.
    """

    @wraps(callback)
    async def wrapper(update, context):
        try:
            return await callback(update, context)
        except TRANSIENT as exc:
            log(
                f"⚠️ [{callback.__name__}] сеть отвалилась на входе, "
                f"диалог всё равно открыт в {state}: {exc!r}"
            )
            return state

    return wrapper


def steps(*callbacks):
    """`step` для нескольких обработчиков сразу."""
    return [step(cb) for cb in callbacks]


__all__ = ["entry", "step", "steps", "TRANSIENT"]
