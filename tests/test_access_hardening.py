"""Вход без admin/admin и API, в котором сотрудник или мастер не видит и не
правит админские данные.

Здесь три слоя: сервис доступа (кого создаёт и кому что видно), конкретные
админские адреса (сотруднику — 403) и страж на все маршруты приложения: новый
адрес «только с проверкой входа» не пройдёт незамеченным.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.amo import create_amo_router
from app.api.assets import create_asset_router
from app.api.dependencies import get_current_user
from app.api.employees import create_employee_router
from app.api.incentives import create_incentive_router
from app.api.leave_requests import create_leave_request_router
from app.api.messages import create_message_router
from app.api.push import create_push_router
from app.api.vacations import create_vacation_router
from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage
from app.services.access_control_service import AccessControlService, ResolvedUser
from tests.conftest import make_employee_dict


def _service(tmp_path, login="", password=""):
    users = tmp_path / "users.json"
    if not users.exists():
        users.write_text(
            json.dumps(
                {"100": make_employee_dict("100"), "200": make_employee_dict("200", name="Мария")},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return AccessControlService(
        path=tmp_path / "access_control.json",
        secret_key="test-secret",
        employee_repo=EmployeeRepository(storage=JsonStorage(users)),
        bootstrap_login=login,
        bootstrap_password=password,
    )


# ── Сервис доступа ────────────────────────────────────────────────────


class TestNoDefaultAdmin:
    def test_fresh_install_has_no_admin_with_known_password(self, tmp_path):
        svc = _service(tmp_path)
        assert not any(u["login"] == "admin" for u in svc.list_users())
        assert svc.authenticate("admin", "admin") is None

    def test_bootstrap_owner_from_settings(self, tmp_path):
        svc = _service(tmp_path, login="boss", password="S3cure-pass")
        user = svc.authenticate("boss", "S3cure-pass")
        assert user is not None
        assert user.role_id == "owner"

    def test_bootstrap_refuses_password_equal_to_login(self, tmp_path):
        svc = _service(tmp_path, login="admin", password="admin")
        assert svc.authenticate("admin", "admin") is None

    def test_bootstrap_skipped_when_someone_can_already_log_in(self, tmp_path):
        _service(tmp_path).create_user(
            {"login": "nick", "password": "nick-pass", "role_id": "owner"}
        )
        svc = _service(tmp_path, login="boss", password="S3cure-pass")
        assert svc.authenticate("boss", "S3cure-pass") is None

    def test_deleted_admin_stays_deleted(self, tmp_path):
        svc = _service(tmp_path, login="admin", password="S3cure-pass")
        svc.create_user({"login": "nick", "password": "nick-pass", "role_id": "owner"})
        admin_id = next(u["id"] for u in svc.list_users() if u["login"] == "admin")
        svc.delete_user(admin_id)

        again = _service(tmp_path, login="admin", password="S3cure-pass")
        assert not any(u["login"] == "admin" for u in again.list_users())
        assert again.authenticate("admin", "S3cure-pass") is None


class TestScope:
    def test_account_without_permissions_and_employee_sees_nobody(self, tmp_path):
        svc = _service(tmp_path)
        created = svc.create_user(
            {"login": "guest", "password": "guest-pass", "role_id": "employee"}
        )
        user = svc.resolve_user(created["id"])
        assert user.permissions == []
        assert svc.visible_employee_ids(user) == set()
        assert svc.is_employee_visible(user, "100") is False

    def test_explicit_empty_scope_is_not_unrestricted(self, tmp_path):
        svc = _service(tmp_path)
        created = svc.create_user(
            {
                "login": "manager",
                "password": "manager-pass",
                "role_id": "employee",
                "permissions": ["payouts"],
                "allowed_employee_ids": [],
            }
        )
        user = svc.resolve_user(created["id"])
        assert svc.visible_employee_ids(user) == set()

    def test_owner_is_unrestricted(self, tmp_path):
        svc = _service(tmp_path, login="boss", password="S3cure-pass")
        owner = svc.authenticate("boss", "S3cure-pass")
        assert svc.visible_employee_ids(owner) is None


# ── Админские адреса ──────────────────────────────────────────────────


def _user(**kw):
    base = dict(
        id="100", login="ivan", role_id="employee", role_name=None, permissions=[],
        bot_buttons=[], display_name=None, allowed_employee_ids=["100"],
        allowed_departments=None, employee_id="100",
    )
    base.update(kw)
    return ResolvedUser(**base)


EMPLOYEE = _user()
MASTER = _user(id="0", login="master", role_id="master", employee_id="nb_1",
               allowed_employee_ids=["nb_1"], is_master=True)
UNLINKED = _user(id="guest", login="guest", employee_id=None, allowed_employee_ids=[])
OWNER = _user(id="owner", login="owner", role_id="owner", permissions=["*"],
              bot_buttons=["*"], allowed_employee_ids=None, employee_id=None)


def _access():
    access = MagicMock()
    access.user_has_permission.side_effect = (
        lambda u, p: "*" in u.permissions or p in u.permissions
    )
    access.is_employee_visible.side_effect = (
        lambda u, eid, dep=None: u.allowed_employee_ids is None
        or str(eid) in u.allowed_employee_ids
    )
    access.visible_employee_ids.side_effect = (
        lambda u: None if u.allowed_employee_ids is None else set(u.allowed_employee_ids)
    )
    access.user_employee_scope.side_effect = (
        lambda u: None if u.allowed_employee_ids is None else set(u.allowed_employee_ids)
    )
    access.user_department_scope.return_value = None
    return access


def _client(user):
    access = _access()
    employees = AsyncMock()
    employees.service = MagicMock()
    employees.service.get_employee.return_value = None
    employees.upload_employee_photo.return_value = {"status": "ok"}
    incentives = AsyncMock()
    incentives.get_incentive_employee = MagicMock(return_value="100")
    incentives.delete_incentive.return_value = True
    vacations = AsyncMock()
    vacations.get_vacation_employee = MagicMock(return_value="100")
    assets = AsyncMock()
    assets.get_asset_employee = MagicMock(return_value="100")
    leave = AsyncMock()
    leave.get_request_employee = MagicMock(return_value="100")
    templates = AsyncMock()
    templates.list_templates.return_value = []
    push = MagicMock()
    push.has_subscription.return_value = False

    app = FastAPI()
    for router in (
        create_employee_router(employees, access),
        create_incentive_router(incentives, access),
        create_vacation_router(vacations, access),
        create_asset_router(assets, access),
        create_leave_request_router(leave, access),
        create_message_router(AsyncMock(), templates),
        create_amo_router(),
        create_push_router(push),
    ):
        app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


ADMIN_ONLY = [
    ("POST", "/api/incentives/"),
    ("PATCH", "/api/incentives/1"),
    ("DELETE", "/api/incentives/1"),
    ("POST", "/api/vacations/"),
    ("PUT", "/api/vacations/1"),
    ("DELETE", "/api/vacations/1"),
    ("POST", "/api/assets/"),
    ("POST", "/api/assets/bulk/create"),
    ("POST", "/api/assets/bulk/delete"),
    ("POST", "/api/assets/bulk/notify"),
    ("POST", "/api/assets/1/notify"),
    ("PUT", "/api/assets/1"),
    ("DELETE", "/api/assets/1"),
    ("POST", "/api/employees/"),
    ("PUT", "/api/employees/100"),
    ("DELETE", "/api/employees/100"),
    ("POST", "/api/employees/100/archive"),
    ("POST", "/api/employees/100/restore"),
    ("POST", "/api/employees/100/passport"),
    ("GET", "/api/employees/external-users"),
    ("GET", "/api/messages/"),
    ("POST", "/api/messages/"),
    ("POST", "/api/messages/1/accept"),
    ("GET", "/api/messages/templates"),
    ("POST", "/api/messages/templates"),
    ("DELETE", "/api/messages/templates/1"),
    ("GET", "/api/amo/status"),
    ("GET", "/api/amo/users"),
    ("GET", "/api/amo/auth/url"),
    ("GET", "/api/amo/raw/lead/1"),
    ("GET", "/api/amo/raw/events?date_from=2026-01-01&date_to=2026-01-02"),
    ("DELETE", "/api/leave-requests/1"),
]


@pytest.mark.parametrize("user", [EMPLOYEE, MASTER, UNLINKED], ids=["employee", "master", "unlinked"])
@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_non_admin_is_forbidden(user, method, path):
    resp = _client(user).request(method, path, json=None if method == "GET" else {})
    assert resp.status_code == 403, resp.text


def test_owner_passes_the_same_gates():
    client = _client(OWNER)
    assert client.get("/api/messages/templates").status_code == 200
    assert client.delete("/api/incentives/1").status_code == 200
    assert client.delete("/api/leave-requests/1").status_code == 200


def test_employee_uploads_own_photo_but_not_someone_elses():
    client = _client(EMPLOYEE)
    files = {"file": ("me.jpg", b"jpeg", "image/jpeg")}
    assert client.post("/api/employees/100/photo", files=files).status_code == 200
    assert client.post("/api/employees/200/photo", files=files).status_code == 403


def test_push_subscription_only_for_self_or_admin():
    body = {"subscription": {}, "employee_id": "100"}
    assert _client(EMPLOYEE).post("/api/push/subscribe", json=body).status_code == 200
    other = {**body, "employee_id": "200"}
    assert _client(EMPLOYEE).post("/api/push/subscribe", json=other).status_code == 403
    assert _client(UNLINKED).post("/api/push/subscribe", json=body).status_code == 403
    assert _client(UNLINKED).get("/api/push/status/100").status_code == 403
    assert _client(OWNER).post("/api/push/subscribe", json=body).status_code == 200


# ── Страж на все маршруты ─────────────────────────────────────────────

# Адреса, где проверяется только вход, а права — внутри обработчика или
# областью видимости («только свои»). Каждый просмотрен: сотруднику они нужны
# для кабинета или сами отказывают без права. Новый адрес без
# require_permission сюда попадёт только осознанно.
AUTH_ONLY_REVIEWED = {
    "GET /api/auth/me",
    # Карточки: список и чтение фильтруются областью, себе — PATCH /self и фото.
    "GET /api/employees/",
    "GET /api/employees/{employee_id}",
    "PATCH /api/employees/{employee_id}/self",
    "POST /api/employees/{employee_id}/photo",
    "GET /api/employees/{user_id}/profile.pdf",
    # ЗП из Excel: строки фильтруются, отчёт PDF отказывает ограниченным.
    "GET /api/salary/",
    "GET /api/salary/months",
    "GET /api/salary/report",
    # График салонов открыт всем сотрудникам (правка — с правом payroll).
    "GET /api/schedule/by_day",
    "GET /api/schedule/month",
    # Push: только на себя, без сотрудника — с правом employees.
    "GET /api/push/vapid-public-key",
    "POST /api/push/subscribe",
    "POST /api/push/unsubscribe",
    "GET /api/push/status/{employee_id}",
    # Выплаты: свои заявки; утверждение и правка — с правом payouts.
    "GET /api/payouts/",
    "GET /api/payouts",
    "POST /api/payouts/",
    "GET /api/payouts/active",
    "GET /api/payouts/unconfirmed",
    "GET /api/payouts/export.pdf",
    # Чтение своих отпусков, заявок, штрафов, имущества; правка — с правами.
    "GET /api/vacations/",
    "GET /api/vacations/active",
    "GET /api/vacations/reminders",
    "GET /api/leave-requests/",
    "POST /api/leave-requests/",
    "POST /api/leave-requests/{request_id}/approve",
    "POST /api/leave-requests/{request_id}/reject",
    "PUT /api/leave-requests/{request_id}/status",
    "DELETE /api/leave-requests/{request_id}",
    "GET /api/employee-messages/",
    "POST /api/employee-messages/",
    "POST /api/employee-messages/{message_id}/read",
    "POST /api/employee-messages/{message_id}/reply",
    "GET /api/incentives/",
    "GET /api/assets/",
    # Расчёт ЗП: каждый обработчик сам проверяет право payroll, кроме /my.
    "GET /api/payroll/my",
    "GET /api/payroll/months",
    "GET /api/payroll/calculate",
    "GET /api/payroll/calculate/{employee_code}",
    "GET /api/payroll/by-salon",
    "GET /api/payroll/advances-history",
    "GET /api/payroll/settlements",
    "PUT /api/payroll/settlements/{employee_code}",
    "GET /api/payroll/plans",
    "GET /api/payroll/plans/{employee_code}",
    "PUT /api/payroll/plans",
    "DELETE /api/payroll/plans/{employee_code}",
    "GET /api/payroll/audit",
    "POST /api/payroll/audit",
    "GET /api/payroll/comments",
    "PUT /api/payroll/comments/{employee_code}",
    "GET /api/payroll/order-lookup",
    "GET /api/payroll/sale-transfers",
    "POST /api/payroll/sale-transfers",
    "DELETE /api/payroll/sale-transfers/{transfer_id}",
    "GET /api/payroll/export/excel",
    # Кабинет мастера: только свои данные.
    "GET /api/masters/me/earnings",
    "GET /api/masters/me/wip",
    "GET /api/masters/me/photos/{photo_id}/full",
    "GET /api/masters/me/advance-cap",
    "GET /api/masters/me/scan/lookup",
    "GET /api/masters/me/scan/mode",
    "POST /api/masters/me/scan/preview",
    "POST /api/masters/me/scan/confirm",
}


def _dependency_names(dependant):
    names, stack = set(), [dependant]
    while stack:
        current = stack.pop()
        if current.call is not None:
            names.add(getattr(current.call, "__qualname__", ""))
        stack.extend(current.dependencies)
    return names


def test_every_login_only_route_was_reviewed(tmp_path, monkeypatch):
    import app.api as api_module

    svc = _service(tmp_path)
    monkeypatch.setattr(api_module, "get_access_control_service", lambda: svc)
    app = api_module.create_app()

    found = set()
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        names = _dependency_names(dependant)
        if "get_current_user" not in names:
            continue
        if any(n.startswith(("require_permission.", "require_any_permission.")) for n in names):
            continue
        found.update(f"{method} {route.path}" for method in route.methods)

    unexpected = sorted(found - AUTH_ONLY_REVIEWED)
    assert not unexpected, (
        "Адреса только с проверкой входа: сотрудник или мастер дойдёт до них "
        "своим токеном. Добавьте require_permission или, если адрес нужен "
        f"кабинету, внесите его в AUTH_ONLY_REVIEWED: {unexpected}"
    )
    stale = sorted(AUTH_ONLY_REVIEWED - found)
    assert not stale, f"Этих адресов больше нет или они уже под правом: {stale}"
