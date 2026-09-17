"""Раздача APK «BONJOUR Салон»: сборка кладёт файл, администратор качает.

Механика общая с приложением мастера (device_app_service), поэтому здесь
проверяется то, что у двух приложений своё: свой файл, свой адрес, свой пакет
внутри APK и свой список логинов на входе.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.salon_app import create_salon_app_public_router
from app.services import mdm_service
from app.services.device_app_service import MASTER_APP, SALON_APP
from app.settings import settings

TOKEN = "ci-token"


def _apk(package: str = "pw.bonjour.salon", version: tuple[str, int] | None = ("1.0.0", 1)) -> bytes:
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
    monkeypatch.setattr(settings, "salon_app_apk_file", str(tmp_path / "salon_app.apk"))
    monkeypatch.setattr(settings, "master_app_apk_file", str(tmp_path / "master_app.apk"))
    monkeypatch.setattr(mdm_service, "current_upload_token", lambda: TOKEN)
    app = FastAPI()
    app.include_router(create_salon_app_public_router(), prefix="/api")
    return TestClient(app)


def _upload(client, data: bytes, token: str | None = TOKEN):
    headers = {"X-Upload-Token": token} if token else {}
    return client.post(
        "/api/salon-app/upload",
        files={"file": ("app-release.apk", data, "application/vnd.android.package-archive")},
        headers=headers,
    )


def test_nothing_uploaded_yet(client):
    assert client.get("/api/salon-app/bonjour-salon.apk").status_code == 404
    assert client.get("/api/salon-app/info").json()["available"] is False
    page = client.get("/api/salon-app/")
    assert page.status_code == 200 and "ещё не загружено" in page.text


def test_upload_then_download(client):
    apk = _apk()
    assert _upload(client, apk).json()["version_name"] == "1.0.0"
    got = client.get("/api/salon-app/bonjour-salon.apk")
    assert got.status_code == 200 and got.content == apk
    assert got.headers["content-type"] == "application/vnd.android.package-archive"


def test_upload_requires_token(client):
    assert _upload(client, _apk(), token=None).status_code == 401
    assert _upload(client, _apk(), token="wrong").status_code == 401


def test_master_apk_is_not_accepted_as_the_salon_one(client):
    """Ошибиться файлом легко: приложения собираются рядом одним ключом."""
    resp = _upload(client, _apk(package="pw.bonjour.master"))
    assert resp.status_code == 400 and resp.json()["detail"] == "foreign_apk"


def test_two_apps_keep_separate_files(client, tmp_path):
    _upload(client, _apk(version=("1.0.0", 1)))
    assert SALON_APP.apk_path().exists()
    assert not MASTER_APP.apk_path().exists()


def test_every_upload_is_kept_under_its_version(client):
    _upload(client, _apk(version=("1.0.0", 1)))
    _upload(client, _apk(version=("1.1.0", 2)))
    old = client.get("/api/salon-app/archive/1.0.0.apk")
    assert old.status_code == 200 and old.content == _apk(version=("1.0.0", 1))
    assert client.get("/api/salon-app/archive/9.9.9.apk").status_code == 404


def test_install_page_names_the_salon_app(client):
    _upload(client, _apk())
    page = client.get("/api/salon-app/").text
    assert "BONJOUR Салон" in page and "bonjour-salon.apk" in page
    assert "BONJOUR Мастер" not in page


def test_logins_list_only_admins_on_a_point(client, monkeypatch):
    class _Service:
        def point_login_options(self):
            return [{"login": "Иванова А.", "name": "Иванова А."}]

    monkeypatch.setattr(
        "app.services.access_control_service.get_access_control_service", lambda: _Service()
    )
    assert client.get("/api/salon-app/logins").json() == [{"login": "Иванова А.", "name": "Иванова А."}]
