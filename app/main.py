"""Entrypoint for running the bot."""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from .core.application import create_application
from .utils.logger import log


def main() -> None:
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
