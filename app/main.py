"""Entrypoint for running the bot."""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .core.application import create_application
from .db.session import init_db
from .utils.logger import log


def main() -> None:
    # The bot process is the one that actually queries recruitment models
    # (e.g. Vacancy.knowledge_base in handle_candidate_message). Relying on the
    # API/admin process to run migrations on the shared hr.db is fragile — if it
    # hasn't started yet (or isn't deployed at all), the bot ends up querying
    # columns that don't exist yet, and since those queries run inside
    # fire-and-forget asyncio tasks, the resulting OperationalError is swallowed
    # silently — the AI interview just never starts, with no error anywhere.
    init_db()
    app = create_application()
    log("🚀 Bot started and waiting for commands...")
    app.run_polling(
        bootstrap_retries=5,
        allowed_updates=[
            "message",
            "edited_message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )


if __name__ == "__main__":
    main()
