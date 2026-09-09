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
    "refresh_apps",  # прислать список установленных приложений заново
    "camera",  # снимок с камеры (для потерянного/украденного телефона)
    "ring",  # громкий сигнал + вибрация, чтобы найти телефон
    "stop_ring",  # выключить сигнал
    "message",  # стойкое сообщение на экране блокировки (потерянный телефон)
    "clear_app_data",  # очистить данные приложения (params: package)
    "set_app_enabled",  # скрыть/показать приложение (params: package, enabled)
    "set_volume",  # выставить громкость 0..100 (params: percent)
    "launch_app",  # открыть приложение (params: package)
    "grant_permission",  # выдать/отозвать разрешение (params: package, permission, grant)
    "set_time_zone",  # часовой пояс (params: zone, напр. Europe/Moscow)
    "set_auto_time",  # автосинхронизация времени вкл/выкл (params: enabled)
    "kiosk_exit",  # аварийно выйти из киоска (снять залипание)
    "add_wifi",  # добавить сеть Wi-Fi (params: ssid, password, hidden)
    "set_stay_awake",  # не гасить экран при зарядке (params: enabled)
    "set_status_bar",  # скрыть/показать строку состояния (params: disabled)
    "set_time",  # выставить точное время (params: epoch_ms)
]


class MdmApp(BaseModel):
    """Приложение, установленное на телефоне."""

    package: str
    label: Optional[str] = None
    version_name: Optional[str] = None
    version_code: Optional[int] = None
    system: bool = False
    enabled: bool = True


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
    no_screen_capture: bool = False  # запретить скриншоты и запись экрана
    no_bluetooth: bool = False
    no_usb_file_transfer: bool = False
    no_config_wifi: bool = False  # запретить менять настройки Wi-Fi


class MdmKiosk(BaseModel):
    """Киоск: телефон работает как терминал одного приложения.

    `home` — приложение, в которое телефон залипает: оно становится домашним
    экраном и запускается в режиме закрепления (lock task). `packages` —
    дополнительные приложения, которым тоже разрешено работать в киоске
    (например, касса рядом с основным). Пустой список пакетов при enabled=True
    без `home` — бессмысленная политика, сервис такое не принимает.

    Флаги системных элементов: что оставить доступным в киоске.
    """

    enabled: bool = False
    home: Optional[str] = None
    packages: list[str] = Field(default_factory=list)
    allow_home_button: bool = False
    allow_recents: bool = False
    allow_notifications: bool = True
    allow_system_info: bool = True


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
    # Отпечаток состава приложений приходит всегда, сам список — только
    # когда изменился: полный список это килобайты, а чек-ины идут раз в
    # две минуты.
    apps_hash: Optional[str] = None
    apps: Optional[list[MdmApp]] = None
    # Play Защита отклоняет тихую установку наших APK, а выключить её
    # программно нельзя — только руками на телефоне. Поэтому агент хотя бы
    # сообщает её состояние, чтобы отказ установки не выглядел загадкой.
    play_protect: Optional[bool] = None
    # Телеметрия телефона: место, память, сеть, аптайм, защищён ли экран.
    storage_total_mb: Optional[int] = None
    storage_free_mb: Optional[int] = None
    ram_total_mb: Optional[int] = None
    network: Optional[str] = None  # wifi | mobile | none
    wifi_ssid: Optional[str] = None
    ip_address: Optional[str] = None
    uptime_seconds: Optional[int] = None
    secure_lock: Optional[bool] = None  # есть ли пароль/PIN на экране
    serial_number: Optional[str] = None
    imei: Optional[str] = None
    sim_operator: Optional[str] = None


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
    # Как часто телефон отдельно спрашивает команды будильником. Приходит с
    # сервера, чтобы частоту можно было менять не пересобирая APK.
    command_poll_seconds: int = 120


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
    apps: list[MdmApp] = Field(default_factory=list)
    apps_updated_at: Optional[str] = None
    play_protect: Optional[bool] = None
    storage_total_mb: Optional[int] = None
    storage_free_mb: Optional[int] = None
    ram_total_mb: Optional[int] = None
    network: Optional[str] = None
    wifi_ssid: Optional[str] = None
    ip_address: Optional[str] = None
    uptime_seconds: Optional[int] = None
    secure_lock: Optional[bool] = None
    serial_number: Optional[str] = None
    imei: Optional[str] = None
    sim_operator: Optional[str] = None
    lock_message: Optional[str] = None
    snapshots: list[MdmSnapshot] = Field(default_factory=list)
    commands: list[MdmCommand] = Field(default_factory=list)


