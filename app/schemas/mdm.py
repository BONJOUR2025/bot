"""Схемы MDM: управление корпоративными Android-телефонами салонов.

Телефон несёт агента (`device/mdm_agent`), который встаёт владельцем устройства
(Device Owner) и раз в несколько минут ходит сюда за политикой и командами.
Политика применяется на самом телефоне и продолжает действовать, когда сервер
недоступен, — связь нужна только чтобы политику поменять или отдать команду.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Типы команд, которые понимает агент. Держится в синхроне с
# device/mdm_agent/.../CommandRunner.kt — добавляя команду сюда, добавь и там.
CommandType = Literal[
    "apply_policy",  # перечитать политику (обычно не нужно: агент и так её тянет)
    "lock",  # немедленно заблокировать экран
    "reboot",  # перезагрузить телефон
    "locate",  # прислать координаты в ближайшем чек-ине
    "install_apk",  # тихо поставить APK по ссылке
    "uninstall",  # удалить приложение по имени пакета
    "wipe",  # полный сброс до заводских настроек
    "release_owner",  # аварийный люк: агент перестаёт быть владельцем устройства
]


class MdmRestrictions(BaseModel):
    """Запреты Android. Имена соответствуют константам UserManager.DISALLOW_*.

    Всё по умолчанию выключено сознательно: телефон, только что вставший под
    управление, ведёт себя ровно как обычный, и запреты включаются по одному,
    когда оператор в них уверен. Особенно это касается no_factory_reset —
    ошибка в политике при включённом запрете сброса превращает телефон в кирпич,
    который уже не сбросить руками.
    """

    no_factory_reset: bool = False
    no_install_apps: bool = False
    no_uninstall_apps: bool = False
    no_install_unknown_sources: bool = False
    no_safe_boot: bool = False
    no_add_user: bool = False
    no_modify_accounts: bool = False
    no_config_mobile_networks: bool = False
    no_config_tethering: bool = False
    no_debugging_features: bool = False
    no_outgoing_calls: bool = False
    no_sms: bool = False
    camera_disabled: bool = False


class MdmKiosk(BaseModel):
    """Киоск: телефон залипает в перечисленных приложениях (lock task mode).

    Пустой список пакетов при enabled=True — бессмысленная и опасная политика
    (телефон залипнет в никуда), поэтому сервис такое не принимает.
    """

    enabled: bool = False
    packages: list[str] = Field(default_factory=list)


class MdmPolicy(BaseModel):
    restrictions: MdmRestrictions = Field(default_factory=MdmRestrictions)
    kiosk: MdmKiosk = Field(default_factory=MdmKiosk)


# --- Устройство -> сервер -------------------------------------------------


class MdmEnrollRequest(BaseModel):
    """Первый запрос агента. Авторизуется общим ключом MDM_ENROLL_KEY."""

    device_id: str = Field(min_length=4, max_length=128)
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    android_version: Optional[str] = None
    agent_version: Optional[str] = None
    device_owner: bool = False


class MdmEnrollResponse(BaseModel):
    device_id: str
    token: str
    policy_version: int
    policy: MdmPolicy


class MdmCommandAck(BaseModel):
    command_id: str
    status: Literal["done", "failed"]
    result: Optional[str] = None


class MdmCheckinRequest(BaseModel):
    """Регулярный чек-ин: агент отчитывается о состоянии и забирает команды."""

    model: Optional[str] = None
    manufacturer: Optional[str] = None
    android_version: Optional[str] = None
    agent_version: Optional[str] = None
    device_owner: bool = False
    battery: Optional[int] = Field(default=None, ge=0, le=100)
    applied_policy_version: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_at: Optional[str] = None
    last_error: Optional[str] = None
    acks: list[MdmCommandAck] = Field(default_factory=list)


class MdmCommand(BaseModel):
    id: str
    type: CommandType
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    status: Literal["pending", "sent", "done", "failed"] = "pending"
    result: Optional[str] = None
    acked_at: Optional[str] = None


class MdmAckRequest(BaseModel):
    """Результаты команд, доставляемые отдельно от чек-ина.

    Отдельная ручка нужна, чтобы агент мог отчитаться сразу после выполнения:
    повторный чек-ин заодно забрал бы новые команды и пометил их отправленными,
    а исполнить их тот проход уже не успевает.
    """

    acks: list[MdmCommandAck] = Field(default_factory=list)
    # Версия политики, применённая уже ПОСЛЕ отправки чек-ина: в самом
    # чек-ине агент может сообщить только предыдущую — политику он получает
    # тем же ответом и применяет, когда запрос уже ушёл.
    applied_policy_version: Optional[int] = None


class MdmCheckinResponse(BaseModel):
    policy_version: int
    policy: MdmPolicy
    commands: list[MdmCommand] = Field(default_factory=list)
    checkin_interval_minutes: int = 15


# --- Админка -> сервер ----------------------------------------------------


class MdmDevice(BaseModel):
    id: str
    name: Optional[str] = None
    salon_id: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    android_version: Optional[str] = None
    agent_version: Optional[str] = None
    device_owner: bool = False
    battery: Optional[int] = None
    enrolled_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    policy_version: int = 1
    applied_policy_version: Optional[int] = None
    policy: MdmPolicy = Field(default_factory=MdmPolicy)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_at: Optional[str] = None
    last_error: Optional[str] = None
    commands: list[MdmCommand] = Field(default_factory=list)


class MdmDeviceUpdate(BaseModel):
    name: Optional[str] = None
    salon_id: Optional[str] = None


class MdmCommandCreate(BaseModel):
    type: CommandType
    params: dict[str, Any] = Field(default_factory=dict)


class MdmEnrollmentInfo(BaseModel):
    """Что нужно вбить в агента при первой установке."""

    server_url: str
    enroll_key: str
    configured: bool
