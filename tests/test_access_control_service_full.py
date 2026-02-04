"""Comprehensive tests for AccessControlService."""

import json
from pathlib import Path

import pytest

from app.data.json_storage import JsonStorage
from app.data.employee_repository import EmployeeRepository
from app.services.access_control_service import AccessControlService
from tests.conftest import make_employee_dict


def _make_employee_repo(tmp_path):
    p = tmp_path / "users.json"
    data = {
        "100": make_employee_dict("100", name="Иван", position="Продавец"),
        "200": make_employee_dict("200", name="Мария", position="Администратор"),
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    storage = JsonStorage(p)
    return EmployeeRepository(storage=storage)


def _make_service(tmp_path, ac_data=None, employee_repo=None):
    ac_path = tmp_path / "access_control.json"
    if ac_data is not None:
        ac_path.write_text(json.dumps(ac_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return AccessControlService(
        path=ac_path,
        secret_key="test_secret_key_12345",
        employee_repo=employee_repo or _make_employee_repo(tmp_path),
    )


class TestAccessControlInit:
    def test_creates_default_admin_and_role(self, tmp_path):
        svc = _make_service(tmp_path)
        roles = svc.list_roles()
        users = svc.list_users()
        assert any(r["id"] == "owner" for r in roles)
        assert any(u["login"] == "admin" for u in users)

    def test_loads_existing_config(self, tmp_path):
        ac_data = {
            "roles": [{"id": "custom", "name": "Custom", "permissions": ["view"],
                        "bot_buttons": []}],
            "users": [{"id": "u1", "login": "user1", "role_id": "custom",
                        "password_hash": "dummy"}],
        }
        svc = _make_service(tmp_path, ac_data=ac_data)
        roles = svc.list_roles()
        assert any(r["id"] == "custom" for r in roles)


class TestRoleCRUD:
    def test_create_role(self, tmp_path):
        svc = _make_service(tmp_path)
        role = svc.create_role({"id": "editor", "name": "Editor",
                                 "permissions": ["dashboard", "employees"]})
        assert role["id"] == "editor"
        assert "dashboard" in role["permissions"]

    def test_create_duplicate_role_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="role_exists"):
            svc.create_role({"id": "owner", "name": "Duplicate"})

    def test_update_role(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.create_role({"id": "editor", "name": "Editor"})
        updated = svc.update_role("editor", {"name": "Senior Editor"})
        assert updated["name"] == "Senior Editor"

    def test_update_nonexistent_role_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="role_not_found"):
            svc.update_role("nonexistent", {"name": "X"})

    def test_delete_role(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.create_role({"id": "temp", "name": "Temp"})
        svc.delete_role("temp")
        roles = svc.list_roles()
        assert not any(r["id"] == "temp" for r in roles)

    def test_delete_role_in_use_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="role_in_use"):
            svc.delete_role("owner")


class TestUserCRUD:
    def test_create_user(self, tmp_path):
        svc = _make_service(tmp_path)
        user = svc.create_user({"login": "newuser", "password": "pass123",
                                 "role_id": "owner"})
        assert user["login"] == "newuser"

    def test_create_duplicate_login_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError, match="login_exists"):
            svc.create_user({"login": "admin", "password": "test"})

    def test_update_user(self, tmp_path):
        svc = _make_service(tmp_path)
        users = svc.list_users()
        admin_user = next(u for u in users if u["login"] == "admin")
        updated = svc.update_user(admin_user["id"], {"permissions": ["dashboard"]})
        assert "dashboard" in updated.get("permissions", [])

    def test_delete_user(self, tmp_path):
        svc = _make_service(tmp_path)
        svc.create_user({"login": "temp", "password": "pass", "role_id": "owner"})
        users_before = len(svc.list_users())
        temp = next(u for u in svc.list_users() if u["login"] == "temp")
        svc.delete_user(temp["id"])
        assert len(svc.list_users()) == users_before - 1


class TestAuthentication:
    def test_authenticate_valid(self, tmp_path):
        svc = _make_service(tmp_path)
        user = svc.authenticate("admin", "admin")
        assert user is not None
        assert user.login == "admin"

    def test_authenticate_invalid_password(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.authenticate("admin", "wrong")
        assert result is None

    def test_authenticate_nonexistent_user(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.authenticate("nobody", "pass")
        assert result is None


class TestTokens:
    def test_issue_and_verify_token(self, tmp_path):
        svc = _make_service(tmp_path)
        users = svc.list_users()
        admin = next(u for u in users if u["login"] == "admin")
        token = svc.issue_token(admin["id"])
        assert isinstance(token, str)
        assert len(token) > 0
        user = svc.verify_token(token)
        assert user.login == "admin"

    def test_verify_invalid_token_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        with pytest.raises(ValueError):
            svc.verify_token("invalid_token")


class TestPermissions:
    def test_user_has_all_permissions_from_owner_role(self, tmp_path):
        svc = _make_service(tmp_path)
        user = svc.authenticate("admin", "admin")
        # Owner role has ["*"] which resolves to all available permissions
        assert svc.user_has_permission(user, "dashboard") is True
        assert svc.user_has_permission(user, "employees") is True
        assert svc.user_has_permission(user, "access") is True

    def test_available_permissions(self, tmp_path):
        svc = _make_service(tmp_path)
        perms = svc.available_permissions()
        assert isinstance(perms, list)

    def test_available_bot_buttons(self, tmp_path):
        svc = _make_service(tmp_path)
        buttons = svc.available_bot_buttons()
        assert isinstance(buttons, list)


class TestVisibility:
    def test_visible_employee_ids_wildcard(self, tmp_path):
        svc = _make_service(tmp_path)
        user = svc.authenticate("admin", "admin")
        visible = svc.visible_employee_ids(user)
        assert visible is None  # None means all visible

    def test_is_employee_visible_for_admin(self, tmp_path):
        svc = _make_service(tmp_path)
        user = svc.authenticate("admin", "admin")
        assert svc.is_employee_visible(user, "100") is True

    def test_user_employee_scope_unrestricted(self, tmp_path):
        svc = _make_service(tmp_path)
        user = svc.authenticate("admin", "admin")
        scope = svc.user_employee_scope(user)
        assert scope is None  # None = unrestricted
