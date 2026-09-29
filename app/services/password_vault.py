"""Обратимая копия пароля входа сотрудника — чтобы руководитель мог его
подсказать, если мастер забыл.

Для входа по-прежнему используется только хэш (access_control_service);
копия лежит рядом, зашифрованная Fernet. Ключ — отдельный файл в рабочей
папке продакшна (EMPLOYEE_PASSWORD_KEY_FILE), не в репозитории и не в
access_control.json: утёкший файл учёток сам по себе паролей не раскрывает.
Ключ создаётся при первой записи. Потерян ключ — копии просто перестают
читаться («пароль неизвестен»), вход от этого не ломается.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import EMPLOYEE_PASSWORD_KEY_FILE

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _fernet(create: bool) -> Optional[Fernet]:
    path = EMPLOYEE_PASSWORD_KEY_FILE
    with _lock:
        if not os.path.exists(path):
            if not create:
                return None
            key = Fernet.generate_key()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
        with open(path, "rb") as f:
            return Fernet(f.read().strip())


def encrypt(password: str) -> Optional[str]:
    try:
        return _fernet(create=True).encrypt(password.encode("utf-8")).decode("ascii")
    except Exception:
        logger.warning("Не удалось сохранить копию пароля", exc_info=True)
        return None


def decrypt(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        f = _fernet(create=False)
        return f.decrypt(token.encode("ascii")).decode("utf-8") if f else None
    except (InvalidToken, ValueError):
        return None
