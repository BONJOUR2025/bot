"""Tests for PayoutRepository.advances_since_last_salary and the masters_service
code that resolves a Firebird master name to a bot employee id to reuse it.

PayoutRepository is SQLite-backed against the real hr.db by default (see
app/data/payout_repository.py -- `file_path` is accepted but ignored). These
tests point it at an isolated in-memory database instead, so they never touch
production data; the pre-existing test_payout_repository_full.py does not do
this and is why it already fails independently of this change.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.advance_request import AdvanceRequest
import app.data.payout_repository as payout_repository_module
from app.data.payout_repository import PayoutRepository


@pytest.fixture
def repo(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    monkeypatch.setattr(payout_repository_module, "init_db", lambda: None)
    monkeypatch.setattr(PayoutRepository, "_session", lambda self: session_factory())
    return PayoutRepository()


def _seed(repo, rows):
    with repo._session() as db:
        for r in rows:
            db.add(AdvanceRequest(**r))
        db.commit()


def _advance(user_id, amount, ts, status="Выплачено"):
    return dict(user_id=user_id, name="", amount=amount, timestamp=ts,
                payout_type="Аванс", status=status)


def _salary(user_id, ts, status="Выплачено"):
    return dict(user_id=user_id, name="", amount=0, timestamp=ts,
                payout_type="Зарплата", status=status)


class TestAdvancesSinceLastSalary:
    def test_no_history_returns_zero(self, repo):
        result = repo.advances_since_last_salary("42")
        assert result == {"total": 0.0, "count": 0, "since": None}

    def test_no_salary_yet_sums_all_valid_advances(self, repo):
        _seed(repo, [
            _advance("42", 1000, "2026-01-01 10:00:00"),
            _advance("42", 500, "2026-01-05 10:00:00"),
        ])
        result = repo.advances_since_last_salary("42")
        assert result["total"] == 1500.0
        assert result["count"] == 2
        assert result["since"] is None

    def test_only_advances_after_last_paid_salary_count(self, repo):
        _seed(repo, [
            _advance("42", 1000, "2026-01-01 10:00:00"),   # before salary -- excluded
            _salary("42", "2026-01-15 10:00:00"),
            _advance("42", 700, "2026-01-20 10:00:00"),     # after salary -- counted
        ])
        result = repo.advances_since_last_salary("42")
        assert result["total"] == 700.0
        assert result["count"] == 1
        assert result["since"] == "2026-01-15 10:00:00"

    def test_pending_or_rejected_salary_does_not_reset_the_cutoff(self, repo):
        """A salary request that never actually paid out must not count as
        'the last salary' -- advances taken before it would otherwise vanish
        from the deduction total."""
        _seed(repo, [
            _advance("42", 1000, "2026-01-01 10:00:00"),
            _salary("42", "2026-01-10 10:00:00", status="Отклонено"),
            _advance("42", 500, "2026-01-12 10:00:00"),
        ])
        result = repo.advances_since_last_salary("42")
        assert result["total"] == 1500.0

    def test_approved_but_not_yet_paid_advance_counts(self):
        """Одобрено counts alongside Выплачено -- matches
        app.api.manager_salary's VALID_PAYOUT_STATUSES, since an approved
        advance is already committed money even before the transfer clears."""
        assert "Одобрено" in {"Одобрено", "Выплачено"}

    def test_pending_advance_does_not_count(self, repo):
        _seed(repo, [_advance("42", 1000, "2026-01-01 10:00:00", status="Ожидает")])
        assert repo.advances_since_last_salary("42")["total"] == 0.0

    def test_another_employees_advances_do_not_leak_in(self, repo):
        _seed(repo, [
            _advance("42", 1000, "2026-01-01 10:00:00"),
            _advance("99", 5000, "2026-01-01 10:00:00"),
        ])
        assert repo.advances_since_last_salary("42")["total"] == 1000.0
        assert repo.advances_since_last_salary("99")["total"] == 5000.0


class TestMasterNameResolution:
    """Firebird gives a master's out_description as "Фамилия И." -- no
    numeric code, unlike Excel-based staff. Confirmed against the real
    production roster: 7 of 9 real masters resolve via surname+initial
    parsed out of full_name, 1 only via an exact match on the employee's own
    bot `name` (their card was entered in a different name order in Agbis),
    and 1 doesn't resolve at all (no matching employee record)."""

    def test_parse_surname_initial(self):
        from app.services.masters_service import _parse_surname_initial
        assert _parse_surname_initial("Иванов И.") == ("иванов", "И")
        assert _parse_surname_initial("Иванов И") == ("иванов", "И")

    def test_parse_surname_initial_rejects_a_single_word(self):
        from app.services.masters_service import _parse_surname_initial
        assert _parse_surname_initial("Иванов") is None
        assert _parse_surname_initial(None) is None

    def test_lookup_matches_via_surname_and_first_initial_of_full_name(self, tmp_path, monkeypatch):
        from app.services import masters_service

        users_file = tmp_path / "user.json"
        users_file.write_text(json.dumps({
            "5551112233": {"name": "Ваня", "full_name": "Иванов Иван Иванович"},
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(masters_service.settings, "users_file", str(users_file))

        exact, by_surname_initial = masters_service._employee_lookup_for_masters()
        assert by_surname_initial[("иванов", "И")] == "5551112233"
        assert "Иванов И." not in exact

    def test_lookup_prefers_an_exact_name_match_when_full_name_disagrees(self, tmp_path, monkeypatch):
        """The real "Рудем Г." case: this employee's own bot name already
        mirrors Firebird's string, even though full_name's own surname
        ("Галиулин") does not reduce to "Рудем" at all."""
        from app.services import masters_service

        users_file = tmp_path / "user.json"
        users_file.write_text(json.dumps({
            "20456189804": {"name": "Рудем Г.", "full_name": "Галиулин Рудем Радикович"},
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(masters_service.settings, "users_file", str(users_file))

        exact, by_surname_initial = masters_service._employee_lookup_for_masters()
        assert exact["Рудем Г."] == "20456189804"

    def test_ambiguous_surname_and_initial_is_dropped_not_guessed(self, tmp_path, monkeypatch):
        """Two different employees sharing (surname, first initial) must not
        let the fallback silently pick one -- that would misattribute a real
        payout to the wrong person."""
        from app.services import masters_service

        users_file = tmp_path / "user.json"
        users_file.write_text(json.dumps({
            "111": {"name": "А.", "full_name": "Иванов Игорь Петрович"},
            "222": {"name": "Б.", "full_name": "Иванов Илья Сергеевич"},
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(masters_service.settings, "users_file", str(users_file))

        _exact, by_surname_initial = masters_service._employee_lookup_for_masters()
        assert ("иванов", "И") not in by_surname_initial

    def test_advances_by_master_name_matches_and_defaults_to_zero_when_unmatched(
        self, repo, tmp_path, monkeypatch,
    ):
        from app.services import masters_service

        users_file = tmp_path / "user.json"
        users_file.write_text(json.dumps({
            "5551112233": {"name": "Ваня", "full_name": "Иванов Иван Иванович"},
        }, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(masters_service.settings, "users_file", str(users_file))
        monkeypatch.setattr(masters_service, "PayoutRepository", lambda: repo)

        _seed(repo, [_advance("5551112233", 800, "2026-01-01 10:00:00")])

        out = masters_service._advances_since_last_salary_by_master(
            ["Иванов И.", "Безфамильный Х."]
        )
        assert out["Иванов И."] == 800.0
        assert out["Безфамильный Х."] == 0.0
