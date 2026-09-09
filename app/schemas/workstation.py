"""Схемы наблюдения за салонными компьютерами.

Отдельно от MDM телефонов и намеренно проще. Телефону нужна очередь команд с
подтверждениями и длинный опрос — здесь этого нет вовсе: агент на ПК только
рассказывает о себе и ничего не умеет делать. Read-only не как «первый этап,
потом добавим», а как свойство: в агенте нет кода, исполняющего команды, и
скомпрометированный сервер не сможет ничего запустить на кассовом компьютере.

Цена такого решения — обновлять агент придётся через тот же удалённый доступ,
которым его ставили. На парке в несколько машин это дешевле, чем держать на
кассе исполнителя произвольных команд.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DiskInfo(BaseModel):
    """Раздел диска. Место здесь — не косметика: при переполнении встаёт
    Firebird, а вместе с ним продажи салона."""

    mount: str
    total_gb: float
    free_gb: float
    free_percent: float


class WorkstationEnrollRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=128)
    agent_version: Optional[str] = None


class WorkstationEnrollResponse(BaseModel):
    workstation_id: str
    token: str


class WorkstationCheckin(BaseModel):
    """Регулярный отчёт агента. Всё, кроме имени, необязательно: сбор любого
    показателя может не удаться на конкретной машине, и это не повод терять
    остальной отчёт."""

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
    # запущен ли. Список ожидаемых задаёт сервер, см. WorkstationCheckinResponse.
    processes: dict[str, bool] = Field(default_factory=dict)
    pending_reboot: Optional[bool] = None
    last_error: Optional[str] = None


class WorkstationCheckinResponse(BaseModel):
    interval_seconds: int
    # Процессы, о которых агент должен доложить. Приходят с сервера, чтобы
    # добавить наблюдение за новой программой можно было без обхода машин.
    watch_processes: list[str] = Field(default_factory=list)


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
    last_error: Optional[str] = None


class WorkstationUpdate(BaseModel):
    """Что оператор может поправить руками: понятное имя и привязка к салону."""

    name: Optional[str] = None
    salon_id: Optional[str] = None
