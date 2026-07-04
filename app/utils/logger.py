import json
import logging
import os
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOGS_DIR = Path("logs")
USERS_LOG_DIR = LOGS_DIR / "users"
BOT_LOG_DIR = LOGS_DIR / "bot"
PAYMENT_CALENDAR_LOG_DIR = LOGS_DIR / "payment_calendar"
EXTERNAL_API_LOG_DIR = LOGS_DIR / "external_apis"
JOBS_LOG_DIR = LOGS_DIR / "jobs"
PROCESSES_LOG_DIR = LOGS_DIR / "processes"
USERS_LOG_DIR.mkdir(parents=True, exist_ok=True)
BOT_LOG_DIR.mkdir(parents=True, exist_ok=True)
PAYMENT_CALENDAR_LOG_DIR.mkdir(parents=True, exist_ok=True)
EXTERNAL_API_LOG_DIR.mkdir(parents=True, exist_ok=True)
JOBS_LOG_DIR.mkdir(parents=True, exist_ok=True)
PROCESSES_LOG_DIR.mkdir(parents=True, exist_ok=True)

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
# Root logger: everything goes to logs/bot/app.log, errors also go to
# logs/bot/errors.log, and everything is mirrored to the console.
# ----------------------------------------------------------------------
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_rotating_handler(BOT_LOG_DIR / "app.log"))
_root_logger.addHandler(_rotating_handler(BOT_LOG_DIR / "errors.log", level=logging.ERROR))
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_FORMATTER)
_root_logger.addHandler(_console_handler)


# ----------------------------------------------------------------------
# Connections log: bot start/stop, admin logins/logouts, telegram /start, etc.
# (Telegram and VK both write here — see app/main.py, app/vk_main.py,
# app/handlers/user/start.py.) Propagates to the root logger as well, so
# it's also visible in app.log.
# ----------------------------------------------------------------------
_connections_logger = logging.getLogger("connections")
_connections_logger.setLevel(logging.INFO)
_connections_logger.addHandler(_rotating_handler(BOT_LOG_DIR / "connections.log"))


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
_payment_calendar_logger.addHandler(_rotating_handler(PAYMENT_CALENDAR_LOG_DIR / "payment_calendar.log"))


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


# ----------------------------------------------------------------------
# External API logs: one file per integration under logs/external_apis/ —
# StarLine, VK, routing providers, amoCRM, Avito, hh.ru, etc. Still
# propagates to the root logger (app.log), same as everything else; this
# just additionally gives each integration its own file so a flaky
# third-party API can be diagnosed without grepping through the whole
# general log.
# ----------------------------------------------------------------------
_service_loggers: dict[str, logging.Logger] = {}


def get_service_logger(name: str) -> logging.Logger:
    logger = _service_loggers.get(name)
    if logger is None:
        logger = logging.getLogger(f"external.{name}")
        logger.setLevel(logging.INFO)
        logger.addHandler(_rotating_handler(EXTERNAL_API_LOG_DIR / f"{name}.log"))
        _service_loggers[name] = logger
    return logger


# ----------------------------------------------------------------------
# Background job logs: one file per scheduled/repeating job under
# logs/jobs/ — birthday reminders, payment reminders, the StarLine poller,
# etc. Unlike ad hoc log() calls scattered in each job, this records every
# run (not just failures), so "did this even run today" is answerable.
# ----------------------------------------------------------------------
_job_loggers: dict[str, logging.Logger] = {}


def get_job_logger(name: str) -> logging.Logger:
    logger = _job_loggers.get(name)
    if logger is None:
        logger = logging.getLogger(f"job.{name}")
        logger.setLevel(logging.INFO)
        logger.addHandler(_rotating_handler(JOBS_LOG_DIR / f"{name}.log"))
        _job_loggers[name] = logger
    return logger


def log_job_run(name: str, *, ok: bool = True, duration_s: float | None = None, **details: Any) -> None:
    """Log one completed run of a background job — start/end aren't tracked
    separately, this is called once the run finishes (success or not)."""
    extra = " " + " ".join(f"{k}={v}" for k, v in details.items()) if details else ""
    dur = f" ({duration_s:.1f}s)" if duration_s is not None else ""
    status = "OK" if ok else "FAILED"
    get_job_logger(name).info(f"[{status}]{dur}{extra}")


def log_job(name: str):
    """Decorator for an async job function — logs every run via
    log_job_run (success + duration, or failure + error) automatically,
    so individual jobs don't each need their own timing/try-except
    boilerplate just to be visible in logs/jobs/."""
    import functools
    import time as _time

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            started = _time.monotonic()
            try:
                result = await func(*args, **kwargs)
                log_job_run(name, ok=True, duration_s=_time.monotonic() - started)
                return result
            except Exception as exc:
                log_job_run(name, ok=False, duration_s=_time.monotonic() - started, error=str(exc))
                raise
        return wrapper
    return decorator


# ----------------------------------------------------------------------
# Process heartbeat: logs/processes/<name>.json — a small "I'm alive"
# marker each long-running process (app.main, app.vk_main, the API/uvicorn
# process) writes on a timer. Surfaced in the Diagnostics UI as an
# online/offline indicator — right now a hung-but-not-crashed process is
# indistinguishable from a healthy one without SSHing in to check.
# ----------------------------------------------------------------------

_process_loggers: dict[str, logging.Logger] = {}


def _get_process_logger(name: str) -> logging.Logger:
    logger = _process_loggers.get(name)
    if logger is None:
        logger = logging.getLogger(f"process.{name}")
        logger.setLevel(logging.INFO)
        logger.addHandler(_rotating_handler(PROCESSES_LOG_DIR / f"{name}.log"))
        _process_loggers[name] = logger
    return logger


def write_heartbeat(process_name: str, **extra: Any) -> None:
    """Writes both a latest-status JSON snapshot (processes/<name>.status.json
    — read by the Diagnostics "process status" panel) and a plain log line
    (processes/<name>.log — so the heartbeat history is also visible in the
    regular folder browser, e.g. to spot gaps where the process was down)."""
    data = {
        "process": process_name,
        "pid": os.getpid(),
        "last_seen": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }
    path = PROCESSES_LOG_DIR / f"{process_name}.status.json"
    try:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    extra_str = " " + " ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
    _get_process_logger(process_name).info(f"alive pid={os.getpid()}{extra_str}")
