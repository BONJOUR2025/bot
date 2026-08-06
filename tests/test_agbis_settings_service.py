"""Tests for the "Настройки Agbis" page's category resolution.

Firebird is stubbed at _connect(), same pattern as test_daily_cash_balances.py.
What matters here: LOCAL_OPTIONS.FOLDER_ID resolved through
LOCAL_OPTIONS_TREE reproduces Agbis's own settings-dialog category
structure — this replaced an earlier keyword-guessing classifier that
dumped 98 of 665 options into an undifferentiated "Прочие настройки"
bucket; the tree-based version narrows that down to 25, matching Agbis's
own "Прочее" folder once the vendor-inheritance rule (see below) accounts
for the rest.
"""
from __future__ import annotations

import pytest

from app.services import agbis_settings_service as svc


class TestBreadcrumbResolver:
    def test_two_level_path(self):
        tree = [
            (20, None, "Кассы/ФР", 5),
            (22, 20, "АТОЛ", 1),
        ]
        resolve = svc._build_breadcrumb_resolver(tree)
        category, subgroup, sort_key = resolve(22)
        assert category == "Кассы/ФР"
        assert subgroup == "АТОЛ"
        assert sort_key == (5, 1)

    def test_option_directly_under_root_has_no_subgroup(self):
        tree = [(1, None, "Основные", 0)]
        resolve = svc._build_breadcrumb_resolver(tree)
        category, subgroup, _ = resolve(1)
        assert category == "Основные"
        assert subgroup is None

    def test_three_level_path_joins_the_middle_segments(self):
        tree = [
            (1, None, "Основные", 0),
            (3, 1, "Для заказов", 2),
            (28, 3, "В журнале заказов", 0),
        ]
        resolve = svc._build_breadcrumb_resolver(tree)
        category, subgroup, sort_key = resolve(28)
        assert category == "Основные"
        assert subgroup == "Для заказов → В журнале заказов"
        assert sort_key == (0, 2, 0)

    def test_unknown_folder_id_resolves_to_none(self):
        resolve = svc._build_breadcrumb_resolver([(1, None, "Основные", 0)])
        assert resolve(9999) == (None, None, ())

    def test_none_folder_id_resolves_to_none(self):
        resolve = svc._build_breadcrumb_resolver([(1, None, "Основные", 0)])
        assert resolve(None) == (None, None, ())

    def test_blank_named_node_is_skipped_in_the_breadcrumb_text(self):
        """A real gap in Agbis's own data (FOLDER_ID 378 under «Кассы/ФР»
        has no NAME) — the node still counts for ordering, it just
        contributes no visible breadcrumb segment."""
        tree = [
            (20, None, "Кассы/ФР", 5),
            (378, 20, "", 3),
        ]
        resolve = svc._build_breadcrumb_resolver(tree)
        category, subgroup, sort_key = resolve(378)
        assert category == "Кассы/ФР"
        assert subgroup is None
        assert sort_key == (5, 3)

    def test_cycle_does_not_infinite_loop(self):
        """Malformed data (a folder that is its own ancestor) must not hang
        the request — bail out via the seen-set rather than looping."""
        tree = [(1, 2, "A", 0), (2, 1, "B", 0)]
        resolve = svc._build_breadcrumb_resolver(tree)
        category, _, _ = resolve(1)
        assert category in ("A", "B")

    def test_memoized_result_is_identical_on_repeat_lookup(self):
        resolve = svc._build_breadcrumb_resolver([
            (20, None, "Кассы/ФР", 5), (22, 20, "АТОЛ", 1),
        ])
        assert resolve(22) == resolve(22)


class _FakeCursor:
    def __init__(self, tables):
        self._tables = tables
        self._result = []

    def execute(self, sql, params=None):
        s = sql.upper()
        if "LOCAL_OPTIONS_TREE" in s:
            self._result = self._tables["tree"]
        elif "LOCAL_OPTION_VALUES" in s:
            self._result = self._tables["values"]
        elif "LOCAL_COMPUTERS_LIST" in s:
            self._result = self._tables["computers"]
        elif "FROM DEPS" in s:
            self._result = self._tables["deps"]
        elif "FROM LOCAL_OPTIONS" in s:
            self._result = self._tables["options"]
        else:
            raise AssertionError(f"unexpected query: {sql[:80]}")

    def fetchall(self):
        return self._result


class _FakeConn:
    def __init__(self, tables):
        self._cursor = _FakeCursor(tables)

    def cursor(self):
        return self._cursor

    def close(self):
        pass


@pytest.fixture
def stub_db(monkeypatch):
    def install(tree=(), options=(), values=(), computers=(), deps=()):
        tables = {"tree": list(tree), "options": list(options), "values": list(values),
                  "computers": list(computers), "deps": list(deps)}
        monkeypatch.setattr(svc, "_connect", lambda *a, **k: _FakeConn(tables))
        monkeypatch.setattr(svc, "FIREBIRD_AVAILABLE", True)
    return install


