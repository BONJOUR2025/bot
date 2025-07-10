"""Payout request helpers using the local repository."""

from typing import Any, Dict, List
from datetime import datetime
import logging

from app.data.payout_repository import (
    PayoutRepository,
    load_advance_requests as repo_load_advance_requests,
)
from app.schemas.payout import Payout
from ..utils.logger import log
from ..core.enums import PAYOUT_STATUSES

logger = logging.getLogger(__name__)

_repo = PayoutRepository()

# statuses considered pending (awaiting admin decision)
PENDING_STATUSES = {PAYOUT_STATUSES[0]}

STATUS_TRANSLATIONS = {
    "approved": "Одобрено",
    "rejected": "Отклонено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}


def load_advance_requests() -> List[Dict[str, Any]]:
    path = _repo._file
    log(f"📂 Загрузка заявок из: {path}")
    data = repo_load_advance_requests(path)
    log(f"✅ Загружено заявок: {len(data)}")
    return data


def save_advance_requests(_requests_list: List[Dict[str, Any]]) -> None:
    log("⚠️ save_advance_requests is deprecated when using repository")


def load_requests_dataclass() -> List[Payout]:
    return [Payout(**r) for r in _repo.load_all()]


def save_requests_dataclass(requests: List[Payout]) -> None:
    for r in requests:
        _repo.update(r.id, r.model_dump(exclude_none=True))


def log_new_request(
    user_id: Any,
    name: str,
    phone: str,
    bank: str,
    amount: Any,
    payout_method: str,
    payout_type: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "user_id": str(user_id),
        "name": name,
        "phone": phone,
        "bank": bank,
        "amount": int(amount),
        "method": payout_method,
        "payout_type": payout_type,
        "status": "Ожидает",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    record = _repo.create(payload)
    log(f"📝 Новый запрос выплаты: {record}")
    return record


def check_pending_request(user_id: Any) -> bool:
    requests = _repo.list(employee_id=user_id)
    return any(r.get("status") in PENDING_STATUSES for r in requests)


def update_request_status(payout_id: Any, status: str) -> bool:
    record = next(
        (r for r in _repo.load_all() if str(r.get("id")) == str(payout_id)),
        None,
    )
    if not record:
        log(f"⚠️ [update_request_status] Запрос {payout_id} не найден")
        return False
    if record.get("status") not in PENDING_STATUSES:
        log(f"⚠️ [update_request_status] Запрос {payout_id} не в ожидающем статусе")
        return False
    status_ru = STATUS_TRANSLATIONS.get(status.lower(), status)
    updates = {"status": status_ru}
    if not record.get("timestamp"):
        updates["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = _repo.update(str(payout_id), updates)
    if updated:
        log(f"✅ Статус запроса {payout_id} обновлён на '{status_ru}'")
        return True
    log(f"⚠️ [update_request_status] Не удалось обновить запрос {payout_id}")
    return False


def delete_request(user_id: Any) -> None:
    items = _repo.list(employee_id=user_id)
    ids = [str(i["id"]) for i in items]
    if ids:
        _repo.delete_many(ids)
        log(f"✅ Запросы пользователя {user_id} удалены")


def edit_request(user_id: Any, updates: Dict[str, Any]) -> None:
    items = _repo.list(employee_id=user_id)
    if not items:
        return
    payout_id = items[0]["id"]
    _repo.update(payout_id, updates)
    log(f"✅ Запрос пользователя {user_id} обновлён: {updates}")


def delete_request_by_index(index: str) -> None:
    _repo.delete(index)
    log(f"✅ Запрос №{index} удалён")


def edit_request_by_index(index: str, updates: Dict[str, Any]) -> None:
    _repo.update(index, updates)
    log(f"✅ Запрос №{index} обновлён: {updates}")
