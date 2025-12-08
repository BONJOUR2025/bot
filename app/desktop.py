"""Запуск десктопной оболочки с pywebview и локальным API."""
from __future__ import annotations

import argparse
"""Десктопная оболочка pywebview для панели администратора."""

import argparse
import socket
import threading
import time
from typing import Tuple

import uvicorn
import webview


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _wait_for_backend(host: str, port: int, timeout: float = 15.0) -> None:
    """Дожидается, пока HTTP-сервер поднимется и начнет принимать соединения."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(
        f"Не удалось дождаться запуска сервера на {host}:{port} за {timeout} секунд"
    )


def _start_backend(host: str, port: int) -> Tuple[uvicorn.Server, threading.Thread]:
    """Запускает FastAPI/uvicorn в отдельном потоке."""
    config = uvicorn.Config("app.server:app", host=host, port=port, reload=False, log_level="info")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="uvicorn-desktop", daemon=True)
    thread.start()
    return server, thread


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Десктопная версия админки на pywebview."
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Хост для локального API")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Порт для локального API")
    parser.add_argument(
        "--wait", type=float, default=15.0, help="Сколько секунд ждать запуска API перед открытием окна"
    )
    parser.add_argument(
        "--title",
        default="HR Control Center",
        help="Заголовок окна pywebview",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Запустить оболочку в debug-режиме pywebview"
    )
    args = parser.parse_args()

    server, _thread = _start_backend(args.host, args.port)

    try:
        _wait_for_backend(args.host, args.port, timeout=args.wait)
    except TimeoutError as exc:
        server.should_exit = True
        raise SystemExit(str(exc))

    url = f"http://{args.host}:{args.port}/admin"
    window = webview.create_window(
        args.title,
        url=url,
        width=1320,
        height=900,
        resizable=True,
        text_select=True,
        background_color="#050b17",
    )

    def _on_close() -> None:
        server.should_exit = True

    window.events.closed += _on_close

    webview.start(debug=args.debug)


if __name__ == "__main__":
    main()
