"""Мастер в сессии: признак is_master и срок жизни токена.

Токен мастера без прав в панели живёт 30 дней, остальные — 12 часов. Срок
считается при каждой проверке, а не зашивается в токен: перестал быть
мастером — старый токен снова подчиняется 12 часам.
"""
from __future__ import annotations

import time

import pytest

from app.api.auth import _to_auth_user
from app.services import access_control_service as acs
from tests.test_master_menu import _record, _service

HOUR = 3600
DAY = 24 * HOUR


def _login_record(uid, employee_id, role_id="master"):
    """Аккаунт с логином в панель: свой id, к сотруднику привязан полем employee_id."""
    record = _record(uid, role_id=role_id)
    record.update({"login": f"login-{uid}", "employee_id": employee_id})
    return record


def _age(monkeypatch, seconds):
    real_now = time.time()
    monkeypatch.setattr(acs.time, "time", lambda: real_now + seconds)


def test_bot_account_of_master_is_master(tmp_path):
    svc = _service(tmp_path, users=[_record("700", role_id="master"), _record("703")])
    assert svc.resolve_user("700").is_master is True
    assert svc.resolve_user("703").is_master is False


def test_panel_login_linked_to_master_card_is_master(tmp_path):
    """Так мастеру и заводят вход в приложение: пользователь в «Доступах» с
    полем «сотрудник». Раньше мастерство определялось по id самого аккаунта и
    такой вход считался бы обычным сотрудником."""
    svc = _service(tmp_path, users=[_login_record("a1b2c3", "700")])
    resolved = svc.resolve_user("a1b2c3")
    assert resolved.is_master is True
    assert "master.earnings" in resolved.bot_buttons
    assert _to_auth_user(resolved).is_master is True


def test_master_token_survives_three_weeks(tmp_path, monkeypatch):
    svc = _service(tmp_path, users=[_record("700", role_id="master")])
    token = svc.issue_token("700")
    _age(monkeypatch, 20 * DAY)
    assert svc.verify_token(token).employee_id == "700"


def test_master_token_expires_after_a_month(tmp_path, monkeypatch):
    svc = _service(tmp_path, users=[_record("700", role_id="master")])
    token = svc.issue_token("700")
    _age(monkeypatch, 31 * DAY)
    with pytest.raises(ValueError, match="token_expired"):
        svc.verify_token(token)


def test_administrator_token_still_lives_12_hours(tmp_path, monkeypatch):
    svc = _service(tmp_path, users=[_record("703")])
    token = svc.issue_token("703")
    _age(monkeypatch, 13 * HOUR)
    with pytest.raises(ValueError, match="token_expired"):
        svc.verify_token(token)


def test_master_with_panel_permissions_keeps_12_hours(tmp_path, monkeypatch):
    """Роль с правами в панели — цена утечки токена уже другая."""
    svc = _service(tmp_path, users=[_record("700", role_id="employee_checkin")])
    resolved = svc.resolve_user("700")
    assert resolved.is_master is True and resolved.permissions
    assert svc.token_ttl_for(resolved) == acs.TOKEN_TTL_SECONDS
    token = svc.issue_token("700")
    _age(monkeypatch, 13 * HOUR)
    with pytest.raises(ValueError, match="token_expired"):
        svc.verify_token(token)


def test_ttl_for_master_without_permissions(tmp_path):
    svc = _service(tmp_path, users=[_record("700", role_id="master")])
    assert svc.token_ttl_for(svc.resolve_user("700")) == acs.MASTER_TOKEN_TTL_SECONDS


def test_login_options_list_only_masters_who_can_actually_log_in(tmp_path):
    """В выпадающем списке на входе — только те, кто по этому логину войдёт."""
    with_password = _login_record("a1", "700")
    with_password["password_hash"] = "hash"
    no_password = _login_record("a2", "701")
    administrator = _login_record("a3", "703", role_id="employee_checkin")
    administrator["password_hash"] = "hash"
    not_linked = _login_record("a4", None)
    not_linked["password_hash"] = "hash"
    svc = _service(tmp_path, users=[with_password, no_password, administrator, not_linked])

    options = svc.master_login_options()

    assert [o["login"] for o in options] == ["login-a1"]
    assert options[0]["name"]


def test_login_names_are_short():
    assert acs.short_person_name("Корягин Константин Сергеевич") == "Корягин К."
    assert acs.short_person_name("Мартиросян Арсен") == "Мартиросян А."
    assert acs.short_person_name("Руслан") == "Руслан"
    assert acs.short_person_name("  ") == ""

