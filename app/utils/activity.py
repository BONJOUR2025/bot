"""Журнал активности в человеческом виде: «открыл «Выплаты»», «скан: выход,
заказ 12345 — записан в Агбис», а не «GET /api/masters/me/earnings -> 200».

Раньше middleware писал в logs/users/ каждый HTTP-запрос как есть. Одно
открытие страницы — десяток строк (auth/me, справочники, миниатюры), плюс
пинги телефонов салонов и фоновые опросы: десятки тысяч строк, в которых
действие человека не найти.

Теперь в журнал попадает три вида записей:
- «открыл <страница>» — по заголовку X-Page, который фронтенд шлёт с каждым
  запросом (admin_frontend/src/api.js). По адресам API страницу не понять:
  открывая «Выплаты», панель попутно грузит сотрудников, справочники и т.д.
  Повторное открытие той же страницы раньше чем через OPEN_DEDUP_S не пишется;
- описание действия от самого обработчика — ``note("…")``: с номером заказа,
  именем мастера, итогом. Самое ценное, пишется всегда;
- прочие изменения (POST/PUT/PATCH/DELETE) — разделом и адресом, чтобы ни
  одно изменение данных не пропало из журнала.
Чтение (GET) само по себе не пишется. Служебные адреса — тоже (NOISE_PREFIXES).
"""
from __future__ import annotations

import re
import threading
import time
from contextvars import ContextVar

# Держатель заметок текущего запроса. Middleware кладёт сюда новый список
# до вызова обработчика; обработчик (в том числе синхронный, в пуле потоков —
# контекст копируется, но список тот же объект) дописывает в него.
_notes: ContextVar[list | None] = ContextVar("activity_notes", default=None)


def start_request() -> list:
    holder: list[str] = []
    _notes.set(holder)
    return holder


def note(text: str) -> None:
    """Описать действие текущего запроса для журнала активности."""
    holder = _notes.get()
    if holder is not None and text:
        holder.append(text)


# ── служебные адреса: не пишем даже изменения ──────────────────────────
NOISE_PREFIXES = (
    "/api/auth/me", "/api/auth/login", "/api/auth/logout", "/api/mdm/device", "/api/mdm/agent",
    "/api/mdm/enrollment", "/api/mdm/provisioning", "/api/visitor-events", "/api/hh/webhook",
    "/api/avito/webhook", "/api/push", "/api/master-app/info", "/api/salon-app",
    "/api/telegram/webhook", "/api/system/process-status", "/api/system/fdb-cache",
    "/api/recruitment/notifications", "/api/masters/me/telegram", "/api/masters/me/scan/mode",
    "/session/",
)
# Расчёты, которые страницы делают POST-ом, хотя ничего не меняют.
READ_ONLY_POSTS = (
    "/api/manager-salary/calc", "/api/courier-salary/calc", "/api/masters/me/scan/preview",
    "/api/workshop/scan/preview", "/api/lasts/match", "/api/scanner/", "/api/help/ask",
    "/api/recruitment/ai-check",
)

