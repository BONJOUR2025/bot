import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.constants import PAYMENT_REQUEST_PATTERN


def test_payment_request_pattern_matches_regular_spaces():
    text = "💰 Запросить выплату"
    assert PAYMENT_REQUEST_PATTERN.match(text)


def test_payment_request_pattern_matches_nbsp():
    text = "\u00A0💰\u00A0Запросить\u00A0выплату\u00A0"
    assert PAYMENT_REQUEST_PATTERN.match(text)


def test_payment_request_pattern_ignore_case():
    text = "💰 ЗАПРОСИТЬ ВЫПЛАТУ"
    assert PAYMENT_REQUEST_PATTERN.match(text)
