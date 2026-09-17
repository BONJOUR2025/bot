"""APK приложения «BONJOUR Мастер»: приём от сборки и раздача мастерам.

Приложение — оболочка над кабинетом сотрудника на app.bonjour.pw, поэтому
новые экраны приезжают без пересборки, и APK меняется редко. Вся механика
(проверка «наш ли это пакет», атомарная подмена файла, архив версий, чтение
версии из assets) общая с приложением салона и живёт в device_app_service —
здесь остались только имена и адреса мастерского приложения.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.services.device_app_service import (
    MASTER_APP,
    AppValidationError,
    read_version,
)

PACKAGE_NAME = MASTER_APP.package_name
PUBLIC_APK_NAME = MASTER_APP.public_apk_name

# Историческое имя ошибки: на него ссылаются api/master_app.py и тесты.
MasterAppValidationError = AppValidationError

__all__ = [
    "PACKAGE_NAME", "PUBLIC_APK_NAME", "MasterAppValidationError", "read_version",
    "apk_path", "apk_url", "install_page_url", "archive_dir", "archived_apk_path",
    "archive_url", "archive_apk", "info", "save_apk",
]


def apk_path() -> Path:
    return MASTER_APP.apk_path()


def apk_url() -> str:
    return MASTER_APP.apk_url()


def install_page_url() -> str:
    return MASTER_APP.install_page_url()


def archive_dir() -> Path:
    return MASTER_APP.archive_dir()


def archived_apk_path(version_name: str) -> Optional[Path]:
    return MASTER_APP.archived_apk_path(version_name)


def archive_url(version_name: str) -> str:
    return MASTER_APP.archive_url(version_name)


def archive_apk(content: bytes) -> Optional[str]:
    return MASTER_APP.archive_apk(content)


def info() -> dict[str, Any]:
    return MASTER_APP.info()


def save_apk(content: bytes) -> dict[str, Any]:
    return MASTER_APP.save_apk(content)
