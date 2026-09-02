"""Фильтр по салону на вкладке «Заказы».

Фильтр приходит списком Salon.id — так его отдаёт /sales/salon-options и так
его понимают все соседние отчёты. В номере заказа при этом лежит другой
идентификатор: order_code салона, «34247-7» → «7». Раньше id подставлялся в
LIKE напрямую, условие получалось `doc_num LIKE '%-2b40ace9-75d5-...'`, и
вкладка была пуста при выборе ЛЮБОГО салона.

Firebird здесь не нужен: проверяется, какой SQL собирается и что делает
дочистка, поэтому соединение подменено.
"""
from datetime import date

import pytest

from app.services import firebird_service as fb


class _Salon:
    def __init__(self, sid, code, name, opened=None):
        self.id = sid
        self.order_code = code
        self.name = name
        self.opening_date = opened
        self.status = "active"


SALONS = [
    _Salon("uuid-ohta", "17", 'ТЦ "Охта Молл"'),
    _Salon("uuid-ozerki", "3", 'ТЦ "Озерки"'),
    _Salon("uuid-grand", "7", "Гранд Палас"),
    _Salon("uuid-passage", "7", "Пассаж"),
    _Salon("uuid-test", "", "Тестовый"),
]


class _Repo:
    """Ровно тот кусок SalonRepository, которым пользуется отчёт."""

    def __init__(self, salons):
        self._salons = {s.id: s for s in salons}

    def _load(self):
        pass

    def list_salons(self, status=None):
        return list(self._salons.values())

    def get_by_order_code(self, code, year=None, month=None):
        found = [s for s in self._salons.values() if (s.order_code or "") == str(code)]
        if not found:
            return None
        # Настоящий репозиторий разводит одинаковые коды по дате открытия;
        # здесь достаточно детерминированного выбора — тест на дочистку
        # задаёт нужный порядок сам.
        return found[0]


class _Cursor:
    def __init__(self, box, rows):
        self._box = box
        self._rows = rows

    def execute(self, sql, params=()):
        self._box["sql"] = sql
        self._box["params"] = params

    def fetchall(self):
        return self._rows


class _Con:
    def __init__(self, box, rows):
        self._box = box
        self._rows = rows

    def cursor(self):
        return _Cursor(self._box, self._rows)

    def close(self):
        pass


def row(doc_num, d=date(2026, 8, 15)):
    """Строка в том же порядке колонок, что и SELECT в отчёте."""
    return (doc_num, d, 1, "Клиент", "+79990000000", "Мастер 1234",
            None, None, 1000.0, 0.0, 1, 0, 0)


@pytest.fixture
def stub(monkeypatch):
    box = {"sql": "", "params": ()}
    rows = []
    repo = _Repo(SALONS)

    monkeypatch.setattr(fb, "FIREBIRD_AVAILABLE", True)
    monkeypatch.setattr(fb, "_connect", lambda: _Con(box, rows))
    monkeypatch.setattr("app.data.salon_repository.get_salon_repository", lambda: repo)
    box["rows"] = rows
    return box


def call(**kw):
    svc = fb.FirebirdService() if hasattr(fb, "FirebirdService") else fb.get_firebird_service()
    return svc.get_orders_for_period(date(2026, 8, 1), date(2026, 8, 31), **kw)


def like_params(box):
    return [p for p in box["params"] if isinstance(p, str) and p.startswith("%-")]


# ── трансляция id → код ──────────────────────────────────────────────────

def test_salon_id_is_translated_to_the_order_number_suffix(stub):
    """Собственно баг: в LIKE уходил UUID вместо «17»."""
    call(salon_ids=["uuid-ohta"])
    assert like_params(stub) == ["%-17"]
    assert "uuid-ohta" not in str(stub["params"])


def test_several_salons_give_several_suffixes(stub):
    call(salon_ids=["uuid-ohta", "uuid-ozerki"])
    assert sorted(like_params(stub)) == ["%-17", "%-3"]
    assert stub["sql"].count("d.doc_num LIKE ?") == 2


def test_no_salon_filter_adds_no_condition(stub):
    call()
    assert "d.doc_num LIKE" not in stub["sql"]


def test_unknown_salon_id_returns_nothing(stub):
    """Не «весь список»: фильтр выглядел бы проигнорированным."""
    assert call(salon_ids=["не-существует"]) == []


def test_salon_without_an_order_code_returns_nothing(stub):
    """«Тестовый» заведён без кода — сопоставить его заказам нечем."""
    assert call(salon_ids=["uuid-test"]) == []


def test_two_salons_sharing_a_code_query_it_once(stub):
    call(salon_ids=["uuid-grand", "uuid-passage"])
    assert like_params(stub) == ["%-7"]


# ── дочистка одинаковых кодов ────────────────────────────────────────────

def test_shared_code_is_narrowed_after_fetch(stub):
    """«Пассаж» и «Гранд Палас» оба «7»: SQL приносит обоих, в выдаче
    должен остаться только выбранный."""
    stub["rows"].extend([row("100-7"), row("101-7")])
    got = call(salon_ids=["uuid-grand"])          # _Repo отдаёт Гранд Палас
    assert len(got) == 2
    got = call(salon_ids=["uuid-passage"])
    assert got == []


def test_unique_code_is_not_narrowed(stub):
    stub["rows"].append(row("200-17"))
    got = call(salon_ids=["uuid-ohta"])
    assert [o["doc_num"] for o in got] == ["200-17"]


# ── витрина ──────────────────────────────────────────────────────────────

def test_row_carries_the_salon_name(stub):
    """«салон 17» ни о чём не говорит человеку, который только что выбрал
    в фильтре «Охта Молл»."""
    stub["rows"].append(row("200-17"))
    got = call(salon_ids=["uuid-ohta"])
    assert got[0]["salon"] == "17"
    assert got[0]["salon_id"] == "uuid-ohta"
    assert got[0]["salon_name"] == 'ТЦ "Охта Молл"'


def test_order_without_a_suffix_still_returns(stub):
    """Номер без суффикса салона не должен ронять выдачу."""
    stub["rows"].append(row("300"))
    got = call()
    assert got[0]["salon"] is None
    assert got[0]["salon_name"] == ""
