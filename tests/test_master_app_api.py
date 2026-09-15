"""Раздача APK «BONJOUR Мастер»: сборка кладёт файл, мастер качает по ссылке."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.master_app import create_master_app_public_router
from app.services import mdm_service
from app.settings import settings

TOKEN = "ci-token"


def _apk(package: str = "pw.bonjour.master", version: tuple[str, int] | None = ("1.0.0", 1)) -> bytes:
    """Минимальный «APK»: zip с манифестом, где имя пакета в UTF-16, как в
    бинарном манифесте Android, и файлом версии, который кладёт сборка."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00" + package.encode("utf-16-le"))
        if version:
            archive.writestr(
                "assets/app_version.json",
                json.dumps({"version_name": version[0], "version_code": version[1]}),
            )
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "master_app_apk_file", str(tmp_path / "master_app.apk"))
    monkeypatch.setattr(mdm_service, "current_upload_token", lambda: TOKEN)
    app = FastAPI()
    app.include_router(create_master_app_public_router(), prefix="/api")
    return TestClient(app)


def _upload(client, data: bytes, token: str | None = TOKEN):
    headers = {"X-Upload-Token": token} if token else {}
    return client.post(
        "/api/master-app/upload",
        files={"file": ("app-release.apk", data, "application/vnd.android.package-archive")},
        headers=headers,
    )


def test_nothing_uploaded_yet(client):
    assert client.get("/api/master-app/bonjour-master.apk").status_code == 404
    assert client.get("/api/master-app/info").json()["available"] is False
    page = client.get("/api/master-app/")
    assert page.status_code == 200
    assert "ещё не загружено" in page.text


def test_upload_requires_token(client):
    assert _upload(client, _apk(), token=None).status_code == 401
    assert _upload(client, _apk(), token="wrong").status_code == 401


def test_upload_not_configured(client, monkeypatch):
    monkeypatch.setattr(mdm_service, "current_upload_token", lambda: "")
    assert _upload(client, _apk()).status_code == 503


def test_rejects_a_file_that_is_not_an_apk(client):
    resp = _upload(client, b"definitely not a zip")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "not_an_apk"


def test_rejects_someone_elses_apk(client):
    """Главная ошибка, которую ловит проверка: залить агента MDM вместо приложения."""
    resp = _upload(client, _apk(package="pw.bonjour.mdm"))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "foreign_apk"
    assert client.get("/api/master-app/bonjour-master.apk").status_code == 404


def test_upload_then_download(client):
    data = _apk()
    resp = _upload(client, data)
    assert resp.status_code == 200
    info = resp.json()
    assert info["available"] is True
    assert info["version_name"] == "1.0.0"
    assert info["version_code"] == 1

    download = client.get("/api/master-app/bonjour-master.apk")
    assert download.status_code == 200
    assert download.content == data
    assert download.headers["content-type"].startswith("application/vnd.android.package-archive")

    page = client.get("/api/master-app/")
    assert "Версия 1.0.0" in page.text
    assert "bonjour-master.apk" in page.text


def test_new_upload_replaces_previous(client, tmp_path):
    _upload(client, _apk(version=("1.0.0", 1)))
    _upload(client, _apk(version=("1.1.0", 2)))
    assert client.get("/api/master-app/info").json()["version_code"] == 2
    assert not list(tmp_path.glob("*.tmp"))
