from app.services.payroll_service import PayrollService


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
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Зарплата", "Отклонено", "2025-01-10 10:00:00"),
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-20 10:00:00", amount=3000),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 8000


def test_paid_salary_request_resets_advances_cutoff():
    """An actually paid 'Зарплата' request is a real cutoff — only advances
    taken after it should still count."""
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Зарплата", "Выплачено", "2025-01-10 10:00:00"),
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-20 10:00:00", amount=3000),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 3000


def test_pending_salary_request_does_not_reset_advances_cutoff():
    """A still-pending 'Зарплата' request hasn't paid out either."""
    svc = PayrollService()
    svc._load_advance_records = lambda: [
        _row("Иван 1234", "Аванс", "Одобрено", "2025-01-05 10:00:00", amount=5000),
        _row("Иван 1234", "Зарплата", "Ожидает", "2025-01-10 10:00:00"),
    ]

    result = svc._get_advances_after_last_salary()

    assert result["1234"] == 5000
