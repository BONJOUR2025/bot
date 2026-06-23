import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOGS_DIR = Path("logs")
USERS_LOG_DIR = LOGS_DIR / "users"
USERS_LOG_DIR.mkdir(parents=True, exist_ok=True)

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 5

_FORMATTER = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")


def _rotating_handler(path: Path, level: int = logging.INFO) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(_FORMATTER)
    handler.setLevel(level)
    return handler


# ----------------------------------------------------------------------
# Root logger: everything goes to logs/app.log, errors also go to
# logs/errors.log, and everything is mirrored to the console.
# ----------------------------------------------------------------------
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_rotating_handler(LOGS_DIR / "app.log"))
_root_logger.addHandler(_rotating_handler(LOGS_DIR / "errors.log", level=logging.ERROR))
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_FORMATTER)
_root_logger.addHandler(_console_handler)


# ----------------------------------------------------------------------
# Connections log: bot start/stop, admin logins/logouts, telegram /start, etc.
# Propagates to the root logger as well, so it's also visible in app.log.
# ----------------------------------------------------------------------
_connections_logger = logging.getLogger("connections")
_connections_logger.setLevel(logging.INFO)
_connections_logger.addHandler(_rotating_handler(LOGS_DIR / "connections.log"))


# ----------------------------------------------------------------------
# Per-user action log: logs/users/<id>_<username>_<name>.log — one file
# per bot/admin user. Also propagates to the root logger.
# ----------------------------------------------------------------------
_user_loggers: dict[str, logging.Logger] = {}
_user_log_filenames: dict[str, str] = {}
_SAFE_ID_PATTERN = re.compile(r"[^\w.-]+")


def _safe_id(user_id: Any) -> str:
    return _SAFE_ID_PATTERN.sub("_", str(user_id)) or "unknown"


def _safe_label(label: Any) -> str:
    return _SAFE_ID_PATTERN.sub("_", str(label)).strip("_")


def _get_user_logger(user_id: Any, label: str | None = None) -> logging.Logger:
    safe_id = _safe_id(user_id)
    filename = safe_id
    safe_label = _safe_label(label) if label and str(label) != str(user_id) else ""
    if safe_label:
        filename = f"{safe_id}_{safe_label}"

    logger = _user_loggers.get(safe_id)
    prev_filename = _user_log_filenames.get(safe_id)

    if logger is not None and (prev_filename == filename or prev_filename != safe_id):
        # Either the name is unchanged, or we already have a labeled
        # filename — never downgrade back to a bare id on a later call
        # that happens to arrive without a label.
        return logger

    if logger is None:
        logger = logging.getLogger(f"users.{safe_id}")
        logger.setLevel(logging.INFO)
    else:
        # A fuller label showed up after the file was created with a
        # shorter name (e.g. first log call happened before the
        # username was known) — move the log onto the new filename
        # instead of leaving it stuck with the old one forever.
        for old_handler in list(logger.handlers):
            logger.removeHandler(old_handler)
            old_handler.close()
        old_path = USERS_LOG_DIR / f"{prev_filename}.log"
        new_path = USERS_LOG_DIR / f"{filename}.log"
        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)

    logger.addHandler(_rotating_handler(USERS_LOG_DIR / f"{filename}.log"))
    _user_loggers[safe_id] = logger
    _user_log_filenames[safe_id] = filename
    return logger


def log(message: Any) -> None:
    """
    Логирует сообщение в общий файл logs/app.log и в консоль.
    Принимает любое значение, приводимое к строке.
    """
    logging.info(str(message))


def log_connection(message: Any) -> None:
    """Логирует событие подключения/авторизации в logs/connections.log."""
    _connections_logger.info(str(message))


_payment_calendar_logger = logging.getLogger("payment_calendar")
_payment_calendar_logger.setLevel(logging.INFO)
_payment_calendar_logger.addHandler(_rotating_handler(LOGS_DIR / "payment_calendar.log"))


def log_payment_calendar(message: Any) -> None:
    """Логирует события отправки счетов кассиру в logs/payment_calendar.log."""
    _payment_calendar_logger.info(str(message))


def log_user_action(user_id: Any, label: str | None, action: str, **details: Any) -> None:
    """
    Логирует действие конкретного пользователя в его персональный файл
    logs/users/<id>_<username>_<имя>.log (и в общий лог).

    ``user_id`` и ``label`` определяют имя файла (Telegram id + юзернейм/имя,
    либо id и логин пользователя админки). ``label`` также добавляется в
    начало записи. ``action`` — описание действия, ``details`` —
    дополнительные поля key=value.
    """
    extra = ""
    if details:
        extra = " " + " ".join(f"{key}={value}" for key, value in details.items())
    who = f"{user_id}"
    if label and str(label) != str(user_id):
        who = f"{user_id} ({label})"
    message = f"[{who}] {action}{extra}"
    _get_user_logger(user_id, label).info(message)
