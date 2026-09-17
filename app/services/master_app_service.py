"""APK приложения «BONJOUR Мастер»: приём от сборки и раздача мастерам.

Приложение — оболочка над кабинетом сотрудника на app.bonjour.pw, поэтому
новые экраны приезжают без пересборки, и APK меняется редко. Держать для него
что-то сложнее одного файла в корне рабочей директории незачем.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.settings import settings

PACKAGE_NAME = "pw.bonjour.master"
PUBLIC_APK_NAME = "bonjour-master.apk"


class MasterAppValidationError(ValueError):
    """Загружен не тот файл — наверх идёт как HTTP 400."""


def apk_path() -> Path:
    return Path(settings.master_app_apk_file)


VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")


def archive_dir() -> Path:
    """Прошлые и текущая сборки под своими версиями — рядом с основным APK.

    Нужны, чтобы проверить обновление со старой версии (или вернуть мастеру
    ту, что работала): основной файл каждая сборка перезаписывает.
    """
    return apk_path().parent / "master_app_archive"


def archived_apk_path(version_name: str) -> Optional[Path]:
    if not VERSION_RE.match(version_name or ""):
        return None
    return archive_dir() / f"bonjour-master-{version_name}.apk"


def archive_apk(content: bytes) -> Optional[str]:
    """Кладёт копию APK в архив под его версией. Без версии внутри — не кладёт."""
    version_name, _ = read_version(content)
    path = archived_apk_path(version_name) if version_name else None
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return version_name


def archive_url(version_name: str) -> str:
    return settings.public_base_url.rstrip("/") + f"/api/master-app/archive/{version_name}.apk"


def apk_url() -> str:
    return settings.public_base_url.rstrip("/") + "/api/master-app/" + PUBLIC_APK_NAME


def install_page_url() -> str:
    return settings.public_base_url.rstrip("/") + "/api/master-app/"


def read_version(content: bytes) -> tuple[Optional[str], Optional[int]]:
    """Версия лежит в assets/app_version.json, который кладёт сборка —
    по той же причине, что у агента MDM: разбирать бинарный манифест ради
    двух чисел несоразмерно, а имени файла доверять нельзя."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        data = json.loads(archive.read("assets/app_version.json").decode("utf-8"))
        return str(data["version_name"]), int(data["version_code"])
    except Exception:
        return None, None


def info() -> dict[str, Any]:
    path = apk_path()
    if not path.exists():
        return {"available": False, "url": apk_url(), "install_page": install_page_url()}
    raw = path.read_bytes()
    version_name, version_code = read_version(raw)
    return {
        "available": True,
        "version_name": version_name,
        "version_code": version_code,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "url": apk_url(),
        "install_page": install_page_url(),
    }


def save_apk(content: bytes) -> dict[str, Any]:
    """Кладёт новый APK на сервер.

    Проверка — на вменяемость, а не подпись: что это APK и что внутри наш
    пакет. Смысл — поймать «залил не тот файл» до того, как мастера скачают
    вместо приложения агента MDM или что-то ещё.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        manifest = archive.read("AndroidManifest.xml")
    except Exception as exc:
        raise MasterAppValidationError("not_an_apk") from exc
    if PACKAGE_NAME.encode("utf-16-le") not in manifest:
        raise MasterAppValidationError("foreign_apk")

    path = apk_path()
    archive_apk(content)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    # Подмена целиком: мастер, который качает файл в эту секунду, не должен
    # получить наполовину записанный APK.
    tmp.replace(path)
    return info()
