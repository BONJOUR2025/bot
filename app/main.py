"""Entrypoint for running the bot."""

from .core.application import create_application
from .handlers.user import register_user_handlers
from .utils.logger import log


def main() -> None:
    app = create_application()
    register_user_handlers(app)
    log("🚀 Bot started and waiting for commands...")
    app.run_polling()


if __name__ == "__main__":
    main()
