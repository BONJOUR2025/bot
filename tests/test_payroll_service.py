from dataclasses import dataclass

import pytest

from app.services.payroll_service import PayrollRow, PayrollService
from app.data.salon_repository import SalonRepository
from app.schemas.salon import SalonCreate


def _row(name, payout_type, status, timestamp, amount=0):
    return {
        "name": name,
        "payout_type": payout_type,
        "status": status,
        "timestamp": timestamp,
        "amount": amount,
    }


def test_rejected_salary_request_does_not_reset_advances_cutoff():
    """A rejected 'Зарплата' request was never actually paid out, so it must
    not act as a cutoff — advances taken before it still count."""
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Зарплата", "Отклонено", "2025-01-10 10:00:00"),
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-20 10:00:00", amount=3000),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 8000


def test_paid_salary_request_resets_advances_cutoff():
    """An actually paid 'Зарплата' request is a real cutoff — only advances
    taken after it should still count."""
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Зарплата", "Выплачено", "2025-01-10 10:00:00"),
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-20 10:00:00", amount=3000),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 3000


def test_pending_salary_request_does_not_reset_advances_cutoff():
    """A still-pending 'Зарплата' request hasn't paid out either."""
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Зарплата", "Ожидает", "2025-01-10 10:00:00"),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 5000


def test_approved_but_not_paid_advance_is_not_counted():
    """Only actually disbursed ('Выплачено') advances count — an approved
    but not-yet-paid-out advance must not be deducted yet."""
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-20 10:00:00", amount=3000),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 3000


def test_advances_for_month_only_counts_paid():
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Аванс", "Выплачено", "2025-01-20 10:00:00", amount=3000),
    ]

    result = svc._get_advances_for_month(2025, 1)

    assert result["1234"] == 3000


# ---------------------------------------------------------------------------
# get_payroll_by_salon
# ---------------------------------------------------------------------------

def _payroll_row(code="1234", name="Иван 1234", **overrides) -> PayrollRow:
    defaults = dict(
        employee_code=code,
        employee_name=name,
        base_salary=0.0,
        repair_sales=0.0,
        cosmetics_sales=0.0,
        shoes_sales=0.0,
        repair_plan=0.0,
        cosmetics_plan=0.0,
        shoes_plan=0.0,
        repair_fulfillment=0.0,
        cosmetics_fulfillment=0.0,
        shoes_fulfillment=0.0,
        repair_rate=0.02,
        cosmetics_rate=0.08,
        shoes_rate=0.0,
        repair_commission=0.0,
        cosmetics_commission=0.0,
        shoes_commission=0.0,
        bonuses=0.0,
        excel_bonus=0.0,
        penalties=0.0,
        advances=0.0,
        advances_this_month=0.0,
        ignore_kpi=False,
        force_max=[],
        force_min=[],
        shoes_orders=[],
        total_commission=0.0,
        total_gross=0.0,
        total_deductions=0.0,
        total_net=0.0,
        shifts_by_point={},
    )
    defaults.update(overrides)
    return PayrollRow(**defaults)


@dataclass
class _FakeSalon:
    id: str
    name: str
    code: str = ""
    order_code: str = ""


class _FakeSalonRepo:
    """Minimal stand-in for SalonRepository, keyed by `code`/`order_code`."""

    def __init__(self, by_code: dict[str, _FakeSalon] | None = None,
                 by_order_code: dict[str, _FakeSalon] | None = None) -> None:
        self._by_code = by_code or {}
        self._by_order_code = by_order_code or {}

    def get_by_code(self, code: str):
        return self._by_code.get(code)

    def get_by_order_code(self, order_code: str, year: int | None = None, month: int | None = None):
        return self._by_order_code.get(order_code)


