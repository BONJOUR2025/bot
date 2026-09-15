"""Меню бота у мастера — отдельный набор кнопок, а не довесок к меню сотрудника.

«Просмотр ЗП» и «Просмотр расписания» читают «ФОТ админы *.xlsx», где
мастеров нет, — у мастера они всегда отвечали бы «данные не найдены».
«Открыть салон» — обязанность администратора. Поэтому по должности мастер
получает меню роли «Мастер», а набор в этой роли правится в панели.
"""
from __future__ import annotations

import json

from app.data.employee_repository import EmployeeRepository
from app.data.json_storage import JsonStorage
from app.services.access_control_service import (
    MASTER_ROLE_DEFAULT_BUTTON_IDS,
    MASTER_ROLE_ID,
    AccessControlService,
)
from tests.conftest import make_employee_dict

EARN = "🔧 Мой заработок"
WIP = "🧰 Что на мне висит"
SALARY = "📄 Просмотр ЗП"
SCHEDULE = "📅 Просмотр расписания"
OPEN_SALON = "🏪 Открыть салон"
PAYOUT = "💰 Запросить выплату"
PROFILE = "👤 Личный кабинет"
HOME = "🏠 Домой"

MASTER_MENU = [EARN, WIP, PAYOUT, PROFILE, HOME]

EMPLOYEES = {
    "700": make_employee_dict("700", name="Константин К.", position="Мастер по ремонту"),
    "701": make_employee_dict("701", name="Мединский А.", position="Ученик мастера"),
    "702": make_employee_dict("702", name="Семина М.", position="Мастер по изготовлению подошвы"),
    "703": make_employee_dict("703", name="Юлия 3007", position="Администратор"),
    "704": make_employee_dict("704", name="Роман Щ.", position="Мастер по химчистке"),
}

CHECKIN_ROLE = {
    "id": "employee_checkin",
    "name": "Сотрудник с открытием салона",
    "permissions": ["tasks"],
    "bot_buttons": [
        "user.view_salary", "user.view_schedule", "user.request_payout",
        "user.profile", "user.open_salon",
    ],
}


def _record(uid, role_id="employee_checkin", bot_buttons=None):
    return {
        "id": uid, "login": None, "role_id": role_id, "permissions": None,
        "bot_buttons": bot_buttons, "salt": None, "password_hash": None,
        "employee_id": uid, "allowed_employee_ids": None, "allowed_departments": None,
    }


def _service(tmp_path, users=None):
    emp_path = tmp_path / "users.json"
    emp_path.write_text(json.dumps(EMPLOYEES, ensure_ascii=False), encoding="utf-8")
    ac_path = tmp_path / "access_control.json"
    ac_path.write_text(
        json.dumps({
            "roles": [
                {"id": "owner", "name": "Владелец", "permissions": ["*"], "bot_buttons": ["*"]},
                CHECKIN_ROLE,
            ],
            "users": users or [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return AccessControlService(
        path=ac_path,
        secret_key="test",
        employee_repo=EmployeeRepository(storage=JsonStorage(emp_path)),
    )


def test_master_role_is_seeded(tmp_path):
    roles = {r["id"]: r for r in _service(tmp_path).list_roles()}
    assert roles[MASTER_ROLE_ID]["bot_buttons"] == MASTER_ROLE_DEFAULT_BUTTON_IDS


def test_master_menu_replaces_employee_role_menu(tmp_path):
    """Тот самый случай: у мастера были и «Просмотр ЗП», и «Мой заработок»."""
    svc = _service(tmp_path, users=[_record("700")])
    menu = svc.get_bot_button_texts("700")
    assert menu == MASTER_MENU
    assert SALARY not in menu and SCHEDULE not in menu and OPEN_SALON not in menu


def test_master_without_access_record_gets_master_menu(tmp_path):
    """Карточку с tg id можно завести заранее — запись доступа появится позже."""
    assert _service(tmp_path).get_bot_button_texts("700") == MASTER_MENU


def test_all_master_positions_get_master_menu(tmp_path):
    svc = _service(tmp_path, users=[_record("701"), _record("704")])
    assert svc.get_bot_button_texts("701") == MASTER_MENU
    assert svc.get_bot_button_texts("704") == MASTER_MENU


def test_administrator_keeps_role_menu(tmp_path):
    menu = _service(tmp_path, users=[_record("703")]).get_bot_button_texts("703")
    assert SALARY in menu and OPEN_SALON in menu
    assert EARN not in menu and WIP not in menu


def test_sole_maker_is_not_a_master_menu_user(tmp_path):
    menu = _service(tmp_path, users=[_record("702")]).get_bot_button_texts("702")
    assert EARN not in menu and SALARY in menu


def test_owner_wildcard_has_no_master_buttons(tmp_path):
    menu = _service(tmp_path).get_bot_button_texts("admin")
    assert EARN not in menu and WIP not in menu


def test_explicit_per_user_buttons_beat_position(tmp_path):
    svc = _service(tmp_path, users=[_record("700", bot_buttons=["user.profile"])])
    assert svc.get_bot_button_texts("700") == [PROFILE, HOME]


def test_master_role_menu_is_editable_in_panel(tmp_path):
    svc = _service(tmp_path, users=[_record("700")])
    svc.update_role(MASTER_ROLE_ID, {"bot_buttons": ["master.earnings", "user.profile"]})
    assert svc.get_bot_button_texts("700") == [EARN, PROFILE, HOME]


def test_panel_shows_master_menu_for_master(tmp_path):
    """В «Доступах» у мастера должно быть видно то меню, что он реально видит."""
    svc = _service(tmp_path, users=[_record("700")])
    resolved = svc.resolve_user("700")
    assert "master.earnings" in resolved.bot_buttons
    assert "user.view_salary" not in resolved.bot_buttons
    # права при этом остаются от назначенной роли
    assert resolved.permissions == ["tasks"]


def test_vk_menu_hides_master_sections(tmp_path):
    """В VK раздел мастера не портирован — кнопка без обработчика молчала бы."""
    svc = _service(tmp_path, users=[_record("700")])
    assert svc.get_bot_button_texts("700", channel="vk") == [PAYOUT, PROFILE, HOME]
