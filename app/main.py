"""Entrypoint for running the bot."""

from .core.application import create_application
from .utils.logger import log


def main() -> None:
    app = create_application()
    log("🚀 Bot started and waiting for commands...")
    app.run_polling()


if __name__ == "__main__":
    main()

