"""Entrypoint for running the bot."""

from .core.application import create_application
from .utils.logger import log


def main() -> None:
    app = create_application()
    log("🚀 Bot started and waiting for commands...")
    app.run_polling(bootstrap_retries=5, read_timeout=10, write_timeout=10, connect_timeout=10, pool_timeout=10)


if __name__ == "__main__":
    main()
