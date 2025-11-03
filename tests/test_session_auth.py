from fastapi.testclient import TestClient

from app.api import create_app


def create_test_client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_login_page_accessible():
    client = create_test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "Панель управления" in response.text


def test_session_login_sets_cookie_and_token():
    client = create_test_client()
    response = client.post("/session/login", json={"login": "admin", "password": "admin"})
    assert response.status_code == 200
    payload = response.json()
    token = payload["token"]
    assert token
    assert response.cookies.get("access_token") == token


def test_session_login_rejects_invalid_credentials():
    client = create_test_client()
    response = client.post(
        "/session/login", json={"login": "admin", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


def test_root_renders_login_even_with_cookie():
    client = create_test_client()
    login_response = client.post(
        "/session/login", json={"login": "admin", "password": "admin"}
    )
    token = login_response.json()["token"]
    client.cookies.set("access_token", token)
    response = client.get("/")
    assert response.status_code == 200
    assert "id=\"login-form\"" in response.text
    assert "credentials: 'include'" in response.text


def test_root_clears_invalid_cookie():
    client = create_test_client()
    client.cookies.set("access_token", "invalid")
    response = client.get("/")
    assert response.status_code == 200
    assert "id=\"login-form\"" in response.text
    cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=" in cookie_header
    assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header


def test_api_login_sets_cookie_and_token():
    client = create_test_client()
    response = client.post(
        "/api/auth/login", json={"login": "admin", "password": "admin"}
    )
    assert response.status_code == 200
    payload = response.json()
    token = payload["token"]
    assert token
    assert response.cookies.get("access_token") == token
