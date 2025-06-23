"""Access payout requests via the REST API instead of local JSON files."""

import time
from dataclasses import asdict
from typing import Any, Dict, List

import requests

from ..utils.logger import log
from ..models import PayoutRequest

# Base URL of the local API
API_URL = "http://localhost:8000/api"

# Соответствие статусов на английском и русском языках
STATUS_TRANSLATIONS = {
    "approved": "Одобрено",
    "rejected": "Отклонено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}


def load_advance_requests() -> List[Dict[str, Any]]:
    """Fetch payout requests from the local API."""
    try:
        resp = requests.get(f"{API_URL}/payouts/")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log(f"❌ Ошибка загрузки выплат через API: {e}")
        return []


def save_advance_requests(_requests_list: List[Dict[str, Any]]) -> None:
    """Deprecated helper kept for backward compatibility."""
    log("⚠️ save_advance_requests is deprecated when using the API")


def load_requests_dataclass() -> List[PayoutRequest]:
    """Возвращает список запросов как объекты PayoutRequest."""
    return [PayoutRequest(**d) for d in load_advance_requests()]


def save_requests_dataclass(requests: List[PayoutRequest]) -> None:
    """Сохраняет список объектов PayoutRequest."""
    save_advance_requests([asdict(r) for r in requests])


def log_new_request(
    user_id: Any,
    name: str,
    phone: str,
    bank: str,
    amount: Any,
    payout_method: str,
    payout_type: str | None = None,
) -> None:
    """Send a new payout request to the API."""
    payload = {
        "user_id": str(user_id),
        "name": name,
        "phone": phone,
        "bank": bank,
        "amount": int(amount),
        "method": payout_method,
        "payout_type": payout_type,
    }
    try:
        requests.post(f"{API_URL}/payouts/", json=payload)
        log(f"📝 Новый запрос выплаты: {payload}")
    except Exception as e:
        log(f"❌ Ошибка создания запроса выплаты через API: {e}")


def check_pending_request(user_id: Any) -> bool:
    """Check via API if user has a pending payout request."""
    try:
        resp = requests.get(
            f"{API_URL}/payouts/",
            params={"employee_id": user_id, "status": "В ожидании"},
        )
        resp.raise_for_status()
        return len(resp.json()) > 0
    except Exception as e:
        log(f"❌ Ошибка проверки запроса выплаты через API: {e}")
        return False


def update_request_status(user_id: Any, status: str) -> None:
    """Update the last pending request for a user via the API."""
    try:
        resp = requests.get(
            f"{API_URL}/payouts/",
            params={"employee_id": user_id, "status": "В ожидании"},
        )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            log(
                f"⚠️ [update_request_status] Не найдено активных запросов для user_id {user_id}"
            )
            return
        payout_id = items[0]["id"]
        status_ru = STATUS_TRANSLATIONS.get(status.lower(), status)
        requests.put(
            f"{API_URL}/payouts/{payout_id}",
            json={
                "status": status_ru})
        log(f"✅ Статус запроса для user_id {user_id} обновлён на '{status}'")
    except Exception as e:
        log(f"❌ Ошибка обновления статуса выплаты через API: {e}")


def delete_request(user_id: Any) -> None:
    """Delete all requests for a user via the API."""
    try:
        resp = requests.get(
            f"{API_URL}/payouts/",
            params={"employee_id": user_id},
        )
        resp.raise_for_status()
        ids = [str(item["id"]) for item in resp.json()]
        if ids:
            requests.delete(
                f"{API_URL}/payouts/", params={"ids": ",".join(ids)}
            )
            log(f"✅ Запросы пользователя {user_id} удалены")
    except Exception as e:
        log(f"❌ Ошибка удаления запросов через API: {e}")


def edit_request(user_id: Any, updates: Dict[str, Any]) -> None:
    """Edit the first request of a user via the API."""
    try:
        resp = requests.get(
            f"{API_URL}/payouts/", params={"employee_id": user_id}
        )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            return
        payout_id = items[0]["id"]
        requests.put(f"{API_URL}/payouts/{payout_id}", json=updates)
        log(f"✅ Запрос пользователя {user_id} обновлён: {updates}")
    except Exception as e:
        log(f"❌ Ошибка редактирования запроса через API: {e}")


def delete_request_by_index(index: str) -> None:
    """Delete a request by its id via the API."""
    try:
        requests.delete(f"{API_URL}/payouts/{index}")
        log(f"✅ Запрос №{index} удалён")
    except Exception as e:
        log(f"❌ Ошибка удаления запроса через API: {e}")


def edit_request_by_index(index: str, updates: Dict[str, Any]) -> None:
    """Edit a request by id via the API."""
    try:
        requests.put(f"{API_URL}/payouts/{index}", json=updates)
        log(f"✅ Запрос №{index} обновлён: {updates}")
    except Exception as e:
        log(f"❌ Ошибка обновления запроса через API: {e}")
