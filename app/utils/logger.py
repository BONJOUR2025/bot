import logging
import re
from typing import Any

# Настройка логирования: вывод в файл и консоль.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


_TOKEN_PATTERN = re.compile(r"\b\d{10,}\b")


def _mask(value: str) -> str:
    """Mask digits that look like chat ids or tokens."""
    return _TOKEN_PATTERN.sub("[REDACTED]", value)


def log(message: Any) -> None:
    """
    Логирует сообщение в файл bot.log и в консоль.
    Принимает любое значение, приводимое к строке.
    """
    logging.info(_mask(str(message)))
