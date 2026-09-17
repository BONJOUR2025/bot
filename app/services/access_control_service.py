from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.config import ADMIN_LOGIN, ADMIN_PASSWORD, SECRET_KEY
from app.data.bot_user_repository import BotUserRepository, get_bot_user_repository
from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage
from app.utils.file_lock import FileLock


AVAILABLE_PERMISSIONS: list[dict[str, str]] = [
    {"id": "dashboard", "label": "Дашборд"},
    {"id": "employees", "label": "Сотрудники"},
    {"id": "payroll", "label": "Расчёт зарплаты"},
    {"id": "payouts", "label": "Выплаты"},
    {
        "id": "payouts-manage-dates",
        "label": "Выплаты: изменять дату и создавать задним числом",
    },
    {"id": "payouts-control", "label": "Контроль выплат"},
    {"id": "manager-salary", "label": "Расчёт ЗП менеджеров"},
    {"id": "incentives", "label": "Штрафы и премии"},
    {"id": "broadcast", "label": "Рассылка"},
    {"id": "messages", "label": "История сообщений"},
    {"id": "dictionary", "label": "Словарь"},
    {"id": "settings", "label": "Настройки"},
    {"id": "vacations", "label": "Отпуска"},
    {"id": "birthdays", "label": "Дни рождения"},
    {"id": "assets", "label": "Имущество"},
    {"id": "access", "label": "Управление доступом"},
    {"id": "tasks", "label": "Задачи"},
    {"id": "passwords", "label": "Пароли"},
    {"id": "salons", "label": "Управление салонами"},
    {"id": "cash-moves", "label": "Кассовые перемещения"},
    {"id": "shift-checkins", "label": "Рабочее время"},
    {"id": "visitor-counters", "label": "Счётчик посетителей"},
    {"id": "mdm", "label": "Телефоны салонов (MDM)"},
    {"id": "smses", "label": "СМС Агбис"},
    {"id": "payment-calendar", "label": "Платежный календарь"},
    {"id": "leave-requests", "label": "Заявки на отгул/отсутствие"},
    {"id": "employee-messages", "label": "Сообщения от сотрудников"},
    {"id": "3d-scanner", "label": "3D сканер"},
    {"id": "salon-audio", "label": "Прослушивание аудио салонов"},
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
        "id": "user.knowledge_base",
        "label": "📚 База знаний",
        "scope": "user",
        "text": "📚 База знаний",
    },
    {
        "id": "user.open_salon",
        "label": "🏪 Открыть салон",
        "scope": "user",
        "text": "🏪 Открыть салон",
    },
    {
        "id": "master.earnings",
        "label": "🔧 Мой заработок",
        "scope": "master",
        "text": "🔧 Мой заработок",
    },
    {
        "id": "master.wip",
        "label": "🧰 Что на мне висит",
        "scope": "master",
        "text": "🧰 Что на мне висит",
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
    "user.open_salon",
]

# Роль «Мастер» — набор кнопок для мастеров и учеников. Меню у мастера не
# дополняет меню сотрудника, а заменяет его: «Просмотр ЗП» и «Просмотр
# расписания» читают «ФОТ админы *.xlsx», где мастеров нет вовсе, так что у
# мастера эти кнопки всегда отвечали бы «данные не найдены»; «Открыть салон»
# — обязанность администратора.
#
# Роль назначается по должности в карточке (см. resolve_user), а не вручную
# на экране доступов, но набор кнопок в ней правится в панели как у любой
# другой роли. Если админ задал сотруднику кнопки персонально — это явный
# выбор, и он главнее должности.
MASTER_ROLE_ID = "master"
MASTER_ROLE_DEFAULT_BUTTON_IDS: list[str] = [
    "master.earnings",
    "master.wip",
    "user.request_payout",
    "user.profile",
]

TOKEN_TTL_SECONDS = 60 * 60 * 12

# Мастер входит с личного телефона через приложение «BONJOUR Мастер», и 12
# часов значили бы ввод логина и пароля дважды в день — таким приложением
# просто перестают пользоваться. Длинный срок только у мастеров без прав в
# панели: их аккаунт видит лишь собственный заработок и может попросить аванс,
# который всё равно утверждает админ. Как только сотрудник перестаёт быть
# мастером (перевели, уволили), его токен снова живёт 12 часов — срок
# считается при каждой проверке, а не зашивается в токен.
MASTER_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30


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
    employee_id: str | None = None
    is_master: bool = False


