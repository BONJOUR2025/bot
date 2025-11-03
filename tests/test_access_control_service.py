from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.access_control_service import AccessControlService, DEFAULT_USER_BUTTON_IDS


class DummyEmployeeRepo:
    def __init__(self, mapping: dict[str, object] | None = None) -> None:
        self.called: list[str] = []
        self.mapping = mapping or {}

    def get_employee(self, employee_id: str):
        self.called.append(employee_id)
        return self.mapping.get(employee_id)


def test_default_admin_created(tmp_path: Path) -> None:
    path = tmp_path / "access.json"
    service = AccessControlService(path=path, secret_key="secret", employee_repo=DummyEmployeeRepo())
    roles = service.list_roles()
    assert any(role["id"] == "owner" for role in roles)
    users = service.list_users()
    assert any(user["login"] == "admin" for user in users)

    authenticated = service.authenticate("admin", "admin")
    assert authenticated is not None
    token = service.issue_token(authenticated.id)
    verified = service.verify_token(token)
    assert verified.id == authenticated.id
    assert verified.display_name is None  # admin user not linked to employee repo


def test_user_permissions_override(tmp_path: Path) -> None:
    path = tmp_path / "access.json"
    employee = type('Employee', (), {'full_name': 'Manager User', 'name': 'Manager User'})
    repo = DummyEmployeeRepo({'123': employee})
    service = AccessControlService(path=path, secret_key="secret", employee_repo=repo)

    service.create_role({
        "id": "manager",
        "name": "Менеджер",
        "permissions": ["employees"],
        "bot_buttons": ["user.view_salary"],
    })
    service.create_user({
        "id": "123",
        "login": "manager",
        "password": "pass",
        "role_id": "manager",
    })

    resolved = service.resolve_user("123")
    assert resolved is not None
    assert resolved.permissions == ["employees"]
    assert set(DEFAULT_USER_BUTTON_IDS).intersection(resolved.bot_buttons)

    service.update_user("123", {
        "permissions": ["reports"],
        "bot_buttons": ["user.profile"],
    })
    resolved = service.resolve_user("123")
    assert resolved.permissions == ["reports"]
    assert "user.profile" in resolved.bot_buttons
    assert "common.home" in resolved.bot_buttons

    buttons = service.get_bot_button_texts("123")
    assert any("Личный кабинет" in text for text in buttons)
