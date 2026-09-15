import json

import pytest
from fastapi.testclient import TestClient

import app.api as api_module
from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage
from app.services.access_control_service import AccessControlService

LOGIN = "owner"
PASSWORD = "0wner-session-pass"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    # Отдельный конфиг доступа: тест не зависит от access_control.json в
    # репозитории и не правит его.
    users = tmp_path / "users.json"
    users.write_text(json.dumps({}), encoding="utf-8")
    service = AccessControlService(
        path=tmp_path / "access_control.json",
        secret_key="session-test-secret",
        employee_repo=EmployeeRepository(storage=JsonStorage(users)),
        bootstrap_login=LOGIN,
        bootstrap_password=PASSWORD,
    )
    monkeypatch.setattr(api_module, "get_access_control_service", lambda: service)
    return TestClient(api_module.create_app())


def test_root_redirects_to_login_without_cookie(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_session_login_sets_cookie_and_token(client):
    response = client.post("/session/login", json={"login": LOGIN, "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["token"]
    assert token
    assert response.cookies.get("access_token") == token


def test_session_login_rejects_invalid_credentials(client):
    response = client.post("/session/login", json={"login": LOGIN, "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


def test_default_admin_password_does_not_work(client):
    response = client.post("/session/login", json={"login": "admin", "password": "admin"})
    assert response.status_code == 401


def test_root_redirects_when_cookie_valid(client):
    token = client.post(
        "/session/login", json={"login": LOGIN, "password": PASSWORD}
    ).json()["token"]
    client.cookies.set("access_token", token)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/admin"
