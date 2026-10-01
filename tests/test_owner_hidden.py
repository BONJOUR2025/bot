"""Владелец невидим и неприкосновенен для не-владельцев, даже с правом «access»."""
import json

import pytest

from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage
from app.services.access_control_service import AVAILABLE_PERMISSIONS, AccessControlService

ALL_BUT_MDM = [p["id"] for p in AVAILABLE_PERMISSIONS if p["id"] != "mdm"]


@pytest.fixture
def svc(tmp_path):
    users = tmp_path / "user.json"
    users.write_text(json.dumps({}), encoding="utf-8")
    s = AccessControlService(path=tmp_path / "a.json", secret_key="s", bootstrap_password="",
                             employee_repo=EmployeeRepository(JsonStorage(str(users))))
    if not s._get_role("owner"):
        s.create_role({"id": "owner", "name": "Владелец", "permissions": ["*"]})
    s.create_user({"id": "nick", "login": "Nick", "password": "ownerpass", "role_id": "owner"})
    s.create_user({"id": "armen", "login": "Армен", "password": "armenpass", "permissions": ALL_BUT_MDM})
    s.create_user({"id": "vera", "login": "Вера", "password": "verapass", "permissions": ["employees"]})
    return s


def _actor(s, uid):
    return s.resolve_user(uid)


def test_owner_hidden_from_non_owner(svc):
    armen = _actor(svc, "armen")
    logins = {u["login"] for u in svc.list_users(actor=armen)}
    assert "Nick" not in logins and {"Армен", "Вера"} <= logins
    assert all(r["id"] != "owner" for r in svc.list_roles(actor=armen))


def test_owner_sees_everyone(svc):
    nick = _actor(svc, "nick")
    assert "Nick" in {u["login"] for u in svc.list_users(actor=nick)}
    assert any(r["id"] == "owner" for r in svc.list_roles(actor=nick))


def test_non_owner_cannot_touch_owner(svc):
    armen = _actor(svc, "armen")
    for call in (lambda: svc.update_user("nick", {"password": "x"}, actor=armen),
                 lambda: svc.delete_user("nick", actor=armen),
                 lambda: svc.reveal_password("nick", actor=armen),
                 lambda: svc.update_role("owner", {"permissions": []}, actor=armen),
                 lambda: svc.delete_role("owner", actor=armen)):
        with pytest.raises(ValueError):
            call()
    assert svc.authenticate("Nick", "ownerpass") is not None


def test_non_owner_cannot_make_an_owner(svc):
    armen = _actor(svc, "armen")
    with pytest.raises(ValueError, match="privilege_escalation"):
        svc.update_user("vera", {"role_id": "owner"}, actor=armen)
    with pytest.raises(ValueError, match="privilege_escalation"):
        svc.create_user({"login": "x", "password": "y", "permissions": ["*"]}, actor=armen)


def test_non_owner_still_manages_others(svc):
    armen = _actor(svc, "armen")
    svc.update_user("vera", {"permissions": ["employees", "birthdays"]}, actor=armen)
    assert "birthdays" in svc.resolve_user("vera").permissions