def _mock_internal(svc, rows, order_detail, unknown_codes=None):
    async def _fake(month, year=None):
        return rows, unknown_codes or [], order_detail
    svc._calculate_payroll_internal = _fake


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_by_salon_ignore_kpi_zeroes_commission_everywhere():
    """ignore_kpi zeroes the row's final commission but not its resolved
    rates — the by-salon report must not resurrect commission via rate×sales."""
    svc = PayrollService()
    salon_a = _FakeSalon(id="salon-a", name="Салон А")
    svc.salon_repo = _FakeSalonRepo(
        by_code={"A": salon_a}, by_order_code={"1": salon_a}
    )
    row = _payroll_row(
        ignore_kpi=True,
        base_salary=1000.0,
        shifts_by_point={"A": 10},
        repair_rate=0.02,
        cosmetics_rate=0.08,
    )
    order_detail = {
        "1234": {
            "repair_orders": [{"doc_num": "555-1", "kredit": 1000.0}],
            "cosmetics_orders": [{"doc_num": "555-1", "kredit": 500.0}],
            "shoes_order_items": [{"doc_num": "555-1", "kredit": 12000.0}],
        }
    }
    _mock_internal(svc, [row], order_detail)

    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))

    assert result["grand_total"]["repair_commission"] == 0.0
    assert result["grand_total"]["cosmetics_commission"] == 0.0
    assert result["grand_total"]["shoes_commission"] == 0.0
    assert result["grand_total"]["oklad"] == 1000.0


def test_by_salon_unrecognized_code_goes_to_unallocated_and_reconciles():
    svc = PayrollService()
    svc.salon_repo = _FakeSalonRepo()  # nothing resolves
    row = _payroll_row(
        base_salary=1000.0,
        shifts_by_point={"A": 10},
        repair_rate=0.02,
        cosmetics_rate=0.08,
        repair_commission=20.0,
        cosmetics_commission=40.0,
        shoes_commission=1000.0,
        total_commission=1060.0,
    )
    order_detail = {
        "1234": {
            "repair_orders": [{"doc_num": "555-9", "kredit": 1000.0}],
            "cosmetics_orders": [{"doc_num": "555-9", "kredit": 500.0}],
            "shoes_order_items": [{"doc_num": "555-9", "kredit": 12000.0}],
        }
    }
    _mock_internal(svc, [row], order_detail)

    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))

    assert len(result["salons"]) == 1
    bucket = result["salons"][0]
    assert bucket["salon_id"] == PayrollService.UNALLOCATED_SALON_ID
    assert bucket["salon_name"] == PayrollService.UNALLOCATED_SALON_NAME
    assert result["grand_total"]["repair_commission"] == pytest.approx(20.0)
    assert result["grand_total"]["cosmetics_commission"] == pytest.approx(40.0)
    assert result["grand_total"]["shoes_commission"] == pytest.approx(1000.0)
    assert (
        result["grand_total"]["repair_commission"]
        + result["grand_total"]["cosmetics_commission"]
        + result["grand_total"]["shoes_commission"]
        == pytest.approx(row.total_commission)
    )


def test_by_salon_bonuses_included_and_reconciles_with_total_gross():
    """Regression: премии (bonuses/excel_bonus) не привязаны к продаже, но
    обязаны попасть в отчёт — иначе ФОТ по салонам расходится с ФОТ на
    странице расчёта зарплаты (total_gross)."""
    svc = PayrollService()
    salon_a = _FakeSalon(id="salon-a", name="Салон А")
    svc.salon_repo = _FakeSalonRepo(by_code={"A": salon_a}, by_order_code={"1": salon_a})

    total_commission = 20.0 + 40.0 + 1000.0
    row = _payroll_row(
        base_salary=1000.0,
        shifts_by_point={"A": 10},
        bonuses=500.0,
        excel_bonus=200.0,
        repair_rate=0.02,
        cosmetics_rate=0.08,
        repair_commission=20.0,
        cosmetics_commission=40.0,
        shoes_commission=1000.0,
        total_commission=total_commission,
        total_gross=1000.0 + total_commission + 500.0 + 200.0,
    )
    order_detail = {
        "1234": {
            "repair_orders": [{"doc_num": "555-1", "kredit": 1000.0}],
            "cosmetics_orders": [{"doc_num": "555-1", "kredit": 500.0}],
            "shoes_order_items": [{"doc_num": "555-1", "kredit": 12000.0}],
        }
    }
    _mock_internal(svc, [row], order_detail)

    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))

    assert result["grand_total"]["bonuses"] == pytest.approx(700.0)
    assert result["grand_total"]["total"] == pytest.approx(row.total_gross)


