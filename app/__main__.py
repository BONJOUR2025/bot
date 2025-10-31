"""Console script for launching the HTTP API with Uvicorn."""

from __future__ import annotations

import os
from typing import Final

import uvicorn

DEFAULT_HOST: Final[str] = "0.0.0.0"
DEFAULT_PORT: Final[int] = 8000


def main() -> None:
    """Run the FastAPI application with Uvicorn."""

    host = os.getenv("TELEGRAM_BOT_HOST", DEFAULT_HOST)
    port = int(os.getenv("TELEGRAM_BOT_PORT", str(DEFAULT_PORT)))
    uvicorn.run("app.server:app", host=host, port=port)


if __name__ == "__main__":
    main()
