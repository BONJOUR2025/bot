"""Оплаты за день: деньги по видам и точкам, бонусы — не деньги, возвраты вычитаются."""
from datetime import date

from app.services import payments_service


class _Cur:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *a):
        pass

    def fetchall(self):
        return self._rows


class _Con:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _Cur(self._rows)

    def close(self):
        pass


def test_payments_split(monkeypatch):
    rows = [
        # doc_type, dep_src_id, count, debet, kredit
        (9, 8, 10, 65969.0, 0.0),
        (31, 8, 2, 5500.0, 0.0),
        (3, 1, 1, 23900.0, 200.0),   # центральная касса — наличные, офис
        (9, 7, 3, 1000.0, 560.0),    # возврат по карте
        (91, 8, 3, 2011.0, 0.0),     # бонусы — не деньги
        (4, 13, 1, 5000.0, 0.0),     # безнал по счёту
    ]
    import app.services.firebird_service as fb
    monkeypatch.setattr(fb, "_connect", lambda: _Con(rows))

    r = payments_service.payments(date(2026, 9, 30), date(2026, 9, 30))
    kinds = {k["key"]: k for k in r["kinds"]}
    assert kinds["card"]["amount"] == 65969 + 440
    assert kinds["cash"]["amount"] == 5500 + 23700
    assert kinds["bank"]["amount"] == 5000
    assert kinds["bonus"]["money"] is False and kinds["bonus"]["amount"] == 2011
    assert r["total"] == 65969 + 440 + 5500 + 23700 + 5000
    assert r["refunds"] == 760
    pts = {p["name"]: p for p in r["points"]}
    assert pts["Бестужевская"]["money"] == 71469 and pts["Бестужевская"]["cash"] == 5500
    assert pts["Гранд Палас"]["card"] == 440
    assert r["points"][-1]["name"] == "Офис / другое"
    assert pts["Офис / другое"]["money"] == 23700 + 5000