# ── страницы: путь во фронтенде → как называется ───────────────────────
# Более длинные пути раньше: совпадение по префиксу.
PAGES: tuple[tuple[str, str], ...] = (
    # кабинет сотрудника / приложение мастера
    ("/employee/earnings", "«Заработок» (кабинет мастера)"),
    ("/employee/wip", "«В работе» (кабинет мастера)"),
    ("/employee/scan", "«Скан» (кабинет мастера)"),
    ("/employee/kpi", "«Мой KPI» (кабинет менеджера)"),
    ("/employee/workshop", "«Цех» (кабинет старшего мастера)"),
    ("/employee/assets", "«Имущество» (кабинет)"),
    ("/employee/salary", "«Зарплата» (кабинет)"),
    ("/employee/payouts", "«Авансы» (кабинет)"),
    ("/employee/schedule", "«График» (кабинет)"),
    ("/employee/profile", "«Профиль» (кабинет)"),
    ("/employee/history", "«История» (кабинет)"),
    ("/employee/leave-requests", "«Заявки на отгул» (кабинет)"),
    ("/employee/feedback", "«Обратная связь» (кабинет)"),
    ("/employee", "главную (кабинет)"),
    # админка
    ("/admin/employees/", "карточку сотрудника"),
    ("/admin/employees", "«Сотрудники»"),
    ("/admin/recruitment", "«Подбор персонала»"),
    ("/admin/archive", "«Архив сотрудников»"),
    ("/admin/birthdays", "«Дни рождения»"),
    ("/admin/assets", "«Имущество»"),
    ("/admin/schedule", "«Расписание»"),
    ("/admin/vacations", "«Отпуска»"),
    ("/admin/leave-requests", "«Заявки на отгул»"),
    ("/admin/shift-checkins", "«Рабочее время»"),
    ("/admin/workshop", "«Цех»"),
    ("/admin/tag-scanner", "«Сканер бирок»"),
    ("/admin/salons", "«Салоны»"),
    ("/admin/visitor-counters", "«Счётчик посетителей»"),
    ("/admin/mdm-devices", "«Телефоны салонов»"),
    ("/admin/workstations", "«Компьютеры салонов»"),
    ("/admin/sales", "«Продажи»"),
    ("/admin/clients", "«Клиенты»"),
    ("/admin/location-plans", "«Планы продаж»"),
    ("/admin/sale-transfers", "«Перемещение продажи»"),
    ("/admin/scanner-3d", "«3D сканер»"),
    ("/admin/salon-audio", "«Прослушивание»"),
    ("/admin/payroll-summary", "«Сводный отчёт» (зарплата)"),
    ("/admin/payroll-by-salon", "«ФОТ по салонам»"),
    ("/admin/payroll", "«Зарплата → Администраторы»"),
    ("/admin/masters", "«Зарплата → Мастера»"),
    ("/admin/manager-salary", "«Зарплата → Менеджеры»"),
    ("/admin/courier-salary", "«Зарплата → Курьер»"),
    ("/admin/payouts-control", "«Контроль выплат»"),
    ("/admin/payouts", "«Выплаты»"),
    ("/admin/incentives", "«Штрафы и премии»"),
    ("/admin/cash-moves", "«Кассовые перемещения»"),
    ("/admin/cash-summary", "«Сводный отчёт (касса)»"),
    ("/admin/payments", "«Оплаты»"),
    ("/admin/receivables", "«Дебиторка»"),
    ("/admin/payment-calendar", "«Платежный календарь»"),
    ("/admin/tasks", "«Задачи»"),
    ("/admin/broadcast", "«Рассылка»"),
    ("/admin/messages", "«История сообщений»"),
    ("/admin/employee-messages", "«Сообщения от сотрудников»"),
    ("/admin/smses", "«СМС Агбис»"),
    ("/admin/knowledge-base", "«База знаний»"),
    ("/admin/agbis-users", "«Пользователи АГБИС»"),
    ("/admin/agbis-settings", "«Настройки АГБИС»"),
    ("/admin/passwords", "«Пароли»"),
    ("/admin/client-lk-password", "«Пароль клиента (ЛК)»"),
    ("/admin/settings/general", "«Настройки → Общие»"),
    ("/admin/settings/telegram", "«Настройки → Telegram»"),
    ("/admin/settings/notifications", "«Настройки → Уведомления»"),
    ("/admin/settings/automation", "«Настройки → Автоматизация»"),
    ("/admin/settings/ai-usage", "«Настройки → Расход AI»"),
    ("/admin/settings/integrations", "«Настройки → Интеграции»"),
    ("/admin/settings/vpn", "«Настройки → VPN»"),
    ("/admin/settings/poshiv-bot", "«Настройки → Бот пошива»"),
    ("/admin/settings/templates", "«Настройки → Шаблоны»"),
    ("/admin/settings/dictionary", "«Настройки → Словарь»"),
    ("/admin/settings/access", "«Настройки → Доступ»"),
    ("/admin/settings/diagnostics", "«Настройки → Диагностика»"),
    ("/admin/settings", "«Настройки»"),
    ("/admin/help", "«Помощь»"),
    ("/admin", "«Дашборд»"),
)