def test_by_salon_oklad_split_by_shifts_with_unresolved_and_empty_fallback():
    svc = PayrollService()
    salon_a = _FakeSalon(id="salon-a", name="Салон А")
    svc.salon_repo = _FakeSalonRepo(by_code={"A": salon_a})

    row1 = _payroll_row(
        code="1111", name="Иван 1111",
        base_salary=1500.0, shifts_by_point={"A": 10, "B": 5},
    )
    row2 = _payroll_row(
        code="2222", name="Пётр 2222",
        base_salary=500.0, shifts_by_point={},
    )
    _mock_internal(svc, [row1, row2], {"1111": {}, "2222": {}})

    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))

    by_id = {s["salon_id"]: s for s in result["salons"]}
    assert by_id["salon-a"]["oklad"] == pytest.approx(1500.0 * 10 / 15)
    unalloc = by_id[PayrollService.UNALLOCATED_SALON_ID]
    # row1's "B" portion + row2's entirely-unresolved base_salary
    assert unalloc["oklad"] == pytest.approx(1500.0 * 5 / 15 + 500.0)
    assert result["grand_total"]["oklad"] == pytest.approx(2000.0)


def test_by_salon_shoes_per_pair_rule_and_force_overrides():
    svc = PayrollService()
    salon_a = _FakeSalon(id="salon-a", name="Салон А")
    svc.salon_repo = _FakeSalonRepo(by_order_code={"1": salon_a})

    row_normal = _payroll_row(code="1111", name="Иван 1111")
    order_detail_normal = {
        "1111": {
            "repair_orders": [], "cosmetics_orders": [],
            "shoes_order_items": [
                {"doc_num": "555-1", "kredit": 12000.0},  # > 11000 -> 1000
                {"doc_num": "556-1", "kredit": 5000.0},   # <= 11000 -> 500
            ],
        }
    }
    _mock_internal(svc, [row_normal], order_detail_normal)
    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))
    assert result["grand_total"]["shoes_commission"] == pytest.approx(1500.0)

    row_force_max = _payroll_row(code="1111", name="Иван 1111", force_max=["shoes"])
    order_detail_force_max = {
        "1111": {
            "repair_orders": [], "cosmetics_orders": [],
            "shoes_order_items": [{"doc_num": "555-1", "kredit": 5000.0}],
        }
    }
    _mock_internal(svc, [row_force_max], order_detail_force_max)
    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))
    assert result["grand_total"]["shoes_commission"] == pytest.approx(1000.0)

    row_force_min = _payroll_row(code="1111", name="Иван 1111", force_min=["shoes"])
    order_detail_force_min = {
        "1111": {
            "repair_orders": [], "cosmetics_orders": [],
            "shoes_order_items": [{"doc_num": "555-1", "kredit": 12000.0}],
        }
    }
    _mock_internal(svc, [row_force_min], order_detail_force_min)
    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))
    assert result["grand_total"]["shoes_commission"] == pytest.approx(500.0)


def test_apply_sale_transfers_moves_repair_orders_list_and_scalar(monkeypatch):
    svc = PayrollService()
    sales_data = {
        "1001": {
            "repair": 1000.0, "cosmetics": 0.0, "shoes": 0.0,
            "repair_orders": [{"doc_num": "555-1", "kredit": 1000.0}],
            "cosmetics_orders": [], "shoes_orders": [],
        }
    }

    def _fake_list_transfers(month_key):
        return [{
            "from_category": "repair", "to_category": "repair",
            "from_code": "1001", "to_code": "2002",
            "amount": 1000.0, "doc_num": "555-1",
        }]

    import app.services.sale_transfer_service as sale_transfer_service
    monkeypatch.setattr(sale_transfer_service, "list_transfers", _fake_list_transfers)

    svc._apply_sale_transfers(sales_data, "JANUARY-2025")

    assert sales_data["1001"]["repair"] == 0.0
    assert sales_data["1001"]["repair_orders"] == []
    assert sales_data["2002"]["repair"] == 1000.0
    assert sales_data["2002"]["repair_orders"] == [{"doc_num": "555-1", "kredit": 1000.0}]


