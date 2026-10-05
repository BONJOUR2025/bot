"""Способы выплат, закреплённые за сотрудником."""
from types import SimpleNamespace

from app.services import payout_methods as pm


def test_empty_means_all():
    assert pm.allowed_for(SimpleNamespace(payout_methods=[])) == pm.ALL_METHODS
    assert pm.allowed_for(None) == pm.ALL_METHODS


def test_only_known_methods_in_standard_order():
    emp = SimpleNamespace(payout_methods=["🤝 Наличными", "мусор", "💳 На карту", "🤝 Наличными"])
    assert pm.allowed_for(emp) == ["💳 На карту", "🤝 Наличными"]


def test_dict_employee():
    assert pm.allowed_for({"payout_methods": ["🤝 Наличными"]}) == ["🤝 Наличными"]


def test_describe():
    assert pm.describe(["🤝 Наличными"]) == "только наличными"
    assert pm.describe(["💳 На карту", "🤝 Наличными"]) == "на карту или наличными"


def test_employee_fields_survive_storage(tmp_path):
    from app.data.employee_repository import EmployeeRepository
    from app.data.json_storage import JsonStorage

    storage = JsonStorage(str(tmp_path / "user.json"))
    storage.save({"42": {"name": "Иванова", "payout_methods": ["🤝 Наличными"], "advance_auto_limit": 30000}})
    emp = EmployeeRepository(storage=storage).get_employee("42")
    assert emp.payout_methods == ["🤝 Наличными"]
    assert emp.advance_auto_limit == 30000
    # Старые записи без полей — всё разрешено, лимит общий.
    storage.save({"43": {"name": "Петрова"}})
    emp = EmployeeRepository(storage=storage).get_employee("43")
    assert emp.payout_methods == [] and emp.advance_auto_limit is None
