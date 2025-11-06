from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.config import SECRET_KEY
from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage


AVAILABLE_PERMISSIONS: list[dict[str, str]] = [
    {"id": "dashboard", "label": "Дашборд"},
    {"id": "employees", "label": "Сотрудники"},
    {"id": "payouts", "label": "Выплаты"},
    {
        "id": "payouts-manage-dates",
        "label": "Выплаты: изменять дату и создавать задним числом",
    },
    {"id": "payouts-control", "label": "Контроль выплат"},
    {"id": "incentives", "label": "Штрафы и премии"},
    {"id": "reports", "label": "Отчёты"},
    {"id": "broadcast", "label": "Рассылка"},
    {"id": "messages", "label": "История сообщений"},
    {"id": "dictionary", "label": "Словарь"},
    {"id": "settings", "label": "Настройки"},
    {"id": "vacations", "label": "Отпуска"},
    {"id": "birthdays", "label": "Дни рождения"},
    {"id": "assets", "label": "Имущество"},
    {"id": "access", "label": "Управление доступом"},
]

BOT_BUTTON_CATALOG: list[dict[str, Any]] = [
    {
        "id": "user.view_salary",
        "label": "📄 Просмотр ЗП",
        "scope": "user",
        "text": "📄 Просмотр ЗП",
    },
    {
        "id": "user.request_payout",
        "label": "💰 Запросить выплату",
        "scope": "user",
        "text": "💰 Запросить выплату",
    },
    {
        "id": "user.view_schedule",
        "label": "📅 Просмотр расписания",
        "scope": "user",
        "text": "📅 Просмотр расписания",
    },
    {
        "id": "user.profile",
        "label": "👤 Личный кабинет",
        "scope": "user",
        "text": "👤 Личный кабинет",
    },
    {
        "id": "common.home",
        "label": "🏠 Домой",
        "scope": "common",
        "text": "🏠 Домой",
        "fixed": True,
    },
]

DEFAULT_USER_BUTTON_IDS: list[str] = [
    "user.view_salary",
    "user.request_payout",
    "user.view_schedule",
    "user.profile",
]

TOKEN_TTL_SECONDS = 60 * 60 * 12


@dataclass
class ResolvedUser:
    id: str
    login: str
    role_id: str | None
    role_name: str | None
    permissions: list[str]
    bot_buttons: list[str]
    display_name: str | None
    allowed_employee_ids: list[str] | None
    allowed_departments: list[str] | None