# ── разделы API: для подписи изменений, у которых нет note() ───────────
SECTIONS: tuple[tuple[str, str], ...] = (
    ("/api/masters/me", "приложение мастера"),
    ("/api/managers/me", "кабинет менеджера"),
    ("/api/salon/me", "кабинет"),
    ("/api/workshop", "«Цех»"),
    ("/api/payroll/sale-transfers", "«Перемещение продажи»"),
    ("/api/payroll", "«Зарплата → Администраторы»"),
    ("/api/manager-salary", "«Зарплата → Менеджеры»"),
    ("/api/courier-salary", "«Зарплата → Курьер»"),
    ("/api/masters", "«Зарплата → Мастера»"),
    ("/api/payouts", "«Выплаты»"),
    ("/api/incentives", "«Штрафы и премии»"),
    ("/api/cash-moves", "«Кассовые перемещения»"),
    ("/api/payment-calendar", "«Платежный календарь»"),
    ("/api/sales", "«Продажи»"),
    ("/api/location-plans", "«Планы продаж»"),
    ("/api/employees", "«Сотрудники»"),
    ("/api/recruitment", "«Подбор персонала»"),
    ("/api/assets", "«Имущество»"),
    ("/api/schedule", "«Расписание»"),
    ("/api/vacations", "«Отпуска»"),
    ("/api/leave-requests", "«Заявки на отгул»"),
    ("/api/shift-checkins", "«Рабочее время»"),
    ("/api/salons", "«Салоны»"),
    ("/api/visitor-counters", "«Счётчик посетителей»"),
    ("/api/mdm", "«Телефоны салонов»"),
    ("/api/workstations", "«Компьютеры салонов»"),
    ("/api/lasts", "«3D сканер»"),
    ("/api/tasks", "«Задачи»"),
    ("/api/telegram", "«Рассылка»"),
    ("/api/messages", "«История сообщений»"),
    ("/api/employee-messages", "«Сообщения от сотрудников»"),
    ("/api/knowledge", "«База знаний»"),
    ("/api/passwords", "«Пароли»"),
    ("/api/auth", "«Настройки → Доступ»"),
    ("/api/bot-users", "«Настройки → Доступ»"),
    ("/api/vk-bot-users", "«Настройки → Доступ»"),
    ("/api/config", "«Настройки»"),
    ("/api/dictionary", "«Настройки → Словарь»"),
    ("/api/system", "«Настройки → Диагностика»"),
    ("/api/vpn", "«Настройки → VPN»"),
    ("/api/poshiv-bot", "«Настройки → Бот пошива»"),
    ("/api/notification-routing", "«Настройки → Уведомления»"),
    ("/api/point", "кабинет точки"),
)

VERBS = {"POST": "действие", "PUT": "изменение", "PATCH": "изменение", "DELETE": "удаление"}
OPEN_DEDUP_S = 600
# Первый запрос после такой паузы — новый заход в панель. Пишется всегда,
# даже без X-Page: иначе человек, который только смотрел страницы во
# вкладке со старой версией панели (без заголовка), выглядел бы так, будто
# не заходил вовсе.
SESSION_GAP_S = 1800

_last_seen: dict[str, float] = {}

_dedup_lock = threading.Lock()
_last_open: dict[str, tuple[str, float]] = {}


def _match(table, path: str) -> str | None:
    for prefix, name in table:
        if path == prefix or path.startswith(prefix if prefix.endswith("/") else prefix + "/"):
            return name
    return None


def page_name(page: str | None) -> str | None:
    if not page:
        return None
    return _match(PAGES, page.rstrip("/") or "/")


def page_open(user_key: str, page: str | None, *, now: float | None = None) -> str | None:
    """«открыл …», если человек перешёл на другую страницу (или вернулся на
    ту же спустя OPEN_DEDUP_S). Иначе None."""
    name = page_name(page)
    if name is None:
        return None
    now = time.time() if now is None else now
    with _dedup_lock:
        last = _last_open.get(user_key)
        if last and last[0] == name and now - last[1] < OPEN_DEDUP_S:
            _last_open[user_key] = (name, now)
            return None
        _last_open[user_key] = (name, now)
    return f"открыл {name}"


def is_noise(path: str) -> bool:
    return path.startswith(NOISE_PREFIXES)


def describe_change(method: str, path: str, status: int) -> str | None:
    """Подпись изменения без note(): раздел + адрес. GET и служебное — None."""
    if method in ("GET", "OPTIONS", "HEAD") or status == 401 or is_noise(path):
        return None
    if method == "POST" and path.startswith(READ_ONLY_POSTS):
        return None
    where = _match(SECTIONS, path) or "панель"
    failed = f" — ошибка {status}" if status >= 400 else ""
    return f"{where}: {VERBS.get(method, method)} ({method} {path}){failed}"


def entries(user_key: str, method: str, path: str, status: int, page: str | None,
            notes: list[str] | None, *, now: float | None = None) -> list[str]:
    """Все строки журнала, которые даёт один запрос, по порядку."""
    out: list[str] = []
    now = time.time() if now is None else now
    with _dedup_lock:
        prev = _last_seen.get(user_key)
        _last_seen[user_key] = now
    if prev is None or now - prev > SESSION_GAP_S:
        if page and page.startswith("/employee"):
            out.append("зашёл в личный кабинет")
        elif page:
            out.append("зашёл в панель")
        else:
            out.append("зашёл в панель (какие разделы открывал — не видно: устаревшая вкладка, нужно обновить страницу)")
    opened = page_open(user_key, page, now=now)
    if opened:
        out.append(opened)
    if notes:
        failed = f" — ошибка {status}" if status >= 400 else ""
        out.extend(n + failed for n in notes)
    else:
        change = describe_change(method, path, status)
        if change:
            out.append(change)
    return out
