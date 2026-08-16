"""Повтор запросов к Telegram, когда соединение не удалось установить.

Зачем. 16.08.2026 администратор нажала «🏪 Открыть салон», ответ бота
с просьбой прислать фото не ушёл — одна `httpx.ConnectError`, единственная
за сутки. Обработчик упал на отправке, до `return AWAITING_PHOTO` дело
не дошло, диалог не открылся. Присланное следом фото чека провалилось
в общий медиа-архив, и открытие смены не зафиксировалось.

Сеть на этой машине заведомо неровная: накануне таких ошибок было 848 штук
ровным потоком, в errors.log рядом лежит `WinError 1236: подключение к сети
было разорвано локальной системой`. Значит, разовый обрыв надо переживать,
а не падать на нём.

Что важно: повторяем ТОЛЬКО те ошибки, при которых соединение не открылось,
то есть запрос гарантированно не дошёл до Telegram. Read timeout сюда
не входит — там сообщение могло быть отправлено, и повтор создал бы дубль.
PTB заворачивает httpx-исключения в свои (`raise TimedOut from err`),
поэтому исходную причину смотрим в ``__cause__``.
"""

from __future__ import annotations

import asyncio

import httpx
from telegram.error import NetworkError
from telegram.request import HTTPXRequest

from .logger import log

# Соединение не установлено => запрос не дошёл => повтор безопасен.
SAFE_TO_RETRY = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

MAX_ATTEMPTS = 3
BACKOFF_S = (0.5, 2.0)


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc.__cause__, SAFE_TO_RETRY)


class RetryingHTTPXRequest(HTTPXRequest):
    """HTTPXRequest, переживающий короткий обрыв связи."""

    async def do_request(self, url, method, *args, **kwargs):  # type: ignore[override]
        last: BaseException | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                return await super().do_request(url, method, *args, **kwargs)
            except NetworkError as exc:  # TimedOut — наследник NetworkError
                if not _is_retryable(exc):
                    raise
                last = exc
                if attempt == MAX_ATTEMPTS - 1:
                    break
                delay = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)]
                log(
                    f"⚠️ [tg] {type(exc.__cause__).__name__} на {method} {url.rsplit('/', 1)[-1]}, "
                    f"повтор {attempt + 2}/{MAX_ATTEMPTS} через {delay}с"
                )
                await asyncio.sleep(delay)
        assert last is not None
        log(f"❌ [tg] не достучались до Telegram за {MAX_ATTEMPTS} попытки: {last}")
        raise last
