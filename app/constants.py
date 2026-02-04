from enum import Enum, auto
import re
from .core.enums import PAYOUT_STATUSES


class UserStates(Enum):
    SELECT_DATA_TYPE = auto()
    SELECT_MONTH = auto()
    SELECT_EMPLOYEE = auto()
    BROADCAST_MESSAGE = auto()
    BROADCAST_CONFIRM = auto()
    SELECT_PAYOUT_TYPE = auto()
    SELECT_PERIOD = auto()
    SELECT_STATUS = auto()
    SELECT_SORT = auto()
    SHOW_PAYOUTS = auto()
    SEND_PERSONAL_MESSAGE = auto()
    SELECT_USER_FOR_MESSAGE = auto()
    SELECT_EMPLOYEE_FILTER = auto()


class PayoutStates(Enum):
    REQUEST_PAYOUT = auto()
    SELECT_TYPE = auto()
    ENTER_AMOUNT = auto()
    SELECT_METHOD = auto()
    CONFIRM_CARD = auto()


class ManualPayoutStates(Enum):
    """Состояния для диалога ручного создания выплаты администратором."""

    SELECT_EMPLOYEE = auto()
    SELECT_TYPE = auto()
    ENTER_AMOUNT = auto()
    SELECT_METHOD = auto()
    CONFIRM = auto()


class AdvanceReportStates(Enum):
    ENTER_START_DATE = auto()
    ENTER_END_DATE = auto()
    SELECT_STATUS = auto()


PAYMENT_REQUEST_PATTERN = re.compile(
    r"^[\s\u00A0\u200b\u200c\uFEFF]*💰[\s\u00A0\u200b\u200c\uFEFF]*Запросить[\s\u00A0\u200b\u200c\uFEFF]*выплату[\s\u00A0\u200b\u200c\uFEFF]*$",
    re.IGNORECASE,
)