class MdmDeviceUpdate(BaseModel):
    name: Optional[str] = None
    salon_id: Optional[str] = None


class MdmCommandCreate(BaseModel):
    type: CommandType
    params: dict[str, Any] = Field(default_factory=dict)


class MdmAgentInfo(BaseModel):
    """APK агента, лежащий на сервере, и его расхождение с парком."""

    available: bool = False
    version_name: Optional[str] = None
    version_code: Optional[int] = None
    size: Optional[int] = None
    sha256: Optional[str] = None
    uploaded_at: Optional[str] = None
    url: Optional[str] = None
    # Сколько телефонов сообщают версию, отличную от лежащей на сервере.
    outdated_devices: int = 0


class MdmSnapshot(BaseModel):
    """Снимок с камеры телефона."""

    id: str
    lens: Optional[str] = None  # "back" | "front"
    taken_at: Optional[str] = None
    size: int
    url: str


class MdmLibraryApp(BaseModel):
    """APK, загруженный в панель для раздачи на телефоны."""

    id: str
    filename: str
    package: Optional[str] = None
    version_name: Optional[str] = None
    version_code: Optional[int] = None
    size: int
    uploaded_at: Optional[str] = None
    url: str
    # "apk" — обычное приложение одним файлом; "xapk" — набор из базового
    # APK и довесков под процессор, экран и язык, который ставится одной
    # транзакцией.
    kind: Optional[str] = None
    parts: int = 1
    # Внутри есть данные для игр, которые мы не раскладываем: приложение
    # встанет, но может не запуститься.
    has_obb: bool = False
    # На скольких телефонах этот пакет уже стоит — по данным инвентаризации.
    installed_on: int = 0


class MdmProvisioning(BaseModel):
    """Данные для QR первичной настройки телефона.

    `payload` — готовая строка, которую нужно закодировать в QR-код: её
    читает мастер первичной настройки Android после шести тапов по экрану
    приветствия на сброшенном телефоне.
    """

    ready: bool
    payload: Optional[str] = None
    # Чего не хватает, человеческим языком, если ready=False.
    problems: list[str] = Field(default_factory=list)


class MdmAgentRolloutResult(BaseModel):
    queued: int
    skipped: int


class MdmSchedule(BaseModel):
    """Расписание: команда каждый день в HH:MM для группы телефонов."""

    id: Optional[str] = None
    time: str  # "HH:MM" по Москве
    command_type: CommandType
    command_params: dict[str, Any] = Field(default_factory=dict)
    target: str = "all"  # "all" | "salon:<id>" | "device:<id>"
    enabled: bool = True
    last_run_date: Optional[str] = None


class MdmScheduleCreate(BaseModel):
    time: str
    command_type: CommandType
    command_params: dict[str, Any] = Field(default_factory=dict)
    target: str = "all"
    enabled: bool = True


class MdmBroadcastResult(BaseModel):
    """Сколько телефонов получили команду при массовой рассылке."""

    queued: int
    total: int


class MdmLostMode(BaseModel):
    """Тело запроса режима пропажи: необязательное сообщение на экран."""

    message: Optional[str] = None


class MdmSettingsUpdate(BaseModel):
    """Что можно поменять из панели, не трогая файлы на сервере."""

    command_poll_seconds: int = Field(ge=30, le=3600)


class MdmEnrollmentInfo(BaseModel):
    """Что нужно вбить в агента при первой установке."""

    server_url: str
    enroll_key: str
    configured: bool
    # Показывается в панели, чтобы обещанная там задержка команд не
    # расходилась с тем, что телефоны делают на самом деле.
    command_poll_seconds: int = 120
