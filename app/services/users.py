import json
import os
from dataclasses import asdict
from typing import Dict, Any

from ..config import USERS_FILE
from ..utils.logger import log
from ..models import User


def load_users() -> Dict[str, Any]:
    """Загружает пользователей из JSON-файла."""
    if not USERS_FILE or not os.path.exists(USERS_FILE):
        log(f"⚠️ Файл {USERS_FILE} не найден!")
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        log(f"❌ Ошибка чтения {USERS_FILE}: {e}")
        return {}


def save_users(users: Dict[str, Any]) -> None:
    """Сохраняет словарь users в JSON-файл."""
    directory = os.path.dirname(USERS_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=4)
    except Exception as e:
        log(f"❌ Ошибка сохранения {USERS_FILE}: {e}")


def load_users_dataclass() -> Dict[str, User]:
    """Загружает пользователей как объекты User."""
    raw = load_users()
    return {uid: User(**data) for uid, data in raw.items()}


def save_users_dataclass(users: Dict[str, User]) -> None:
    """Сохраняет словарь объектов User."""
    save_users({uid: asdict(user) for uid, user in users.items()})


def add_user(user_id: str, user_data: Dict[str, Any]) -> None:
    users = load_users()
    users[user_id] = user_data
    save_users(users)


def update_user(user_id: str, fields: Dict[str, Any]) -> None:
    users = load_users()
    if user_id in users:
        users[user_id].update(fields)
        save_users(users)


def delete_user(user_id: str) -> None:
    users = load_users()
    if user_id in users:
        users.pop(user_id)
        save_users(users)