def short_person_name(full_name: str) -> str:
    """«Иванов Иван Иванович» → «Иванов И.». Одно слово остаётся как есть.

    В выпадающем списке входа мастер ищет себя по фамилии, а полное ФИО с
    отчеством на узком экране телефона обрезается.
    """
    parts = str(full_name or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0].upper()}."


class AccessControlService:
    """Manage access control configuration stored in JSON."""

    def __init__(
        self,
        path: str | Path = "access_control.json",
        secret_key: str | None = None,
        employee_repo: EmployeeRepository | None = None,
        bot_user_repo: BotUserRepository | None = None,
        bootstrap_login: str | None = None,
        bootstrap_password: str | None = None,
    ) -> None:
        self._bootstrap_login = bootstrap_login if bootstrap_login is not None else ADMIN_LOGIN
        self._bootstrap_password = (
            bootstrap_password if bootstrap_password is not None else ADMIN_PASSWORD
        )
        self.storage = JsonStorage(path)
        self.secret_key = (secret_key or SECRET_KEY or "change_me").encode("utf-8")
        self.employee_repo = employee_repo or EmployeeRepository()
        # Kept so _reload() can rebuild employee_repo from the *same*
        # backing storage each time (see _reload's comment) instead of
        # silently reverting an injected/custom repo back to the default
        # user.json path.
        self._employee_storage = self.employee_repo._storage
        self.bot_user_repo = bot_user_repo or get_bot_user_repository()
        # This file is read/rewritten wholesale by (at least) two OS
        # processes — bot + web/API — with no other synchronization;
        # without a real cross-process lock, concurrent read-modify-write
        # cycles silently drop each other's changes (see FileLock's
        # docstring). Every method that reloads and/or persists this file
        # holds this lock for its full read-modify-write span.
        self._lock = FileLock(path)
        with self._lock:
            self._data: dict[str, Any] = self.storage.load() or {}
            self._ensure_defaults()

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _reload(self) -> None:
        # always fresh from disk (two-process setup) — employee_repo was
        # previously created once in __init__ and never refreshed here,
        # so _ensure_bot_users() ran against a stale in-memory snapshot of
        # user.json: an employee linked/added after this service instance
        # was first constructed (e.g. right after the process started)
        # would never be found, and the bot-user's access entry would
        # never get auto-created — looking exactly like "uses the bot but
        # never shows up in Доступы".
        with self._lock:
            self.employee_repo = EmployeeRepository(self._employee_storage)
            self._data = self.storage.load() or {}
            self._ensure_defaults()
            self._ensure_bot_users()

    def _ensure_bot_users(self) -> None:
        """Auto-create an access control entry for every employee reachable via
        Telegram or VK.

        Telegram is matched the same way as the "Пользователи бота" admin page:
        by Telegram id == employee id (rekey_employee makes them equal once
        linked). VK is a secondary channel that does NOT change employee.id
        (see EmployeeRepository.link_vk_id), so it's matched by employee.vk_id
        instead, scanning employees rather than the vk_bot_users log.

        This lets bot users be granted roles/permissions/menu buttons from the
        "Пользователи" section without requiring an admin-panel login.
        """
        changed = False
        for bot_user in self.bot_user_repo.list():
            telegram_id = bot_user.get("telegram_id")
            if not telegram_id:
                continue
            employee = self.employee_repo.get_employee(telegram_id)
            if not employee:
                continue
            if self._get_user(employee.id):
                continue
            self._data.setdefault("users", []).append({
                "id": employee.id,
                "login": None,
                "role_id": "employee",
                "permissions": None,
                "bot_buttons": None,
                "salt": None,
                "password_hash": None,
                "employee_id": employee.id,
                "allowed_employee_ids": None,
                "allowed_departments": None,
            })
            changed = True

        for employee in self.employee_repo.list_employees(archived=None):
            if not getattr(employee, "vk_id", ""):
                continue
            if self._get_user(employee.id):
                continue
            self._data.setdefault("users", []).append({
                "id": employee.id,
                "login": None,
                "role_id": "employee",
                "permissions": None,
                "bot_buttons": None,
                "salt": None,
                "password_hash": None,
                "employee_id": employee.id,
                "allowed_employee_ids": None,
                "allowed_departments": None,
            })
            changed = True

        if changed:
            self._persist()

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
        if not any(r.get("id") == MASTER_ROLE_ID for r in self._data["roles"]):
            # Роль нужна для привязки меню к должности мастера, поэтому она
            # восстанавливается при каждой загрузке: удалить её из панели
            # можно, но на следующем чтении конфига она вернётся с набором
            # по умолчанию. Кнопки в ней при этом правятся как угодно.
            self._data["roles"].append(
                {
                    "id": MASTER_ROLE_ID,
                    "name": "Мастер",
                    "permissions": [],
                    "bot_buttons": MASTER_ROLE_DEFAULT_BUTTON_IDS.copy(),
                }
            )
            changed = True
        if "users" not in self._data:
            self._data["users"] = []
            changed = True
        # Раньше здесь при каждом чтении конфига создавался admin/admin, если
        # пользователя с логином «admin» не было. Удалить или переименовать
        # его было нельзя — он возвращался с тем же известным паролем. Теперь
        # первый владелец заводится только на пустой установке (ни у кого нет
        # пароля) и только с паролем из ADMIN_PASSWORD.
        login = (self._bootstrap_login or "").strip()
        password = self._bootstrap_password or ""
        has_password_user = any(u.get("password_hash") for u in self._data["users"])
        if (
            not has_password_user
            and login
            and password
            and password != login
            and not any(u.get("login") == login for u in self._data["users"])
        ):
            salt, password_hash = self._hash_password(password)
            self._data["users"].append(
                {
                    "id": login,
                    "login": login,
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
        known_ids = {
            emp.id for emp in self.employee_repo.list_employees(archived=False)
        }
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
            for emp in self.employee_repo.list_employees(archived=False)
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
        self._reload()
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
        self._reload()
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
                    "has_login": bool(user.get("login")),
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
                    "employee_id": resolved.employee_id,
                    # resolved.id is the access-control record's own id — for a
                    # bot-linked user it happens to equal employee.id, but for a
                    # regular CMS login (custom id, separate employee_id field)
                    # it does not, so looking employee up by resolved.id silently
                    # found nothing and always reported "не привязан".
                    "vk_id": getattr(self.employee_repo.get_employee(resolved.employee_id or resolved.id), "vk_id", "") or "",
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

    def _check_privilege_escalation(
        self, actor: ResolvedUser | None, granted_permissions: Iterable[str]
    ) -> None:
        """Forbid granting a role/user permissions the acting user doesn't hold.

        Without this, anyone with the "access" permission could hand out
        (or take for themselves) permissions beyond their own — including
        owner-level access — by editing a role or user record directly.
        """
        if actor is None:
            return
        actor_permissions = set(actor.permissions or [])
        extra = set(granted_permissions) - actor_permissions
        if extra:
            raise ValueError("privilege_escalation")

    def create_role(
        self, data: dict[str, Any], actor: ResolvedUser | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._reload()
            role_id = data.get("id") or secrets.token_hex(6)
            if self._get_role(role_id):
                raise ValueError("role_exists")
            permissions = self._validate_permissions(data.get("permissions")) or []
            resolved_permissions = (
                [p["id"] for p in AVAILABLE_PERMISSIONS] if "*" in permissions else permissions
            )
            self._check_privilege_escalation(actor, resolved_permissions)
            role = {
                "id": role_id,
                "name": data.get("name", role_id),
                "permissions": permissions,
                "bot_buttons": self._validate_buttons(data.get("bot_buttons")) or [],
            }
            self._data.setdefault("roles", []).append(role)
            self._persist()
            return role

    def update_role(
        self, role_id: str, data: dict[str, Any], actor: ResolvedUser | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._reload()
            role = self._get_role(role_id)
            if not role:
                raise ValueError("role_not_found")
            if "name" in data and data["name"]:
                role["name"] = data["name"]
            if "permissions" in data:
                permissions = self._validate_permissions(data.get("permissions")) or []
                resolved_permissions = (
                    [p["id"] for p in AVAILABLE_PERMISSIONS] if "*" in permissions else permissions
                )
                self._check_privilege_escalation(actor, resolved_permissions)
                role["permissions"] = permissions
            if "bot_buttons" in data:
                role["bot_buttons"] = self._validate_buttons(data.get("bot_buttons")) or []
            self._persist()
            return role

    def delete_role(self, role_id: str) -> None:
        with self._lock:
            self._reload()
            if any(user.get("role_id") == role_id for user in self._data.get("users", [])):
                raise ValueError("role_in_use")
            self._data["roles"] = [r for r in self._data.get("roles", []) if r.get("id") != role_id]
            self._persist()

    def create_user(
        self, data: dict[str, Any], actor: ResolvedUser | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._reload()
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
            role = self._get_role(role_id) if role_id else None
            if role_id and not role:
                raise ValueError("role_not_found")
            salt, password_hash = self._hash_password(password)
            raw_employee_id = data.get("employee_id")
            employee_id = str(raw_employee_id) if raw_employee_id else None
            raw_allowed = data.get("allowed_employee_ids")
            if raw_allowed is None and employee_id:
                raw_allowed = [employee_id]
            permissions = self._validate_permissions(data.get("permissions"))
            user_record = {
                "id": user_id,
                "login": login,
                "role_id": role_id,
                "permissions": permissions,
                "bot_buttons": self._validate_buttons(data.get("bot_buttons")),
                "salt": salt,
                "password_hash": password_hash,
                "employee_id": employee_id,
                "allowed_employee_ids": self._validate_employee_ids(raw_allowed),
                "allowed_departments": self._validate_departments(
                    data.get("allowed_departments")
                ),
            }
            self._check_privilege_escalation(
                actor, self._resolve_permissions(user_record, role)
            )
            self._data.setdefault("users", []).append(user_record)
            self._persist()
            return user_record

    def update_user(
        self, user_id: str, data: dict[str, Any], actor: ResolvedUser | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._reload()
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
            if "employee_id" in data:
                raw_emp = data.get("employee_id")
                user["employee_id"] = str(raw_emp) if raw_emp else None
            role = self._get_role(user.get("role_id"))
            self._check_privilege_escalation(actor, self._resolve_permissions(user, role))
            self._persist()
            return user

    def delete_user(self, user_id: str) -> None:
        with self._lock:
            self._reload()
            self._data["users"] = [u for u in self._data.get("users", []) if u.get("id") != user_id]
            self._persist()

    # ------------------------------------------------------------------
    # authentication helpers
    # ------------------------------------------------------------------
    def authenticate(self, login: str, password: str) -> ResolvedUser | None:
        self._reload()
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
        self._reload()
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
        # Срок зависит от того, чей это токен (см. token_ttl_for), поэтому
        # пользователя разрешаем до проверки срока. Токен старше любого
        # возможного срока отвергаем сразу, не читая конфиг.
        age = time.time() - issued_at
        if age > max(TOKEN_TTL_SECONDS, MASTER_TOKEN_TTL_SECONDS):
            raise ValueError("token_expired")
        resolved = self.resolve_user(user_id)
        if not resolved:
            raise ValueError("user_not_found")
        if age > self.token_ttl_for(resolved):
            raise ValueError("token_expired")
        return resolved

    @staticmethod
    def token_ttl_for(user: ResolvedUser) -> int:
        """Срок жизни токена этого пользователя, секунды.

        Длинный — только у мастера без прав в панели (см.
        MASTER_TOKEN_TTL_SECONDS). Считается при каждой проверке токена, так
        что смена должности или выдача прав сразу возвращают 12 часов.
        """
        if user.is_master and not user.permissions:
            return MASTER_TOKEN_TTL_SECONDS
        return TOKEN_TTL_SECONDS

    def master_login_options(self) -> list[dict[str, str]]:
        """Логины мастеров для выпадающего списка на входе в приложение.

        Только аккаунты с заданным паролем и привязанные к сотруднику-мастеру:
        выбрать из списка логин, по которому всё равно не войти, хуже, чем не
        увидеть его вовсе. Показываем имя из карточки, а не логин — мастер
        ищет себя по фамилии.
        """
        self._reload()
        options: list[dict[str, str]] = []
        for record in self._data.get("users", []):
            login = record.get("login")
            if not login or not record.get("password_hash"):
                continue
            resolved = self.resolve_user(str(record.get("id")))
            if resolved is None or not resolved.is_master:
                continue
            employee = self.employee_repo.get_employee(str(resolved.employee_id or resolved.id))
            full = ((employee.full_name or employee.name) if employee else "") or ""
            options.append({"login": login, "name": short_person_name(full) or login})
        options.sort(key=lambda option: option["name"].lower())
        return options

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
        employee = self.employee_repo.get_employee(user_id)
        # Бот-аккаунт живёт под id сотрудника, а аккаунт с логином в панель —
        # под своим id и привязан к сотруднику полем employee_id (так мастеру
        # и заводят вход в приложение). Мастер ли это, решает карточка того
        # сотрудника, к которому аккаунт привязан.
        linked_id = record.get("employee_id")
        linked = (
            self.employee_repo.get_employee(str(linked_id))
            if linked_id and str(linked_id) != str(user_id)
            else employee
        )
        is_master = self._is_master(linked)
        buttons = self._resolve_buttons(record, role)
        # Мастер получает меню роли «Мастер» вместо меню своей роли — но
        # только кнопки: права в панели остаются от назначенной роли.
        # Персонально заданные кнопки — явный выбор админа, их не трогаем.
        if record.get("bot_buttons") is None and is_master:
            buttons = self._master_buttons()
        display_name: str | None = None
        if employee:
            display_name = employee.full_name or employee.name
        allowed_employee_ids, allowed_departments = self._resolve_scope(record, role)
        employee_id = record.get("employee_id") or None
        if employee_id:
            employee_id = str(employee_id)
            # An employee account (has employee_id) with no scope explicitly set by
            # an admin defaults to "self only" — not "unrestricted". Without this,
            # every self-service employee account (allowed_employee_ids defaults to
            # None) would be treated as having full visibility into and authority
            # over every other employee's payouts/leave-requests/etc, since None
            # means "unrestricted" for admin/manager accounts.
            if allowed_employee_ids is None and allowed_departments is None:
                allowed_employee_ids = [employee_id]
        elif not permissions and allowed_employee_ids is None and allowed_departments is None:
            # Аккаунт без прав и без сотрудника не видит никого. Иначе «не
            # задано» читалось бы как «без ограничений», и вход без единого
            # права открывал бы через API чужие выплаты, ЗП и карточки.
            allowed_employee_ids = []
        return ResolvedUser(
            id=user_id,
            login=record.get("login") or "",
            role_id=record.get("role_id"),
            role_name=role.get("name") if role else None,
            permissions=permissions,
            bot_buttons=buttons,
            display_name=display_name,
            allowed_employee_ids=allowed_employee_ids,
            allowed_departments=allowed_departments,
            employee_id=employee_id,
            is_master=is_master,
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
            resolved = [
                btn["id"] for btn in BOT_BUTTON_CATALOG
                if btn.get("scope") not in ("common", "master")
            ]
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
        employees = self.employee_repo.list_employees(archived=False)
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
            for emp in self.employee_repo.list_employees(archived=False)
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
        # Пустой список — «никого», а не «всех»: так же считает
        # is_employee_visible. Раньше пустая область здесь снимала фильтр.
        if employee_scope is None and department_scope is None:
            return None
        visible: set[str] = set(employee_scope or [])
        if department_scope:
            for employee in self.employee_repo.list_employees(archived=False):
                if employee.work_place in department_scope:
                    visible.add(employee.id)
        return visible

    # ------------------------------------------------------------------
    # bot integration helpers
    # ------------------------------------------------------------------
    def get_bot_button_texts(self, user_id: str | None, channel: str = "telegram") -> list[str]:
        """Тексты кнопок главного меню.

        channel="vk" убирает кнопки разделов, которые в VK-боте не
        портированы (раздел мастера): без обработчика нажатие молчит.
        """
        self._reload()
        if not user_id:
            buttons = DEFAULT_USER_BUTTON_IDS + ["common.home"]
        else:
            user = self.resolve_user(user_id)
            if user:
                buttons = list(user.bot_buttons)
            elif self._is_master(self.employee_repo.get_employee(str(user_id))):
                # Карточку с tg id заводят заранее, а запись доступа
                # появляется позже — мастер не должен до этого видеть
                # чужое меню сотрудника.
                buttons = self._master_buttons()
            else:
                buttons = DEFAULT_USER_BUTTON_IDS + ["common.home"]
        if channel == "vk":
            master_ids = {b["id"] for b in BOT_BUTTON_CATALOG if b.get("scope") == "master"}
            buttons = [b for b in buttons if b not in master_ids]
        return self._buttons_to_text(buttons)

    @staticmethod
    def _is_master(employee) -> bool:
        """Меню мастера выбирается по должности, а не по настройке доступа.

        Мастеров нанимают и переводят чаще, чем кто-то вспоминает про экран
        прав, и «мастер вышел на смену, а заработка в боте нет» — отказ,
        который никто не свяжет с забытой ролью. Должность в карточке и так
        заполняют всегда.
        """
        if employee is None:
            return False
        from app.services.master_bot_service import is_master_position

        return is_master_position(getattr(employee, "position", ""))

    def _master_buttons(self) -> list[str]:
        role = self._get_role(MASTER_ROLE_ID) or {"bot_buttons": MASTER_ROLE_DEFAULT_BUTTON_IDS}
        return self._resolve_buttons({"bot_buttons": None}, role)

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