# (id, folder_id, group, option_name, short, long, d_bool, d_int, d_str, d_float, order_num)
def _opt(oid, folder_id, group, name, short=None, d_bool=None):
    return (oid, folder_id, group, name, short, None, d_bool, None, None, None, 0)


ONE_COMPUTER = [(1, "ARM_21", "1.2.3.4", 0, "ARM_21.fdb")]


class TestMatrixCategorization:
    def test_option_lands_in_its_own_folders_category(self, stub_db):
        stub_db(
            tree=[(20, None, "Кассы/ФР", 0), (22, 20, "АТОЛ", 0)],
            options=[_opt(1, 22, "FiskAtol", "CommPort", "COM порт")],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        cats = {c["name"]: c for c in m["categories"]}
        assert "Кассы/ФР" in cats
        assert cats["Кассы/ФР"]["options"][0]["subgroup"] == "АТОЛ"

    def test_orphan_option_inherits_sibling_vendor_folder(self, stub_db):
        """The real case this exists for: BankName has no FOLDER_ID of its
        own, but other Sberbank options do — it should land next to them,
        not in an unlabeled bucket."""
        stub_db(
            tree=[(20, None, "Кассы/ФР", 0), (19, 20, "Сбербанк", 0)],
            options=[
                _opt(1, 19, "Sberbank", "SberPort", "Порт"),
                _opt(2, 19, "Sberbank", "SberHost", "Хост"),
                _opt(3, None, "Sberbank", "BankName", "Наименование банка"),
            ],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        cats = {c["name"]: c for c in m["categories"]}
        names = {o["option_name"]: o["subgroup"] for o in cats["Кассы/ФР"]["options"]}
        assert names["BankName"] == "Сбербанк"

    def test_orphan_with_no_folder_and_no_folder_ed_siblings_is_uncategorized(self, stub_db):
        stub_db(
            tree=[],
            options=[_opt(1, None, "SomeNewVendor", "SomeNewOption", "Что-то новое")],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        cats = {c["name"]: c for c in m["categories"]}
        assert "Без категории" in cats
        assert cats["Без категории"]["options"][0]["option_name"] == "SomeNewOption"

    def test_uncategorized_sorts_after_real_categories(self, stub_db):
        stub_db(
            tree=[(1, None, "Основные", 0)],
            options=[
                _opt(1, None, "X", "Orphan"),
                _opt(2, 1, "Y", "Grouped"),
            ],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        names = [c["name"] for c in m["categories"]]
        assert names.index("Основные") < names.index("Без категории")

    def test_categories_are_ordered_by_the_tree_root_order_num(self, stub_db):
        stub_db(
            tree=[(1, None, "Второй по счёту", 5), (2, None, "Первый по счёту", 1)],
            options=[_opt(1, 1, None, "A"), _opt(2, 2, None, "B")],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        names = [c["name"] for c in m["categories"]]
        assert names == ["Первый по счёту", "Второй по счёту"]

    def test_options_within_a_category_are_ordered_by_tree_then_own_order(self, stub_db):
        tree = [(1, None, "Root", 0), (2, 1, "B-folder", 2), (3, 1, "A-folder", 1)]
        options = [_opt(1, 2, None, "InB"), _opt(2, 3, None, "InA")]
        stub_db(tree=tree, options=options, computers=ONE_COMPUTER)
        m = svc.get_agbis_settings_matrix()
        opt_names = [o["option_name"] for o in m["categories"][0]["options"]]
        assert opt_names == ["InA", "InB"]

    def test_total_option_count_is_preserved(self, stub_db):
        stub_db(
            tree=[(1, None, "Root", 0)],
            options=[_opt(i, 1, None, f"Opt{i}") for i in range(5)],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        total = sum(len(c["options"]) for c in m["categories"])
        assert total == 5


class TestEffectiveValue:
    def test_override_wins_over_default(self, stub_db):
        stub_db(
            tree=[(1, None, "Root", 0)],
            options=[_opt(1, 1, None, "Toggle", d_bool=0)],
            values=[(1, 1, 1, None, None, None)],  # override: True
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        cell = m["categories"][0]["options"][0]["values"]["1"]
        assert cell == {"value": True, "source": "override"}

    def test_default_used_when_no_override(self, stub_db):
        stub_db(
            tree=[(1, None, "Root", 0)],
            options=[_opt(1, 1, None, "Toggle", d_bool=1)],
            values=[],
            computers=ONE_COMPUTER,
        )
        m = svc.get_agbis_settings_matrix()
        cell = m["categories"][0]["options"][0]["values"]["1"]
        assert cell == {"value": True, "source": "default"}


class TestFailureModes:
    def test_returns_empty_shape_when_driver_missing(self, monkeypatch):
        monkeypatch.setattr(svc, "FIREBIRD_AVAILABLE", False)
        assert svc.get_agbis_settings_matrix() == {"computers": [], "categories": []}

    def test_query_error_returns_empty_shape(self, monkeypatch):
        monkeypatch.setattr(svc, "FIREBIRD_AVAILABLE", True)

        def boom(*a, **k):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(svc, "_connect", boom)
        assert svc.get_agbis_settings_matrix() == {"computers": [], "categories": []}
