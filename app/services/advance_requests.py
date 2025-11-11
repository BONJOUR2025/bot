"""Payout request helpers using the local repository."""

from typing import Any, Dict, List
from datetime import datetime
import logging

from app.data.payout_repository import PayoutRepository
from ..utils.logger import log
from ..core.enums import PAYOUT_STATUSES

logger = logging.getLogger(__name__)

_repo = PayoutRepository()


def _sync_repo() -> PayoutRepository:
    """Reload repository from disk when possible and return repository instance."""
    repo = _repo
    reload_method = getattr(repo, "reload", None)
    if callable(reload_method):
        reload_method()
    return repo

# statuses considered pending (awaiting admin decision)
PENDING_STATUSES = {PAYOUT_STATUSES[0]}

STATUS_TRANSLATIONS = {
    "approved": "Одобрено",
    "rejected": "Отклонено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}


def load_advance_requests() -> List[Dict[str, Any]]:
    repo = _sync_repo()
    path = getattr(repo, "_file", "advance_requests.json")
    log(f"📂 Загрузка заявок из: {path}")
    data = repo.load_all()
    log(f"✅ Загружено заявок: {len(data)}")
    return data


def save_advance_requests(_requests_list: List[Dict[str, Any]]) -> None:
    log("⚠️ save_advance_requests is deprecated when using repository")


def log_new_request(
    user_id: Any,
    name: str,
    phone: str,
    card_number: str,
    bank: str,
    amount: Any,
    payout_method: str,
    payout_type: str | None = None,
) -> Dict[str, Any]:
    payload = {
        "user_id": str(user_id),
        "name": name,
        "phone": phone,
        "card_number": card_number,
        "bank": bank,
        "amount": int(amount),
        "method": payout_method,
        "payout_type": payout_type,
        "status": "Ожидает",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    repo = _sync_repo()
    record = repo.create(payload)
    log(f"📝 Новый запрос выплаты: {record}")
    return record


def check_pending_request(user_id: Any) -> bool:
    repo = _sync_repo()
    requests = repo.list(employee_id=user_id)
    return any(r.get("status") in PENDING_STATUSES for r in requests)


def update_request_status(payout_id: Any, status: str) -> bool:
    repo = _sync_repo()
    record = next(
        (r for r in repo.load_all() if str(r.get("id")) == str(payout_id)),
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
    updated = repo.update(str(payout_id), updates)
    if updated:
        log(f"✅ Статус запроса {payout_id} обновлён на '{status_ru}'")
        return True
    log(f"⚠️ [update_request_status] Не удалось обновить запрос {payout_id}")
    return False
