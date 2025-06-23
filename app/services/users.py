"""Helpers for accessing employees via the local REST API instead of JSON files."""

from dataclasses import asdict
from typing import Dict, Any

import requests

from ..utils.logger import log
from ..models import User

# Base URL of the FastAPI application running locally
API_URL = "http://localhost:8000/api"


def load_users() -> Dict[str, Any]:
    """Fetch users via the local API."""
    try:
        resp = requests.get(f"{API_URL}/employees/")
        resp.raise_for_status()
        items = resp.json()
        return {str(item.get("id")): item for item in items}
    except Exception as e:
        log(f"❌ Ошибка загрузки сотрудников через API: {e}")
        return {}


def save_users(_users: Dict[str, Any]) -> None:
    """Deprecated helper to keep compatibility."""
    log("⚠️ save_users is deprecated when using the API")


def load_users_dataclass() -> Dict[str, User]:
    """Load users and convert to :class:`User` objects."""
    raw = load_users()
    return {uid: User(**data) for uid, data in raw.items()}


def save_users_dataclass(users: Dict[str, User]) -> None:
    """Deprecated; sends updates via the API instead."""
    for uid, user in users.items():
        update_user(uid, asdict(user))


def add_user(user_id: str, user_data: Dict[str, Any]) -> None:
    payload = {"id": user_id, **user_data}
    try:
        requests.post(f"{API_URL}/employees/", json=payload)
    except Exception as e:
        log(f"❌ Ошибка создания сотрудника через API: {e}")


def update_user(user_id: str, fields: Dict[str, Any]) -> None:
    try:
        requests.put(f"{API_URL}/employees/{user_id}", json=fields)
    except Exception as e:
        log(f"❌ Ошибка обновления сотрудника через API: {e}")


def delete_user(user_id: str) -> None:
    try:
        requests.delete(f"{API_URL}/employees/{user_id}")
    except Exception as e:
        log(f"❌ Ошибка удаления сотрудника через API: {e}")
