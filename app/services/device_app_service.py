"""APK наших приложений для телефонов: приём от сборки и раздача.

Приложений теперь два — «BONJOUR Мастер» (мастера цеха) и «BONJOUR Салон»
(администраторы точек), — и они отличаются только тремя вещами: именем пакета,
файлом на диске и адресом раздачи. Всё остальное (проверка «это наш APK»,
атомарная подмена файла, архив версий, чтение версии из assets) общее, поэтому
живёт здесь, а master_app_service/salon_app_service — тонкие обёртки.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")


class AppValidationError(ValueError):
    """Загружен не тот файл — наверх идёт как HTTP 400."""


def read_version(content: bytes) -> tuple[Optional[str], Optional[int]]:
    """Версия лежит в assets/app_version.json, который кладёт сборка —
    разбирать бинарный манифест ради двух чисел несоразмерно, а имени файла
    доверять нельзя."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        data = json.loads(archive.read("assets/app_version.json").decode("utf-8"))
        return str(data["version_name"]), int(data["version_code"])
    except Exception:
        return None, None


@dataclass(frozen=True)
class DeviceApp:
    """Одно приложение: чей пакет, где файл и по какому адресу его качают."""

    key: str                 # master | salon
    package_name: str
    public_apk_name: str     # имя файла, под которым его качает человек
    url_prefix: str          # /api/master-app
    settings_field: str      # поле в Settings с путём к файлу

    # ── файлы ────────────────────────────────────────────────────
    def apk_path(self) -> Path:
        from app.settings import settings

        return Path(getattr(settings, self.settings_field))

    def archive_dir(self) -> Path:
        """Прошлые и текущая сборки под своими версиями — рядом с основным APK.

        Нужны, чтобы проверить обновление со старой версии (или вернуть
        работавшую): основной файл каждая сборка перезаписывает.
        """
        return self.apk_path().parent / f"{self.key}_app_archive"

    def archived_apk_path(self, version_name: str) -> Optional[Path]:
        if not VERSION_RE.match(version_name or ""):
            return None
        return self.archive_dir() / f"{self.public_apk_name.removesuffix('.apk')}-{version_name}.apk"

    # ── адреса ───────────────────────────────────────────────────
    def apk_url(self) -> str:
        from app.settings import settings

        return settings.public_base_url.rstrip("/") + f"{self.url_prefix}/{self.public_apk_name}"

    def install_page_url(self) -> str:
        from app.settings import settings

        return settings.public_base_url.rstrip("/") + self.url_prefix + "/"

    def archive_url(self, version_name: str) -> str:
        from app.settings import settings

        return settings.public_base_url.rstrip("/") + f"{self.url_prefix}/archive/{version_name}.apk"

    # ── операции ─────────────────────────────────────────────────
    def info(self) -> dict[str, Any]:
        path = self.apk_path()
        if not path.exists():
            return {"available": False, "url": self.apk_url(), "install_page": self.install_page_url()}
        raw = path.read_bytes()
        version_name, version_code = read_version(raw)
        return {
            "available": True,
            "version_name": version_name,
            "version_code": version_code,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "uploaded_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "url": self.apk_url(),
            "install_page": self.install_page_url(),
        }

    def archive_apk(self, content: bytes) -> Optional[str]:
        """Кладёт копию APK в архив под его версией. Без версии внутри — не кладёт."""
        version_name, _ = read_version(content)
        path = self.archived_apk_path(version_name) if version_name else None
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return version_name

    def save_apk(self, content: bytes) -> dict[str, Any]:
        """Кладёт новый APK на сервер.

        Проверка — на вменяемость, а не подпись: что это APK и что внутри наш
        пакет. Смысл — поймать «залил не тот файл» до того, как его скачают:
        приложение мастера вместо приложения салона или агент MDM.
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            manifest = archive.read("AndroidManifest.xml")
        except Exception as exc:
            raise AppValidationError("not_an_apk") from exc
        if self.package_name.encode("utf-16-le") not in manifest:
            raise AppValidationError("foreign_apk")

        path = self.apk_path()
        self.archive_apk(content)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(content)
        # Подмена целиком: тот, кто качает файл в эту секунду, не должен
        # получить наполовину записанный APK.
        tmp.replace(path)
        return self.info()


MASTER_APP = DeviceApp(
    key="master",
    package_name="pw.bonjour.master",
    public_apk_name="bonjour-master.apk",
    url_prefix="/api/master-app",
    settings_field="master_app_apk_file",
)

SALON_APP = DeviceApp(
    key="salon",
    package_name="pw.bonjour.salon",
    public_apk_name="bonjour-salon.apk",
    url_prefix="/api/salon-app",
    settings_field="salon_app_apk_file",
)
