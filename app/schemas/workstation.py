"""Схемы управления салонными компьютерами.

Отдельно от MDM телефонов: команды, показатели и экран в панели у них разные,
и сведение в один субсистем-конгломерат дало бы условия «если андроид» в каждой
второй строке. Механику очереди команд повторяем сознательно — она у телефонов
выстрадана (подтверждения, отмена, подметание зависших), и переносим форму, а
не переиспользуем код, чтобы правки для ПК не задевали работающий парк
телефонов.

Про безопасность. На этих машинах касса, Firebird с продажами и Agbis, поэтому
команды «выполнить произвольную строку» здесь нет и не будет. Есть белый список
действий, а имена программ для запуска и перезапуска задаются в config.json
сервера (WORKSTATION_ALLOWED_APPS), а не приходят параметром: так опасная
поверхность лежит в одном видимом месте, а не в теле каждой команды.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Типы команд. Держится в синхроне с device/pc_agent/agent.py.
WorkstationCommandType = Literal[
    "reboot",  # перезагрузить (params: delay_seconds)
    "shutdown",  # выключить (params: delay_seconds)
    "cancel_shutdown",  # отменить отложенную перезагрузку/выключение
    "lock",  # заблокировать экран
    "logoff",  # завершить сеанс пользователя
    "message",  # окно с сообщением на экране (params: text, title)
    "restart_process",  # перезапустить программу из белого списка (params: app)
    "run_app",  # запустить программу из белого списка (params: app)
    "cleanup_temp",  # очистить временные файлы
    "collect_now",  # прислать свежий отчёт немедленно
]

COMMAND_STATUSES = ("pending", "sent", "done", "failed", "canceled")


class DiskInfo(BaseModel):
    """Раздел диска. Место здесь — не косметика: при переполнении встаёт
    Firebird, а вместе с ним продажи салона."""

    mount: str
    total_gb: float
    free_gb: float
    free_percent: float


class WorkstationCommand(BaseModel):
    id: str
    type: WorkstationCommandType
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    status: Literal["pending", "sent", "done", "failed", "canceled"] = "pending"
    result: Optional[str] = None
    acked_at: Optional[str] = None


class WorkstationCommandCreate(BaseModel):
    type: WorkstationCommandType
    params: dict[str, Any] = Field(default_factory=dict)


class WorkstationCommandAck(BaseModel):
    command_id: str
    status: Literal["done", "failed"]
    result: Optional[str] = None


class WorkstationEnrollRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=128)
    agent_version: Optional[str] = None


class WorkstationEnrollResponse(BaseModel):
    workstation_id: str
    token: str


class WorkstationCheckin(BaseModel):
    """Отчёт о состоянии машины.

    Всё, кроме имени, необязательно: сбор любого показателя может не удаться на
    конкретной машине, и это не повод терять остальной отчёт.
    """

    hostname: Optional[str] = None
    os_version: Optional[str] = None
    agent_version: Optional[str] = None
    uptime_seconds: Optional[int] = None
    cpu_percent: Optional[float] = None
    ram_total_mb: Optional[int] = None
    ram_used_percent: Optional[float] = None
    disks: list[DiskInfo] = Field(default_factory=list)
    ip_address: Optional[str] = None
    # Какие из ожидаемых процессов найдены. Ключ — имя процесса, значение —
    # запущен ли. Список ожидаемых задаёт сервер.
    processes: dict[str, bool] = Field(default_factory=dict)
    pending_reboot: Optional[bool] = None
    # Есть ли на машине активный сеанс пользователя. Без него экранные команды
    # (сообщение, блокировка) выполнить некому, и панель должна это показывать
    # заранее, а не отдавать команду в пустоту.
    user_session: Optional[bool] = None
    logged_user: Optional[str] = None
    last_error: Optional[str] = None
    acks: list[WorkstationCommandAck] = Field(default_factory=list)


class WorkstationCheckinResponse(BaseModel):
    interval_seconds: int
    watch_processes: list[str] = Field(default_factory=list)
    # Программы, которые разрешено запускать и перезапускать. Приходят с
    # сервера, чтобы имя программы не было свободным параметром команды.
    allowed_apps: list[str] = Field(default_factory=list)


class WorkstationPollRequest(BaseModel):
    """Длинный опрос: подтверждения едут здесь же.

    Агент исполнил команду и тут же снова встаёт на ожидание, поэтому отдельный
    отчёт был бы вторым запросом на ровном месте.
    """

    acks: list[WorkstationCommandAck] = Field(default_factory=list)


class WorkstationPollResponse(BaseModel):
    commands: list[WorkstationCommand] = Field(default_factory=list)
    hold_seconds: int
    allowed_apps: list[str] = Field(default_factory=list)


class Workstation(BaseModel):
    id: str
    hostname: Optional[str] = None
    name: Optional[str] = None
    salon_id: Optional[str] = None
    os_version: Optional[str] = None
    agent_version: Optional[str] = None
    enrolled_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    uptime_seconds: Optional[int] = None
    cpu_percent: Optional[float] = None
    ram_total_mb: Optional[int] = None
    ram_used_percent: Optional[float] = None
    disks: list[DiskInfo] = Field(default_factory=list)
    ip_address: Optional[str] = None
    processes: dict[str, bool] = Field(default_factory=dict)
    pending_reboot: Optional[bool] = None
    user_session: Optional[bool] = None
    logged_user: Optional[str] = None
    last_error: Optional[str] = None
    commands: list[WorkstationCommand] = Field(default_factory=list)


class WorkstationUpdate(BaseModel):
    """Что оператор правит руками: понятное имя и привязка к салону."""

    name: Optional[str] = None
    salon_id: Optional[str] = None
