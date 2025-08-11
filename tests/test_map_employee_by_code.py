import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.analytics import map_employee_by_code


def test_map_known_code():
    assert map_employee_by_code("Оганов А.С.2404") == "Эмиль 2404"


def test_map_unknown_code():
    assert map_employee_by_code("Оганов А.С.9999") == "Оганов А.С.9999"


def test_map_with_spaces():
    assert map_employee_by_code("  Оганов    А.С.2602  ") == "Анастасия 2602"
