"""Console script for launching the HTTP API with Uvicorn."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Final

import uvicorn

DEFAULT_HOST: Final[str] = "0.0.0.0"
DEFAULT_PORT: Final[int] = 8000

# ── Suppress known Windows asyncio noise ──────────────────────────
_WIN_IGNORED = frozenset([
    "WinError 10054",          # client disconnected abruptly (normal browser close)
    "WinError 10053",          # connection aborted by local software
    "_sockets is not None",    # shutdown race condition (CPython bug)
    "_call_connection_lost",   # proactor cleanup during shutdown
])


def _win_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    msg = str(context.get("message", "")) + str(context.get("exception", ""))
    if any(pat in msg for pat in _WIN_IGNORED):
        return  # silently ignore known Windows asyncio artifacts
    loop.default_exception_handler(context)


def main() -> None:
    """Run the FastAPI application with Uvicorn."""

    if sys.platform == "win32":
        # Patch run_forever so our handler is installed on whatever loop
        # uvicorn creates internally (we can't access it before uvicorn.run).
        _orig_run_forever = asyncio.BaseEventLoop.run_forever

        def _patched_run_forever(self, *args, **kwargs):
            self.set_exception_handler(_win_exception_handler)
            return _orig_run_forever(self, *args, **kwargs)

        asyncio.BaseEventLoop.run_forever = _patched_run_forever  # type: ignore[method-assign]

    host = os.getenv("TELEGRAM_BOT_HOST", DEFAULT_HOST)
    port = int(os.getenv("TELEGRAM_BOT_PORT", str(DEFAULT_PORT)))
    uvicorn.run("app.server:app", host=host, port=port)


if __name__ == "__main__":
    main()
