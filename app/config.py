import json
from pathlib import Path

from .settings import Settings


def _load_settings() -> Settings:
    path = Path("config.json")
    data = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    allowed = {k: v for k, v in data.items() if k in Settings.__annotations__}
    return Settings(**allowed)


settings = _load_settings()

TOKEN = settings.telegram_bot_token
EXCEL_FILE = settings.excel_file
SALES_FILE = settings.sales_file
FIREBIRD_DB = settings.firebird_db
FIREBIRD_USER = settings.firebird_user
FIREBIRD_PASSWORD = settings.firebird_password
USERS_FILE = settings.users_file
ADVANCE_REQUESTS_FILE = settings.advance_requests_file
VACATIONS_FILE = settings.vacations_file
ADJUSTMENTS_FILE = settings.adjustments_file
BONUSES_PENALTIES_FILE = settings.bonuses_penalties_file
ASSETS_FILE = settings.assets_file
ADMIN_ID = settings.admin_id
ADMIN_CHAT_ID = settings.admin_chat_id
ADMIN_LOGIN = settings.admin_login
ADMIN_PASSWORD = settings.admin_password
USER_LOGIN = settings.user_login
USER_PASSWORD = settings.user_password
FONT_PATH = settings.font_path
MAX_ADVANCE_AMOUNT_PER_MONTH = settings.max_advance_amount_per_month
CARD_DISPATCH_CHAT_ID = settings.card_dispatch_chat_id
SECRET_KEY = settings.secret_key
