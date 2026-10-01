"""Бот пошива: руководители и мастера — Telegram ID или @username."""
import pytest

from app.api.poshiv_bot import _norm_person


@pytest.mark.parametrize("raw,expected", [
    (123, 123), ("123", 123), (" 42 ", 42),
    ("@Ivan_Petrov", "@ivan_petrov"), ("ivan_petrov", "@ivan_petrov"),
    ("", None), (None, None),
])
def test_norm_person_ok(raw, expected):
    assert _norm_person(raw) == expected


@pytest.mark.parametrize("raw", ["@ab", "иван", "-5", "a b", 0])
def test_norm_person_rejects(raw):
    with pytest.raises(ValueError):
        _norm_person(raw)
