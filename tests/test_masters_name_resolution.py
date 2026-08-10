"""Resolving a Firebird master name (e.g. "Рудем Г.") to a bot employee id.

Covers the exact-name and surname+initial paths in
app/services/masters_service._employee_lookup_for_masters, plus the
_KNOWN_FIREBIRD_ALIASES escape hatch for the one real account where
Firebird's own name shape doesn't reduce to either.
"""
from __future__ import annotations

from app.services import masters_service as ms


def _resolve(name, users, monkeypatch, tmp_json):
    from app.settings import settings

    path = tmp_json("user.json", users)
    monkeypatch.setattr(settings, "users_file", path)
    exact, by_surname_initial = ms._employee_lookup_for_masters()
    return ms._resolve_master_employee_id(name, exact, by_surname_initial)


def test_exact_name_match(monkeypatch, tmp_json):
    users = {"1": {"name": "Рудем Г.", "full_name": "Галиулин Рудем Радикович"}}
    assert _resolve("Рудем Г.", users, monkeypatch, tmp_json) == "1"


def test_surname_initial_fallback(monkeypatch, tmp_json):
    users = {"1": {"name": "Мартиросян А.", "full_name": "Мартиросян Артём Сергеевич"}}
    assert _resolve("Мартиросян А.", users, monkeypatch, tmp_json) == "1"


def test_known_alias_resolves_even_when_bot_name_no_longer_matches(monkeypatch, tmp_json):
    """The real case that triggered this: employee's bot `name` was renamed
    to the standard "Фамилия И." format ("Галиулин Р."), but Firebird still
    records this specific master as "Рудем Г." — neither the exact-name path
    nor the surname+initial fallback ("галиулин", "Р") can bridge that on
    their own, so the alias table is the only thing that still resolves it."""
    users = {
        "20456189804": {"name": "Галиулин Р.", "full_name": "Галиулин Рудем Радикович"},
    }
    assert _resolve("Рудем Г.", users, monkeypatch, tmp_json) == "20456189804"
    # Their own current name/surname+initial keys still resolve too.
    assert _resolve("Галиулин Р.", users, monkeypatch, tmp_json) == "20456189804"


def test_alias_does_not_override_a_real_exact_match(monkeypatch, tmp_json):
    """If some other, unrelated employee's bot `name` genuinely is "Рудем Г.",
    that real match wins — the alias only fills in when nothing else claims
    the name (see the setdefault in _employee_lookup_for_masters)."""
    users = {
        "999": {"name": "Рудем Г.", "full_name": "Рудем Геннадий Олегович"},
        "20456189804": {"name": "Галиулин Р.", "full_name": "Галиулин Рудем Радикович"},
    }
    assert _resolve("Рудем Г.", users, monkeypatch, tmp_json) == "999"
