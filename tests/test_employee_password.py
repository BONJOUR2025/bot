"""Смена пароля сотрудником и просмотр текущего пароля в админке."""
from __future__ import annotations

import pytest

from app.services import password_vault
from app.services.access_control_service import AccessControlService


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr(password_vault, "EMPLOYEE_PASSWORD_KEY_FILE", str(tmp_path / "k.key"))
    import json

    from app.data.employee_repository import EmployeeRepository
    from app.data.json_storage import JsonStorage

    users = tmp_path / "user.json"
    users.write_text(json.dumps({"e1": {"name": "Мастер", "position": "Мастер по ремонту"}}), encoding="utf-8")
    repo = EmployeeRepository(JsonStorage(str(users)))
    service = AccessControlService(path=tmp_path / "access.json", secret_key="s", employee_repo=repo)
    service.create_user({"id": "m1", "login": "master", "password": "start123", "employee_id": "e1"})
    service.create_user({"id": "boss", "login": "boss", "password": "bosspass"})
    return service


def test_admin_set_password_is_revealable(svc):
    assert svc.reveal_password("m1")["password"] == "start123"
    assert svc.reveal_password("m1")["set_by"] == "admin"


def test_manager_account_never_stored(svc):
    with pytest.raises(ValueError, match="not_employee_account"):
        svc.reveal_password("boss")
    assert "password_enc" not in svc._get_user("boss")


def test_change_own_password(svc):
    with pytest.raises(ValueError, match="wrong_password"):
        svc.change_own_password("m1", "nope", "newpass1")
    with pytest.raises(ValueError, match="password_too_short"):
        svc.change_own_password("m1", "start123", "abc")
    with pytest.raises(ValueError, match="password_is_login"):
        svc.change_own_password("m1", "start123", "Master")
    svc.change_own_password("m1", "start123", "newpass1")
    assert svc.authenticate("master", "newpass1") is not None
    assert svc.authenticate("master", "start123") is None
    rev = svc.reveal_password("m1")
    assert rev["password"] == "newpass1" and rev["set_by"] == "self"


def test_legacy_password_captured_on_login(svc):
    user = svc._get_user("m1")
    user.pop("password_enc")
    svc._persist()
    assert svc.reveal_password("m1")["password"] is None
    assert svc.authenticate("master", "start123") is not None
    assert svc.reveal_password("m1")["password"] == "start123"


def test_lost_key_means_unknown_not_crash(svc, tmp_path, monkeypatch):
    monkeypatch.setattr(password_vault, "EMPLOYEE_PASSWORD_KEY_FILE", str(tmp_path / "other.key"))
    assert svc.reveal_password("m1")["password"] is None
