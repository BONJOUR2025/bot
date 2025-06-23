"""Application setup and entry for running the bot manually."""

from .core.application import create_application
from .utils.logger import log


if __name__ == "__main__":
    application = create_application()
    log("🚀 Bot started...")
    application.run_polling()