def test_salon_repository_get_by_order_code(tmp_path):
    repo = SalonRepository(path=tmp_path / "salons.json")
    salon = repo.create(SalonCreate(name="Салон на Ленина", code="A", order_code="7"))
    repo.create(SalonCreate(name="Другой салон", code="B", order_code="12"))

    assert repo.get_by_order_code("7").id == salon.id
    assert repo.get_by_order_code(" 7 ").id == salon.id
    assert repo.get_by_order_code("99") is None
    assert repo.get_by_order_code("") is None


def test_get_by_order_code_disambiguates_renamed_salon_by_opening_date(tmp_path):
    """Regression: «Пассаж» (код "П") переехал и стал «Гранд Палас» (код
    "Гп") в мае, но номер заказа в Firebird ("...-7") не изменился — обе
    записи Salon имеют order_code="7". Без учёта месяца это раньше
    разъезжалось произвольно (по порядку словаря)."""
    repo = SalonRepository(path=tmp_path / "salons.json")
    old_salon = repo.create(SalonCreate(name="Пассаж", code="П", order_code="7"))
    new_salon = repo.create(SalonCreate(name="Гранд Палас", code="Гп", order_code="7", opening_date="2025-05-01"))

    # До переезда (январь) должен резолвиться только старый салон —
    # «Гранд Палас» с точки зрения графика ещё не существовал.
    assert repo.get_by_order_code("7", 2025, 1).id == old_salon.id
    assert repo.get_by_order_code("7", 2025, 4).id == old_salon.id

    # В месяц переезда и после — уже новый.
    assert repo.get_by_order_code("7", 2025, 5).id == new_salon.id
    assert repo.get_by_order_code("7", 2025, 12).id == new_salon.id

    # Без указания месяца — прежнее поведение (первый найденный), для
    # обратной совместимости c уже существующими вызовами.
    assert repo.get_by_order_code("7") is not None


def test_get_by_order_code_ambiguous_without_opening_date_returns_none(tmp_path):
    """Если ни у одной из задвоенных записей нет opening_date — различить
    их по месяцу нечем, лучше явно не угадать, чем молча приписать не тому
    салону."""
    repo = SalonRepository(path=tmp_path / "salons.json")
    repo.create(SalonCreate(name="Пассаж", code="П", order_code="7"))
    repo.create(SalonCreate(name="Гранд Палас", code="Гп", order_code="7"))

    assert repo.get_by_order_code("7", 2025, 1) is None


def test_by_salon_renamed_salon_attributed_to_correct_era(tmp_path):
    """End-to-end: комиссия за январь должна целиком уйти на «Пассаж», а
    не разъехаться с ещё не существовавшим на тот момент «Гранд Паласом»,
    даже если обе записи имеют order_code="7"."""
    repo = SalonRepository(path=tmp_path / "salons.json")
    old_salon = repo.create(SalonCreate(name="Пассаж", code="П", order_code="7"))
    repo.create(SalonCreate(name="Гранд Палас", code="Гп", order_code="7", opening_date="2025-05-01"))

    svc = PayrollService()
    svc.salon_repo = repo

    row = _payroll_row(repair_rate=0.02, cosmetics_rate=0.08)
    order_detail = {
        "1234": {
            "repair_orders": [{"doc_num": "555-7", "kredit": 1000.0}],
            "cosmetics_orders": [],
            "shoes_order_items": [],
        }
    }
    _mock_internal(svc, [row], order_detail)

    result = _run(svc.get_payroll_by_salon("JANUARY", 2025))

    salon_ids = {s["salon_id"] for s in result["salons"]}
    assert salon_ids == {old_salon.id}
    assert result["grand_total"]["repair_commission"] == pytest.approx(20.0)
