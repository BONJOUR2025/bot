"""Связь задачи с кандидатом: фильтр, перенос, удаление.

Задача и next_attempt_at — не дубликат друг друга: задача напоминает человеку,
next_attempt_at решает, когда кандидат всплывёт в очереди. Проверяем ровно то,
где они обязаны совпасть (перенос) и где обязаны разойтись (удаление).
"""
from datetime import date, datetime, time

import pytest

from app.data.task_repository import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task_service import TaskService
from tests.conftest import run_async


@pytest.fixture
def service(tmp_path):
    return TaskService(repo=TaskRepository(file_path=str(tmp_path / "tasks.json")))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Отдельная база + подмена SessionLocal: schedule_from_task открывает
    сессию сам, поэтому подменять надо именно фабрику."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.db.session as session_module
    from app.models.recruitment import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(session_module, "SessionLocal", factory)
    s = factory()
    yield s
    s.close()


@pytest.fixture
def candidate(db):
    from app.models.recruitment import Candidate, Vacancy

    v = Vacancy(title="Мастер", is_open=True)
    db.add(v)
    db.commit()
    c = Candidate(vacancy_id=v.id, name="Иван", phone="+79990000000",
                  source="avito", stage="ответил")
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def call_hours_off(monkeypatch):
    """Окно звонков выключено: тест про синхронизацию, а не про окно —
    иначе результат зависел бы от config.json боевого стенда."""
    from app.services.config_service import ConfigService

    # Schedule — frozen dataclass, подменять его методы нельзя; подменяем
    # источник настроек. Пустой конфиг = расписание выключено.
    monkeypatch.setattr(ConfigService, "load", lambda self: {})


# ── фильтр ───────────────────────────────────────────────────────────────

def test_candidate_id_survives_the_json_roundtrip(service):
    created = run_async(service.create_task(
        TaskCreate(title="Позвонить: Иван", candidate_id=42)))

    assert created.candidate_id == 42
    assert (run_async(service.get_task(created.id))).candidate_id == 42


def test_list_filters_by_candidate(service):
    run_async(service.create_task(TaskCreate(title="Позвонить: Иван", candidate_id=42)))
    run_async(service.create_task(TaskCreate(title="Позвонить: Пётр", candidate_id=7)))
    run_async(service.create_task(TaskCreate(title="Обычная задача")))

    found = run_async(service.list_tasks(candidate_id=42))

    assert [t.title for t in found] == ["Позвонить: Иван"]


def test_ordinary_tasks_are_not_matched_by_candidate_filter(service):
    run_async(service.create_task(TaskCreate(title="Обычная задача")))

    assert run_async(service.list_tasks(candidate_id=42)) == []


# ── перенос ──────────────────────────────────────────────────────────────

def test_moving_the_task_moves_the_call(service, db, candidate, call_hours_off):
    task = run_async(service.create_task(TaskCreate(
        title="Позвонить: Иван", candidate_id=candidate.id,
        due_date=date(2026, 9, 1), due_time=time(14, 0))))

    run_async(service.update_task(task.id, TaskUpdate(due_date=date(2026, 9, 3))))

    db.refresh(candidate)
    assert candidate.next_attempt_at == datetime(2026, 9, 3, 14, 0)


def test_moving_only_the_time_moves_the_call(service, db, candidate,
                                                   call_hours_off):
    task = run_async(service.create_task(TaskCreate(
        title="Позвонить: Иван", candidate_id=candidate.id,
        due_date=date(2026, 9, 1), due_time=time(14, 0))))

    run_async(service.update_task(task.id, TaskUpdate(due_time=time(17, 30))))

    db.refresh(candidate)
    assert candidate.next_attempt_at == datetime(2026, 9, 1, 17, 30)


def test_renaming_the_task_leaves_the_schedule_alone(service, db, candidate,
                                                           call_hours_off):
    task = run_async(service.create_task(TaskCreate(
        title="Позвонить: Иван", candidate_id=candidate.id,
        due_date=date(2026, 9, 1), due_time=time(14, 0))))
    candidate.next_attempt_at = datetime(2026, 9, 1, 14, 0)
    db.commit()

    run_async(service.update_task(task.id, TaskUpdate(title="Позвонить: Иван Петров")))

    db.refresh(candidate)
    assert candidate.next_attempt_at == datetime(2026, 9, 1, 14, 0)


def test_task_without_candidate_touches_nothing(service, db, candidate,
                                                      call_hours_off):
    task = run_async(service.create_task(TaskCreate(
        title="Обычная задача", due_date=date(2026, 9, 1))))

    run_async(service.update_task(task.id, TaskUpdate(due_date=date(2026, 9, 3))))

    db.refresh(candidate)
    assert candidate.next_attempt_at is None


def test_moved_task_still_obeys_the_daily_veto(service, db, candidate,
                                                     call_hours_off):
    """Перенос задачи на сегодня после сегодняшнего недозвона не открывает
    второй звонок: normalize сдвигает время на следующий допустимый день."""
    from app.services import candidate_outreach as outreach
    from app.services.hours_window import local_now

    today = local_now()
    outreach.record_outcome(db, candidate, outreach.OUTCOME_NO_ANSWER, now=today)

    task = run_async(service.create_task(TaskCreate(
        title="Позвонить: Иван", candidate_id=candidate.id,
        due_date=today.date(), due_time=time(9, 0))))
    run_async(service.update_task(task.id, TaskUpdate(due_time=time(23, 0))))

    db.refresh(candidate)
    assert candidate.next_attempt_at.date() > today.date()


# ── удаление ─────────────────────────────────────────────────────────────

def test_deleting_the_task_does_not_cancel_the_call(service, db, candidate,
                                                          call_hours_off):
    """Удалённое напоминание не должно молча отменять звонок: задача —
    удобство для человека, а расписание живёт в карточке кандидата."""
    task = run_async(service.create_task(TaskCreate(
        title="Позвонить: Иван", candidate_id=candidate.id,
        due_date=date(2026, 9, 1), due_time=time(14, 0))))
    candidate.next_attempt_at = datetime(2026, 9, 1, 14, 0)
    db.commit()

    assert run_async(service.delete_task(task.id)) is True

    db.refresh(candidate)
    assert candidate.next_attempt_at == datetime(2026, 9, 1, 14, 0)
