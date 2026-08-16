"""Обрыв связи не должен терять шаг диалога.

История. 16.08.2026 администратор нажала «🏪 Открыть салон». Ответ бота
с просьбой прислать фото не ушёл — одна httpx.ConnectError за все сутки,
и та попала ровно в этот момент. `open_salon_start` упал на `reply_text`,
до `return AWAITING_PHOTO` дело не дошло, ConversationHandler диалог
не открыл. Фото чека, присланное через 29 секунд, обработал общий
медиа-архив, и открытие смены не зафиксировалось: у остальных пяти
администраторов в тот день файл лежит и в media_archive, и в shift_checkins,
у неё — только в первом.

Лечим в двух местах: транспорт повторяет запрос, если соединение вообще
не установилось, а обёртки вокруг обработчиков не дают диалогу развалиться,
если и повторы не помогли.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from telegram.error import BadRequest, NetworkError, TimedOut

from app.core.resilience import entry, step
from app.utils.tg_request import MAX_ATTEMPTS, RetryingHTTPXRequest, _is_retryable


def _net_error(cause: BaseException) -> NetworkError:
    """Так PTB заворачивает httpx-исключения: `raise NetworkError(...) from err`."""
    err = NetworkError(f"httpx.{type(cause).__name__}: {cause}")
    err.__cause__ = cause
    return err


class TestRetryOnlyWhenSafe:
    """Повторяем только то, что заведомо не дошло до Telegram."""

    @pytest.mark.parametrize("cause", [
        httpx.ConnectError("nope"),
        httpx.ConnectTimeout("nope"),
        httpx.PoolTimeout("nope"),
    ])
    def test_connection_never_opened_is_retryable(self, cause):
        assert _is_retryable(_net_error(cause))

    @pytest.mark.parametrize("cause", [
        httpx.ReadTimeout("сообщение могло уйти"),
        httpx.WriteTimeout("сообщение могло уйти"),
        httpx.RemoteProtocolError("сервер оборвал ответ"),
    ])
    def test_request_may_have_arrived_is_not_retryable(self, cause):
        """Иначе повтор создаст дубль: выплату, рассылку, отметку смены."""
        assert not _is_retryable(_net_error(cause))

    def test_telegram_refusals_are_not_retryable(self):
        assert not _is_retryable(BadRequest("chat not found"))


class TestRetryingTransport:
    """Подменяем сам HTTP-вызов, чтобы проверить логику повторов без сети."""

    def _run(self, monkeypatch, fail_times, cause=None):
        from telegram.request import HTTPXRequest

        calls = {"n": 0}
        cause = cause or httpx.ConnectError("boom")

        async def fake(self, url, method, *a, **kw):
            calls["n"] += 1
            if calls["n"] <= fail_times:
                raise _net_error(cause)
            return 200, b'{"ok":true}'

        monkeypatch.setattr(HTTPXRequest, "do_request", fake, raising=False)
        monkeypatch.setattr("app.utils.tg_request.BACKOFF_S", (0, 0))
        req = RetryingHTTPXRequest()
        return asyncio.run(req.do_request("https://api/sendMessage", "POST")), calls

    def test_recovers_after_one_blip(self, monkeypatch):
        (status, _), calls = self._run(monkeypatch, 1)
        assert status == 200
        assert calls["n"] == 2, "должна быть ровно одна повторная попытка"

    def test_gives_up_after_max_attempts(self, monkeypatch):
        with pytest.raises(NetworkError):
            self._run(monkeypatch, MAX_ATTEMPTS + 1)

    def test_does_not_retry_unsafe_errors(self, monkeypatch):
        """Read timeout не повторяем: сообщение могло уже уйти."""
        with pytest.raises(NetworkError):
            self._run(monkeypatch, 1, cause=httpx.ReadTimeout("уже ушло"))
        # ровно одна попытка, без повторов — проверяем через счётчик
        from telegram.request import HTTPXRequest

        calls = {"n": 0}

        async def fake(self, url, method, *a, **kw):
            calls["n"] += 1
            raise _net_error(httpx.ReadTimeout("уже ушло"))

        monkeypatch.setattr(HTTPXRequest, "do_request", fake, raising=False)
        with pytest.raises(NetworkError):
            asyncio.run(RetryingHTTPXRequest().do_request("https://api/x", "POST"))
        assert calls["n"] == 1


class TestEntryKeepsDialogOpen:
    """Главный случай: вход в диалог не должен теряться."""

    def test_state_returned_even_if_reply_failed(self):
        async def open_salon_start(update, context):
            raise _net_error(httpx.ConnectError(""))

        wrapped = entry(open_salon_start, "AWAITING_PHOTO")
        assert asyncio.run(wrapped(None, None)) == "AWAITING_PHOTO"

    def test_normal_result_passes_through(self):
        async def ok(update, context):
            return "AWAITING_PHOTO"

        assert asyncio.run(entry(ok, "SOMETHING_ELSE")(None, None)) == "AWAITING_PHOTO"

    def test_non_network_errors_still_raise(self):
        """Ошибка в коде должна быть видна, а не прятаться за «сеть моргнула»."""
        async def broken(update, context):
            raise ValueError("опечатка в обработчике")

        with pytest.raises(ValueError):
            asyncio.run(entry(broken, "X")(None, None))


class TestStepStaysOnCurrentState:
    def test_returns_none_so_state_is_kept(self):
        """None для ConversationHandler означает «состояние не менять»."""
        async def failing(update, context):
            raise TimedOut()

        assert asyncio.run(step(failing)(None, None)) is None

    def test_normal_result_passes_through(self):
        async def ok(update, context):
            return 42

        assert asyncio.run(step(ok)(None, None)) == 42

    def test_supports_plain_functions_returning_coroutines(self):
        """`invalid_data_type` объявлен обычным def и возвращает корутину."""
        async def inner():
            return 7

        def plain(update, context):
            return inner()

        assert asyncio.run(step(plain)(None, None)) == 7


class TestEveryConversationCallbackIsWrapped:
    """Чтобы новый обработчик не добавили в обход обёртки."""

    def test_no_bare_callbacks_left(self):
        """Разбираем файл через ast: у каждого Handler(...) колбэк должен быть
        завёрнут в step() или entry(), иначе сетевой сбой снова уронит шаг."""
        import ast
        import pathlib

        path = (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "core" / "conversations.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))

        HANDLERS = {"MessageHandler", "CallbackQueryHandler", "CommandHandler"}
        WRAPPERS = {"step", "entry"}
        bare = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in HANDLERS:
                continue
            # колбэк: у CommandHandler он второй, у остальных — тоже второй
            # позиционный (первый — фильтр/паттерн)
            args = [a for a in node.args]
            if len(args) < 2:
                continue
            cb = args[1]
            wrapped = (isinstance(cb, ast.Call) and isinstance(cb.func, ast.Name)
                       and cb.func.id in WRAPPERS)
            if not wrapped:
                bare.append(f"{node.func.id} на строке {node.lineno}: "
                            f"{ast.unparse(cb)[:50]}")
        assert bare == [], "обработчики без step()/entry():\n  " + "\n  ".join(bare)
