"""Журнал активности: человеческие записи вместо HTTP-запросов."""
import pytest

from app.utils import activity


@pytest.fixture(autouse=True)
def fresh_dedup(monkeypatch):
    monkeypatch.setattr(activity, "_last_open", {})


def test_page_open_logged_once_while_staying_on_page():
    assert activity.page_open("u", "/admin/payouts", now=0) == "открыл «Выплаты»"
    # Страница дёргает API дальше — повторно не пишем.
    assert activity.page_open("u", "/admin/payouts", now=60) is None
    assert activity.page_open("u", "/admin/payouts", now=600) is None
    # Ушёл и вернулся — пишем.
    assert activity.page_open("u", "/admin/tasks", now=700) == "открыл «Задачи»"
    assert activity.page_open("u", "/admin/payouts", now=710) == "открыл «Выплаты»"


def test_page_reopened_after_idle_is_logged_again():
    activity.page_open("u", "/employee/scan", now=0)
    assert activity.page_open("u", "/employee/scan", now=activity.OPEN_DEDUP_S + 1) == "открыл «Скан» (кабинет мастера)"


def test_page_names():
    assert activity.page_name("/admin/employees/abc123") == "карточку сотрудника"
    assert activity.page_name("/admin/employees") == "«Сотрудники»"
    assert activity.page_name("/admin/payroll-summary") == "«Сводный отчёт» (зарплата)"
    assert activity.page_name("/admin/payroll") == "«Зарплата → Администраторы»"
    assert activity.page_name("/admin/") == "«Дашборд»"
    assert activity.page_name("/employee/kpi") == "«Мой KPI» (кабинет менеджера)"
    assert activity.page_name("/login") is None


def test_reads_and_noise_are_not_logged():
    assert activity.entries("u", "GET", "/api/masters/me/earnings", 200, None, []) == []
    assert activity.entries("u", "GET", "/api/auth/me", 200, "/admin", [])[1:] == []
    assert activity.describe_change("POST", "/api/mdm/device", 200) is None
    assert activity.describe_change("POST", "/api/manager-salary/calc", 200) is None


def test_change_without_note_keeps_section_and_path():
    line = activity.describe_change("DELETE", "/api/tasks/5", 200)
    assert line == "«Задачи»: удаление (DELETE /api/tasks/5)"
    assert activity.describe_change("PUT", "/api/payouts/7", 403).endswith("ошибка 403")


def test_handler_note_replaces_generic_line():
    lines = activity.entries("u", "POST", "/api/masters/me/scan/confirm", 200, "/employee/scan",
                             ["скан: выход, заказ 123 — записан в Агбис"], now=0)
    assert lines == ["открыл «Скан» (кабинет мастера)", "скан: выход, заказ 123 — записан в Агбис"]


def test_note_collects_into_current_request():
    holder = activity.start_request()
    activity.note("отметил ученику день")
    assert holder == ["отметил ученику день"]


def test_one_log_file_per_person(tmp_path, monkeypatch):
    from app.utils import logger

    monkeypatch.setattr(logger, "USERS_LOG_DIR", tmp_path)
    monkeypatch.setattr(logger, "_user_loggers", {})
    monkeypatch.setattr(logger, "_user_log_filenames", {})
    (tmp_path / "1014523112_Армен.log").write_text("", encoding="utf-8")
    # Бот подписывает человека иначе, чем админка, — файл всё равно один.
    logger.log_user_action(1014523112, "@Ar_Oganov Armen", "нажал кнопку")
    for h in logger._user_loggers["1014523112"].handlers:
        h.flush()
        h.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["1014523112_Армен.log"]
    assert "нажал кнопку" in (tmp_path / "1014523112_Армен.log").read_text(encoding="utf-8")
