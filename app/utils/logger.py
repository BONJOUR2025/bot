import logging
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


def log(message: Any) -> None:
    """
    Логирует сообщение в файл bot.log и в консоль.
    Принимает любое значение, приводимое к строке.
    """
    logging.info(str(message))
