import json
import os
import time
from dataclasses import asdict
from typing import List, Dict, Any
from ..utils.logger import log
from ..config import ADVANCE_REQUESTS_FILE
from ..models import PayoutRequest

# Соответствие статусов на английском и русском языках
STATUS_TRANSLATIONS = {
    "approved": "Одобрено",
    "rejected": "Отклонено",
    "pending": "Ожидает",
    "cancelled": "Отменено",
}


def load_advance_requests() -> List[Dict[str, Any]]:
    """
    Загружает список запросов выплат из JSON-файла.
    Если файл не найден или произошла ошибка, возвращается пустой список.
    """
    if not os.path.exists(ADVANCE_REQUESTS_FILE):
        log(f"⚠️ Файл {ADVANCE_REQUESTS_FILE} не найден. Создаём новый.")
        return []
    try:
        with open(ADVANCE_REQUESTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for req in data:
                status = req.get("status")
                if isinstance(status, str):
                    lower_status = status.lower()
                    if lower_status in STATUS_TRANSLATIONS:
                        req["status"] = STATUS_TRANSLATIONS[lower_status]
            return data
    except Exception as e:
        log(f"❌ Ошибка загрузки {ADVANCE_REQUESTS_FILE}: {e}")
        return []


def save_advance_requests(requests_list: List[Dict[str, Any]]) -> None:
    """
    Сохраняет список запросов выплат в JSON-файл.
    """
    try:
        with open(ADVANCE_REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(requests_list, f, ensure_ascii=False, indent=4)
        log(f"DEBUG [save_advance_requests] Сохранено: {requests_list}")
    except Exception as e:
        log(f"❌ Ошибка сохранения в {ADVANCE_REQUESTS_FILE}: {e}")


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
    payout_type: str = None,
) -> None:
    """
    Логирует новый запрос на выплату и сохраняет его в файл.
    """
    requests_list = load_advance_requests()
    new_request = {
        "user_id": str(user_id),
        "name": name,
        "phone": phone,
        "bank": bank,
        "amount": int(amount),  # Приводим к int
        "method": payout_method,
        "payout_type": payout_type,
        "status": "Ожидает",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    requests_list.append(new_request)
    save_advance_requests(requests_list)
    log(f"📝 Новый запрос выплаты: {new_request}")


def check_pending_request(user_id: Any) -> bool:
    """Проверяет, есть ли у пользователя активный запрос выплаты."""
    requests_list = load_advance_requests()
    for req in requests_list:
        if (
            str(req.get("user_id")) == str(user_id)
            and req.get("status") == "Ожидает"
        ):
            return True
    return False


def update_request_status(user_id: Any, status: str) -> None:
    """
    Обновляет статус запроса для пользователя.
    """
    requests_list = load_advance_requests()
    # Поддерживаем английские статусы для обратной совместимости
    status_ru = STATUS_TRANSLATIONS.get(status.lower(), status)
    updated = False
    for request in requests_list:
        if (
            str(request.get("user_id")) == str(user_id)
            and request.get("status") == "Ожидает"
        ):
            request["status"] = status_ru
            updated = True
    if updated:
        save_advance_requests(requests_list)
        log(f"✅ Статус запроса для user_id {user_id} обновлён на '{status}'")
    else:
        log(
            f"⚠️ [update_request_status] Не найдено активных запросов для user_id {user_id}"
        )


def delete_request(user_id: Any) -> None:
    """Удаляет все запросы пользователя."""
    requests_list = load_advance_requests()
    new_list = [r for r in requests_list if str(r.get("user_id")) != str(user_id)]
    if len(new_list) != len(requests_list):
        save_advance_requests(new_list)
        log(f"✅ Запросы пользователя {user_id} удалены")


def edit_request(user_id: Any, updates: Dict[str, Any]) -> None:
    """Обновляет поля запроса пользователя (первого найденного)."""
    requests_list = load_advance_requests()
    for req in requests_list:
        if str(req.get("user_id")) == str(user_id):
            req.update(updates)
            save_advance_requests(requests_list)
            log(f"✅ Запрос пользователя {user_id} обновлён: {updates}")
            break

def delete_request_by_index(index: int) -> None:
    """Удаляет запрос по его индексу."""
    requests_list = load_advance_requests()
    if 0 <= index < len(requests_list):
        requests_list.pop(index)
        save_advance_requests(requests_list)
        log(f"✅ Запрос №{index} удалён")


def edit_request_by_index(index: int, updates: Dict[str, Any]) -> None:
    """Редактирует запрос по индексу."""
    requests_list = load_advance_requests()
    if 0 <= index < len(requests_list):
        requests_list[index].update(updates)
        save_advance_requests(requests_list)
        log(f"✅ Запрос №{index} обновлён: {updates}")
