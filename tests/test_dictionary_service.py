import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.dictionary_service import DictionaryService
from app.core.enums import PAYOUT_STATUSES, EmployeeStatus
from app.core.constants import PAYOUT_METHODS, PAYOUT_TYPES


def test_load_includes_defaults(tmp_path):
    path = tmp_path / "dict.json"
    service = DictionaryService(path)
    data = service.load()
    assert set(data["payout_statuses"]) >= set(PAYOUT_STATUSES)
    assert set(data["payout_methods"]) >= set(PAYOUT_METHODS)
    assert set(data["payout_types"]) >= set(PAYOUT_TYPES)
    assert set(data["employee_statuses"]) >= {s.value for s in EmployeeStatus}

