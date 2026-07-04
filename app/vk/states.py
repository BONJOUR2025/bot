"""FSM states for the VK bot — mirrors app/constants.py's Telegram states,
one state group per conversation. vkbottle's BaseStateGroup + state_dispenser
is the equivalent of python-telegram-bot's ConversationHandler states."""

from vkbottle import BaseStateGroup


class MenuStates(BaseStateGroup):
    AWAITING_MONTH_SALARY = 0
    AWAITING_MONTH_SCHEDULE = 1


class CabinetStates(BaseStateGroup):
    AWAITING_NEW_VALUE = 0
    AWAITING_EDIT_CONFIRM = 1


class PayoutStates(BaseStateGroup):
    SELECT_TYPE = 0
    ENTER_AMOUNT = 1
    SELECT_METHOD = 2
    CONFIRM = 3


class ShiftCheckinStates(BaseStateGroup):
    AWAITING_PHOTO = 0
