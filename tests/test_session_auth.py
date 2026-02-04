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


def test_root_redirects_when_cookie_valid():
    client = create_test_client()
    login_response = client.post(
        "/session/login", json={"login": "admin", "password": "admin"}
    )
    token = login_response.json()["token"]
    client.cookies.set("access_token", token)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/admin"
