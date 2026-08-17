import json
from pathlib import Path
from typing import Any, Iterable

from .settings import Settings


def _load_settings() -> Settings:
    path = Path("config.json")
    data = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    allowed = {k: v for k, v in data.items() if k in Settings.__annotations__}
    return Settings(**allowed)


def _normalize_card_dispatch_chats(
    raw_chats: Iterable[dict[str, Any]] | None,
    fallback_chat_id: int | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if raw_chats:
        for idx, entry in enumerate(raw_chats, start=1):
            if not isinstance(entry, dict):
                continue
            chat_id = entry.get("chat_id")
            try:
                chat_id_int = int(chat_id)
            except (TypeError, ValueError):
                continue
            key = entry.get("key") or entry.get("id") or f"chat_{idx}"
            name = entry.get("name") or f"Кассир {idx}"
            normalized.append(
                {
                    "key": str(key),
                    "name": str(name),
                    "chat_id": chat_id_int,
                }
            )
    if not normalized and fallback_chat_id:
        try:
            chat_id_int = int(fallback_chat_id)
        except (TypeError, ValueError):
            chat_id_int = None
        if chat_id_int:
            normalized.append(
                {
                    "key": "default",
                    "name": "Основной кассир",
                    "chat_id": chat_id_int,
                }
            )
    return normalized


settings = _load_settings()

TOKEN = settings.telegram_bot_token
VK_API_TOKEN = settings.vk_api_token
EXCEL_FILE = settings.excel_file
USERS_FILE = settings.users_file
ADVANCE_REQUESTS_FILE = settings.advance_requests_file
VACATIONS_FILE = settings.vacations_file
LEAVE_REQUESTS_FILE = settings.leave_requests_file
EMPLOYEE_MESSAGES_FILE = settings.employee_messages_file
ADJUSTMENTS_FILE = settings.adjustments_file
BONUSES_PENALTIES_FILE = settings.bonuses_penalties_file
SHIFT_CHECKINS_FILE = settings.shift_checkins_file
VISITOR_EVENTS_FILE = settings.visitor_events_file
VISITOR_COUNTER_RESETS_FILE = settings.visitor_counter_resets_file
BOT_USERS_FILE = settings.bot_users_file
VK_BOT_USERS_FILE = settings.vk_bot_users_file
ASSETS_FILE = settings.assets_file
ADMIN_ID = settings.admin_id
ADMIN_CHAT_ID = settings.admin_chat_id
ADMIN_LOGIN = settings.admin_login
ADMIN_PASSWORD = settings.admin_password
USER_LOGIN = settings.user_login
USER_PASSWORD = settings.user_password
FONT_PATH = settings.font_path
MAX_ADVANCE_AMOUNT_PER_MONTH = settings.max_advance_amount_per_month
CARD_DISPATCH_CHATS = _normalize_card_dispatch_chats(
    settings.card_dispatch_chats, settings.card_dispatch_chat_id
)
CARD_DISPATCH_CHAT_ID = (
    CARD_DISPATCH_CHATS[0]["chat_id"] if CARD_DISPATCH_CHATS else settings.card_dispatch_chat_id
)
DEFAULT_CARD_DISPATCH_CHAT_KEY = (
    CARD_DISPATCH_CHATS[0]["key"] if CARD_DISPATCH_CHATS else None
)
SECRET_KEY = settings.secret_key


def _load_salon_audio_tokens() -> dict[str, str]:
    """Токены салонных аудио-агентов: { salon_id: token }.

    Секреты, поэтому живут только в боевом config.json, не в Settings и не
    в репозитории. Каждый салонный ПК знает свой токен; сервер сверяет по нему
    входящее соединение агента.
    """
    path = Path("config.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = data.get("salon_audio_tokens") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v}


SALON_AUDIO_TOKENS = _load_salon_audio_tokens()
