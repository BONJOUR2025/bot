"""Плашка оплаты заказа: не оплачен / предоплата / оплачен."""
from app.services import order_payment as op


def test_states():
    assert op.payment(5860, 0)["state"] == "unpaid"
    p = op.payment(5860, 2911)
    assert p["state"] == "prepaid" and p["left"] == 2949
    assert op.payment(4380, 4380)["state"] == "paid"
    assert op.payment(1000, 1200)["state"] == "paid"      # переплата — оплачен
    assert op.payment(0, 0)["state"] == "paid"            # нечего платить


def test_attach_walks_nested_lists(monkeypatch):
    monkeypatch.setattr(op, "by_doc_nums", lambda nums: {n: op.payment(100, 0) for n in nums})
    data = {"wip": [{"doc_num": "1-1"}], "advice": {"queue": [{"doc_num": "2-2"}]}, "x": [{"name": "no doc"}]}
    op.attach(data)
    assert data["wip"][0]["payment"]["state"] == "unpaid"
    assert data["advice"]["queue"][0]["payment"]["state"] == "unpaid"
    assert "payment" not in data["x"][0]


def test_attach_survives_agbis_failure(monkeypatch):
    def boom(nums):
        raise RuntimeError("Firebird занят")
    monkeypatch.setattr(op, "by_doc_nums", boom)
    data = [{"doc_num": "1-1"}]
    assert op.attach(data) == [{"doc_num": "1-1"}]