class AccessControlService:
    """Manage access control configuration stored in JSON."""

    def __init__(
        self,
        path: str | Path = "access_control.json",
        secret_key: str | None = None,
        employee_repo: EmployeeRepository | None = None,
    ) -> None:
        self.storage = JsonStorage(path)
        self.secret_key = (secret_key or SECRET_KEY or "change_me").encode("utf-8")
        self.employee_repo = employee_repo or EmployeeRepository()
        self._data: dict[str, Any] = self.storage.load() or {}
        self._ensure_defaults()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _ensure_defaults(self) -> None:
        changed = False
        if "roles" not in self._data:
            self._data["roles"] = [
                {
                    "id": "owner",
                    "name": "Владелец",
                    "permissions": ["*"],
                    "bot_buttons": ["*"],
                },
                {
                    "id": "employee",
                    "name": "Сотрудник",
                    "permissions": [],
                    "bot_buttons": DEFAULT_USER_BUTTON_IDS.copy(),
                },
            ]
            changed = True
        if "users" not in self._data:
            self._data["users"] = []
            changed = True
        if not any(u.get("login") == "admin" for u in self._data["users"]):
            salt, password_hash = self._hash_password("admin")
            self._data["users"].append(
                {
                    "id": "admin",
                    "login": "admin",
                    "role_id": "owner",
                    "permissions": None,
                    "bot_buttons": None,
                    "salt": salt,
                    "password_hash": password_hash,
                    "allowed_employee_ids": None,
                    "allowed_departments": None,
                }
            )
            changed = True
        if changed:
            self._persist()

    def _persist(self) -> None:
        self.storage.save(self._data)

    def _hash_password(self, password: str, salt: str | None = None) -> tuple[str, str]:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
        return salt, digest

    def _validate_permissions(self, permissions: Iterable[str] | None) -> list[str] | None:
        if permissions is None:
            return None
        valid_ids = {p["id"] for p in AVAILABLE_PERMISSIONS}
        if "*" in permissions:
            return ["*"]
        filtered = [perm for perm in permissions if perm in valid_ids]
        return filtered

    def _validate_buttons(self, button_ids: Iterable[str] | None) -> list[str] | None:
        if button_ids is None:
            return None
        valid_ids = {btn["id"] for btn in BOT_BUTTON_CATALOG}
        if "*" in button_ids:
            return ["*"]
        filtered = [btn_id for btn_id in button_ids if btn_id in valid_ids]
        return filtered

    def _validate_employee_ids(
        self, employee_ids: Iterable[str] | None
    ) -> list[str] | None:
        if employee_ids is None:
            return None
        known_ids = {emp.id for emp in self.employee_repo.list_employees()}
        result = []
        for value in employee_ids:
            if value is None:
                continue
            emp_id = str(value)
            if emp_id in known_ids and emp_id not in result:
                result.append(emp_id)
        return result

    def _validate_departments(
        self, departments: Iterable[str] | None
    ) -> list[str] | None:
        if departments is None:
            return None
        known_departments = {
            emp.work_place.strip()
            for emp in self.employee_repo.list_employees()
            if emp.work_place
        }
        result: list[str] = []
        for raw in departments:
            if not raw:
                continue
            department = str(raw).strip()
            if not department:
                continue
            if known_departments and department not in known_departments:
                continue
            if department not in result:
                result.append(department)
        return result

    def _get_role(self, role_id: str | None) -> dict[str, Any] | None:
        if not role_id:
            return None
        for role in self._data.get("roles", []):
            if role.get("id") == role_id:
                return role
        return None

    def _get_user(self, user_id: str) -> dict[str, Any] | None:
        for user in self._data.get("users", []):
            if user.get("id") == user_id:
                return user
        return None

    def _get_user_by_login(self, login: str) -> dict[str, Any] | None:
        for user in self._data.get("users", []):
            if user.get("login") == login:
                return user
        return None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def list_roles(self) -> list[dict[str, Any]]:
        roles = []
        for role in self._data.get("roles", []):
            roles.append(
                {
                    "id": role.get("id"),
                    "name": role.get("name"),
                    "permissions": role.get("permissions", []),
                    "bot_buttons": role.get("bot_buttons", []),
                }
            )
        return roles

    def list_users(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for user in self._data.get("users", []):
            resolved = self.resolve_user(user.get("id"))
            if not resolved:
                continue
            allowed_ids = self._validate_employee_ids(user.get("allowed_employee_ids"))
            allowed_departments = self._validate_departments(user.get("allowed_departments"))
            result.append(
                {
                    "id": resolved.id,
                    "login": resolved.login,
                    "role_id": resolved.role_id,
                    "role_name": resolved.role_name,
                    "permissions": user.get("permissions"),
                    "bot_buttons": user.get("bot_buttons"),
                    "resolved_permissions": resolved.permissions,
                    "resolved_bot_buttons": resolved.bot_buttons,
                    "resolved_bot_button_labels": self.button_labels(resolved.bot_buttons),
                    "display_name": resolved.display_name,
                    "allowed_employee_ids": allowed_ids,
                    "allowed_departments": allowed_departments,
                    "resolved_employee_names": self._employee_names(allowed_ids),
                    "resolved_departments": allowed_departments or [],
                }
            )
        return result

    def button_labels(self, button_ids: Iterable[str]) -> list[str]:
        catalog_map = {btn["id"]: btn["label"] for btn in BOT_BUTTON_CATALOG}
        labels: list[str] = []
        for btn_id in button_ids:
            label = catalog_map.get(btn_id)
            if label and label not in labels:
                labels.append(label)
        return labels

    def available_permissions(self) -> list[dict[str, str]]:
        return AVAILABLE_PERMISSIONS

    def available_bot_buttons(self) -> list[dict[str, Any]]:
        return BOT_BUTTON_CATALOG

    def user_has_permission(self, user: ResolvedUser, permission: str) -> bool:
        permissions = user.permissions or []
        return "*" in permissions or permission in permissions

    def create_role(self, data: dict[str, Any]) -> dict[str, Any]:
        role_id = data.get("id") or secrets.token_hex(6)
        if self._get_role(role_id):
            raise ValueError("role_exists")
        role = {
            "id": role_id,
            "name": data.get("name", role_id),
            "permissions": self._validate_permissions(data.get("permissions")) or [],
            "bot_buttons": self._validate_buttons(data.get("bot_buttons")) or [],
        }
        self._data.setdefault("roles", []).append(role)
        self._persist()
        return role

    def update_role(self, role_id: str, data: dict[str, Any]) -> dict[str, Any]:
        role = self._get_role(role_id)
        if not role:
            raise ValueError("role_not_found")
        if "name" in data and data["name"]:
            role["name"] = data["name"]
        if "permissions" in data:
            role["permissions"] = self._validate_permissions(data.get("permissions")) or []
        if "bot_buttons" in data:
            role["bot_buttons"] = self._validate_buttons(data.get("bot_buttons")) or []
        self._persist()
        return role

    def delete_role(self, role_id: str) -> None:
        if any(user.get("role_id") == role_id for user in self._data.get("users", [])):
            raise ValueError("role_in_use")
        self._data["roles"] = [r for r in self._data.get("roles", []) if r.get("id") != role_id]
        self._persist()

    def create_user(self, data: dict[str, Any]) -> dict[str, Any]:
        user_id = str(data.get("id") or secrets.token_hex(8))
        login = data.get("login")
        password = data.get("password")
        if not login or not password:
            raise ValueError("login_password_required")
        if self._get_user(user_id):
            raise ValueError("user_exists")
        if self._get_user_by_login(login):
            raise ValueError("login_exists")
        role_id = data.get("role_id")
        if role_id and not self._get_role(role_id):
            raise ValueError("role_not_found")
        salt, password_hash = self._hash_password(password)
        user_record = {
            "id": user_id,
            "login": login,
            "role_id": role_id,
            "permissions": self._validate_permissions(data.get("permissions")),
            "bot_buttons": self._validate_buttons(data.get("bot_buttons")),
            "salt": salt,
            "password_hash": password_hash,
            "allowed_employee_ids": self._validate_employee_ids(
                data.get("allowed_employee_ids")
            ),
            "allowed_departments": self._validate_departments(
                data.get("allowed_departments")
            ),
        }
        self._data.setdefault("users", []).append(user_record)
        self._persist()
        return user_record

    def update_user(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        user = self._get_user(user_id)
        if not user:
            raise ValueError("user_not_found")
        login = data.get("login")
        if login and login != user.get("login"):
            if self._get_user_by_login(login):
                raise ValueError("login_exists")
            user["login"] = login
        if "role_id" in data:
            role_id = data.get("role_id")
            if role_id and not self._get_role(role_id):
                raise ValueError("role_not_found")
            user["role_id"] = role_id
        if "permissions" in data:
            user["permissions"] = self._validate_permissions(data.get("permissions"))
        if "bot_buttons" in data:
            user["bot_buttons"] = self._validate_buttons(data.get("bot_buttons"))
        if "allowed_employee_ids" in data:
            user["allowed_employee_ids"] = self._validate_employee_ids(
                data.get("allowed_employee_ids")
            )
        if "allowed_departments" in data:
            user["allowed_departments"] = self._validate_departments(
                data.get("allowed_departments")
            )
        if data.get("password"):
            user["salt"], user["password_hash"] = self._hash_password(data["password"])
        self._persist()
        return user

    def delete_user(self, user_id: str) -> None:
        self._data["users"] = [u for u in self._data.get("users", []) if u.get("id") != user_id]
        self._persist()

    # ------------------------------------------------------------------
    # authentication helpers
    # ------------------------------------------------------------------
    def authenticate(self, login: str, password: str) -> ResolvedUser | None:
        user_record = self._get_user_by_login(login)
        if not user_record:
            return None
        salt = user_record.get("salt")
        password_hash = user_record.get("password_hash")
        if not salt or not password_hash:
            return None
        _, computed = self._hash_password(password, salt=salt)
        if not hmac.compare_digest(computed, password_hash):
            return None
        return self.resolve_user(user_record.get("id"))

    def issue_token(self, user_id: str) -> str:
        now = int(time.time())
        payload = f"{user_id}:{now}"
        signature = hmac.new(self.secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode("utf-8")).decode("utf-8")
        return token

    def verify_token(self, token: str) -> ResolvedUser:
        try:
            decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
            user_id, issued_at_str, signature = decoded.split(":", 2)
        except Exception as exc:
            raise ValueError("invalid_token") from exc
        expected_signature = hmac.new(
            self.secret_key, f"{user_id}:{issued_at_str}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            raise ValueError("invalid_token")
        issued_at = int(issued_at_str)
        if time.time() - issued_at > TOKEN_TTL_SECONDS:
            raise ValueError("token_expired")
        resolved = self.resolve_user(user_id)
        if not resolved:
            raise ValueError("user_not_found")
        return resolved

    # ------------------------------------------------------------------
    # resolution helpers
    # ------------------------------------------------------------------
    def resolve_user(self, user_id: str | None) -> ResolvedUser | None:
        if not user_id:
            return None
        record = self._get_user(user_id)
        if not record:
            return None
        role = self._get_role(record.get("role_id"))
        permissions = self._resolve_permissions(record, role)
        buttons = self._resolve_buttons(record, role)
        employee = self.employee_repo.get_employee(user_id)
        display_name: str | None = None
        if employee:
            display_name = employee.full_name or employee.name
        allowed_employee_ids, allowed_departments = self._resolve_scope(record, role)
        return ResolvedUser(
            id=user_id,
            login=record.get("login", ""),
            role_id=record.get("role_id"),
            role_name=role.get("name") if role else None,
            permissions=permissions,
            bot_buttons=buttons,
            display_name=display_name,
            allowed_employee_ids=allowed_employee_ids,
            allowed_departments=allowed_departments,
        )

    def _resolve_permissions(
        self, record: dict[str, Any], role: dict[str, Any] | None
    ) -> list[str]:
        user_permissions = record.get("permissions")
        if user_permissions is None and role:
            user_permissions = role.get("permissions")
        if not user_permissions:
            return []
        if "*" in user_permissions:
            return [perm["id"] for perm in AVAILABLE_PERMISSIONS]
        valid = {perm["id"] for perm in AVAILABLE_PERMISSIONS}
        return [perm for perm in user_permissions if perm in valid]

    def _resolve_buttons(
        self, record: dict[str, Any], role: dict[str, Any] | None
    ) -> list[str]:
        button_ids = record.get("bot_buttons")
        if button_ids is None and role:
            button_ids = role.get("bot_buttons")
        if button_ids is None:
            resolved = DEFAULT_USER_BUTTON_IDS.copy()
        elif button_ids and "*" in button_ids:
            resolved = [btn["id"] for btn in BOT_BUTTON_CATALOG if btn.get("scope") != "common"]
        else:
            valid_ids = {btn["id"] for btn in BOT_BUTTON_CATALOG}
            resolved = [btn_id for btn_id in button_ids if btn_id in valid_ids]
        if "common.home" not in resolved:
            resolved.append("common.home")
        return resolved

    def _resolve_scope(
        self, record: dict[str, Any], role: dict[str, Any] | None
    ) -> tuple[list[str] | None, list[str] | None]:
        employee_ids = record.get("allowed_employee_ids")
        if employee_ids is None and role:
            employee_ids = role.get("allowed_employee_ids")
        departments = record.get("allowed_departments")
        if departments is None and role:
            departments = role.get("allowed_departments")
        return (
            self._validate_employee_ids(employee_ids),
            self._validate_departments(departments),
        )

    def _employee_names(self, employee_ids: Iterable[str] | None) -> list[str]:
        if not employee_ids:
            return []
        names: list[str] = []
        for emp_id in employee_ids:
            employee = self.employee_repo.get_employee(str(emp_id))
            if not employee:
                continue
            name = employee.full_name or employee.name or str(emp_id)
            names.append(name)
        return names

    # ------------------------------------------------------------------
    # scope helpers
    # ------------------------------------------------------------------
    def available_employees(self) -> list[dict[str, str]]:
        employees = self.employee_repo.list_employees()
        items = [
            {
                "id": emp.id,
                "name": emp.full_name or emp.name or emp.id,
                "department": emp.work_place or "",
            }
            for emp in employees
        ]
        items.sort(key=lambda item: item["name"].lower())
        return items

    def available_departments(self) -> list[str]:
        departments = {
            emp.work_place.strip()
            for emp in self.employee_repo.list_employees()
            if emp.work_place and emp.work_place.strip()
        }
        return sorted(departments)

    def user_employee_scope(self, user: ResolvedUser) -> set[str] | None:
        if user.allowed_employee_ids is None:
            return None
        return set(user.allowed_employee_ids)

    def user_department_scope(self, user: ResolvedUser) -> set[str] | None:
        if user.allowed_departments is None:
            return None
        return set(user.allowed_departments)

    def is_employee_visible(
        self,
        user: ResolvedUser,
        employee_id: str | None,
        department: str | None = None,
    ) -> bool:
        employee_scope = self.user_employee_scope(user)
        department_scope = self.user_department_scope(user)
        if employee_scope is not None:
            if not employee_id or str(employee_id) not in employee_scope:
                return False
            return True
        if department_scope is not None:
            if department and department in department_scope:
                return True
            if employee_id:
                employee = self.employee_repo.get_employee(str(employee_id))
                if employee and employee.work_place in department_scope:
                    return True
            return False
        return True

    def visible_employee_ids(self, user: ResolvedUser) -> set[str] | None:
        employee_scope = self.user_employee_scope(user)
        department_scope = self.user_department_scope(user)
        if not employee_scope and not department_scope:
            return None
        visible: set[str] = set(employee_scope or [])
        if department_scope:
            for employee in self.employee_repo.list_employees():
                if employee.work_place in department_scope:
                    visible.add(employee.id)
        return visible

    # ------------------------------------------------------------------
    # bot integration helpers
    # ------------------------------------------------------------------
    def get_bot_button_texts(self, user_id: str | None) -> list[str]:
        if not user_id:
            return self._buttons_to_text(DEFAULT_USER_BUTTON_IDS + ["common.home"])
        user = self.resolve_user(user_id)
        if not user:
            return self._buttons_to_text(DEFAULT_USER_BUTTON_IDS + ["common.home"])
        return self._buttons_to_text(user.bot_buttons)

    def _buttons_to_text(self, button_ids: Iterable[str]) -> list[str]:
        catalog_map = {btn["id"]: btn["text"] for btn in BOT_BUTTON_CATALOG}
        texts: list[str] = []
        for btn_id in button_ids:
            text = catalog_map.get(btn_id)
            if text and text not in texts:
                texts.append(text)
        return texts


_service_instance: AccessControlService | None = None


def get_access_control_service() -> AccessControlService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AccessControlService()
    return _service_instance
