from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with sane defaults for local usage."""

    telegram_bot_token: str = Field(
        "dummy", validation_alias="TELEGRAM_BOT_TOKEN"
    )
    # Community/group access token (messages scope) for the (future) VK bot —
    # empty until a VK community exists; app/vk_main.py refuses to start
    # without it rather than crashing on a bad token.
    vk_api_token: str = Field("", validation_alias="VK_API_TOKEN")
    excel_file: str = Field("data.xlsx", validation_alias="EXCEL_FILE")
    users_file: str = Field("user.json", validation_alias="USERS_FILE")
    advance_requests_file: str = Field(
        "advance_requests.json", validation_alias="ADVANCE_REQUESTS_FILE"
    )
    adjustments_file: str = Field(
        "adjustments.json", validation_alias="ADJUSTMENTS_FILE"
    )
    vacations_file: str = Field(
        "vacations.json", validation_alias="VACATIONS_FILE"
    )
    leave_requests_file: str = Field(
        "leave_requests.json", validation_alias="LEAVE_REQUESTS_FILE"
    )
    employee_messages_file: str = Field(
        "employee_messages.json", validation_alias="EMPLOYEE_MESSAGES_FILE"
    )
    bonuses_penalties_file: str = Field(
        "bonuses_penalties.json",
        validation_alias="BONUSES_PENALTIES_FILE",
    )
    assets_file: str = Field("assets.json", validation_alias="ASSETS_FILE")
    admin_id: int = Field(0, validation_alias="ADMIN_ID")
    admin_chat_id: int = Field(
        5495663985, validation_alias="ADMIN_CHAT_ID"
    )
    admin_login: str = Field("admin", validation_alias="ADMIN_LOGIN")
    admin_password: str | None = Field(
        None, validation_alias="ADMIN_PASSWORD"
    )
    user_login: str = Field("user", validation_alias="USER_LOGIN")
    user_password: str | None = Field(
        None, validation_alias="USER_PASSWORD"
    )
    admin_token: str | None = Field(None, validation_alias="ADMIN_TOKEN")
    font_path: str = Field("fonts/DejaVuSans.ttf", validation_alias="FONT_PATH")
    card_dispatch_chat_id: int = Field(
        -1002667932339, validation_alias="CARD_DISPATCH_CHAT_ID"
    )
    card_dispatch_chats: list[dict[str, Any]] = Field(
        default_factory=list, validation_alias="CARD_DISPATCH_CHATS"
    )
    max_advance_amount_per_month: int = Field(
        500000000,
        validation_alias="MAX_ADVANCE_AMOUNT_PER_MONTH",
    )
    secret_key: str = Field("change_me", validation_alias="SECRET_KEY")

    # Proxy для Telegram API (например: "socks5://127.0.0.1:1080" или "http://127.0.0.1:8080")
    telegram_proxy: str | None = Field(None, validation_alias="TELEGRAM_PROXY")
    # Отдельный (не переиспользующий telegram_proxy) прокси для обращений к
    # Anthropic API — сплит-туннель VPN держит эти два переключателя
    # независимыми: у Телеграма и у Клода разные требования к сети, и до
    # этого поля llm_client.py читал именно telegram_proxy, из-за чего
    # включить прокси только для одного из двух было нельзя.
    claude_proxy: str | None = Field(None, validation_alias="CLAUDE_PROXY")

    # amoCRM (расчёт ЗП менеджеров). Токены обновляются автоматически и
    # дописываются обратно в .env.
    amo_domain: str = Field("", validation_alias="AMO_DOMAIN")
    amo_client_id: str = Field("", validation_alias="AMO_CLIENT_ID")
    amo_client_secret: str = Field("", validation_alias="AMO_CLIENT_SECRET")
    amo_redirect_uri: str = Field("", validation_alias="AMO_REDIRECT_URI")
    amo_access_token: str = Field("", validation_alias="AMO_ACCESS_TOKEN")
    amo_refresh_token: str = Field("", validation_alias="AMO_REFRESH_TOKEN")

    # Firebird database для расчёта зарплаты (продажи)
    firebird_host: str = Field("localhost", validation_alias="FIREBIRD_HOST")
    firebird_port: int = Field(3050, validation_alias="FIREBIRD_PORT")
    firebird_database: str = Field(
        r"D:\Agbis\DB\ARM_21.fdb", validation_alias="FIREBIRD_DATABASE"
    )
    firebird_user: str = Field("SYSDBA", validation_alias="FIREBIRD_USER")
    firebird_password: str = Field("masterkey", validation_alias="FIREBIRD_PASSWORD")
    firebird_charset: str = Field("UTF8", validation_alias="FIREBIRD_CHARSET")

    # Хранилище фотографий Agbis. Полноразмерные снимки лежат не в базе (там
    # только миниатюры) и не в облаке, а на агенте локального хранилища —
    # компьютере в салоне, доступном снаружи через шлюз im-gate.com. Адрес и
    # порт агента берутся из MST_AGENTS, здесь только учётные данные.
    # Пароль хранится в том же виде, в каком его шлёт сам Agbis, — SHA-1.
    agbis_storage_user: str = Field("", validation_alias="AGBIS_STORAGE_USER")
    agbis_storage_password_sha1: str = Field(
        "", validation_alias="AGBIS_STORAGE_PASSWORD_SHA1"
    )
    agbis_storage_dep_id: int = Field(21, validation_alias="AGBIS_STORAGE_DEP_ID")
    # Вне каталога app/: deploy.ps1 зеркалит его через robocopy /MIR и стёр бы кэш.
    agbis_photo_cache_dir: str = Field(
        r"D:\Agbis\BonjourPhotoCache", validation_alias="AGBIS_PHOTO_CACHE_DIR"
    )
    agbis_photo_cache_limit_mb: int = Field(
        5120, validation_alias="AGBIS_PHOTO_CACHE_LIMIT_MB"
    )

    # Excel файл с окладами
    payroll_excel_file: str = Field(
        r"C:\Users\hrbon\Desktop\telegram_bot\ФОТ админы 2026.xlsx",
        validation_alias="PAYROLL_EXCEL_FILE"
    )

    # Файл для хранения планов продаж сотрудников
    sales_plans_file: str = Field(
        "sales_plans.json", validation_alias="SALES_PLANS_FILE"
    )

    # Файл для хранения статусов выплаты зарплат
    payroll_settlements_file: str = Field(
        "payroll_settlements.json", validation_alias="PAYROLL_SETTLEMENTS_FILE"
    )

    # Источник данных для отчёта по зарплате в боте: "excel" или "sql"
    salary_bot_source: str = Field("excel", validation_alias="SALARY_BOT_SOURCE")

    # Файл для хранения данных о салонах
    salons_file: str = Field("salons.json", validation_alias="SALONS_FILE")

    # Файл для хранения кодов точек и планов продаж по точкам
    locations_file: str = Field("locations.json", validation_alias="LOCATIONS_FILE")

    # Файл для хранения категорий и правил кассовых перемещений
    cash_categories_file: str = Field("cash_categories.json", validation_alias="CASH_CATEGORIES_FILE")

    # Файл для хранения отметок об открытии смены
    shift_checkins_file: str = Field("shift_checkins.json", validation_alias="SHIFT_CHECKINS_FILE")

    # Файл для хранения событий счётчика посетителей
    visitor_events_file: str = Field("visitor_events.json", validation_alias="VISITOR_EVENTS_FILE")

    # Файл для хранения точек сброса счётчика посетителей (по салонам)
    visitor_counter_resets_file: str = Field(
        "visitor_counter_resets.json", validation_alias="VISITOR_COUNTER_RESETS_FILE"
    )

    # Статический API-ключ для устройств-счётчиков посетителей (ESP8266 и т.п.)
    visitor_counter_api_key: str = Field("", validation_alias="VISITOR_COUNTER_API_KEY")

    # Файл для хранения пользователей бота (для привязки к сотрудникам)
    bot_users_file: str = Field("bot_users.json", validation_alias="BOT_USERS_FILE")

    # Файл для хранения пользователей ВКонтакте (для привязки к сотрудникам,
    # тот же принцип, что и bot_users_file, — до появления самого VK-бота)
    vk_bot_users_file: str = Field("vk_bot_users.json", validation_alias="VK_BOT_USERS_FILE")

    # Авито API (для авто-импорта откликов)
    avito_client_id: str = Field("", validation_alias="AVITO_CLIENT_ID")
    avito_client_secret: str = Field("", validation_alias="AVITO_CLIENT_SECRET")

    # hh.ru API (для авто-импорта откликов)
    hh_client_id: str = Field("", validation_alias="HH_CLIENT_ID")
    hh_client_secret: str = Field("", validation_alias="HH_CLIENT_SECRET")

    # Публичный адрес этого сервера — нужен там, где код сам строит свой же
    # внешний URL (сейчас только hh/Avito webhook-подписки в
    # api/recruitment.py). request.base_url для этого не годится: xtunnel
    # проксирует запрос на localhost:8000 и не сохраняет исходный Host, так
    # что base_url всегда получался бы "https://localhost:8000" независимо
    # от того, через какой домен реально обратился браузер — из-за этого
    # подписка либо регистрировалась по недоступному извне адресу, либо (при
    # проверке статуса) не находила себя же среди уже оформленных подписок
    # и вечно показывала "не подключено", даже когда всё уже было подключено.
    public_base_url: str = Field("https://app.bonjour.pw", validation_alias="PUBLIC_BASE_URL")

    # Сплит-туннель VPN (см. app/services/vpn_service.py): какие свои
    # исходящие соединения (Telegram, Claude API, ...) идут через локальный
    # прокси xray-core, а какие — напрямую. Файл — не токены/секреты, а
    # ссылка на подписку + выбранный сервер + флаги "что через VPN"; сама
    # подписка тем не менее содержит боевой VLESS-ключ, поэтому файл в
    # .gitignore, как и остальные новые runtime-данные этого приложения.
    vpn_settings_file: str = Field("vpn_settings.json", validation_alias="VPN_SETTINGS_FILE")
    # Каталог с бинарником xray-core и сгенерированным из подписки
    # config.json — вне app/ и admin_frontend/, чтобы деплой (robocopy /MIR
    # тех двух папок) их не трогал, и вне git, потому что config.json несёт
    # тот же боевой VLESS-ключ.
    vpn_dir: str = Field("vpn", validation_alias="VPN_DIR")
    # Локальные порты xray-core поднимает сам по нашему config.json — см.
    # vpn_service.BASE_XRAY_CONFIG. Не заводить под них env-переменные:
    # это внутренний loopback-контракт между нашим кодом и тут же
    # сгенерированным конфигом, снаружи их никто не читает.
    vpn_socks_proxy: str = "socks5://127.0.0.1:10808"
    # Реальная сетевая карта для "прямого" исходящего трафика в TUN-режиме
    # (см. vpn_service.build_tun_config) — "auto" в самом xray-core у нас на
    # этой машине не резолвится ("Failed to find matching adapter name"),
    # из-за чего direct-трафик зацикливался обратно в тот же TUN-адаптер
    # вместо выхода в сеть. Имя — как в `Get-NetAdapter` (Name), не
    # InterfaceDescription; сменится при переустановке сетевой карты.
    vpn_tun_outbound_interface: str = Field("Ethernet", validation_alias="VPN_TUN_OUTBOUND_INTERFACE")

    # StarLine (телематика: пробег авто курьера)
    starline_app_id: str = Field("", validation_alias="STARLINE_APP_ID")
    starline_app_secret: str = Field("", validation_alias="STARLINE_APP_SECRET")
    starline_login: str = Field("", validation_alias="STARLINE_LOGIN")
    starline_password: str = Field("", validation_alias="STARLINE_PASSWORD")

    # Уточнение длины GPS-разрывов по дорогам, а не по прямой (курьерский пробег).
    # Оба провайдера опциональны и независимы; если задан только один — используется он.
    yandex_router_api_key: str = Field("", validation_alias="YANDEX_ROUTER_API_KEY")
    ors_api_key: str = Field("", validation_alias="ORS_API_KEY")  # openrouteservice.org

    # Файлы для зарплаты курьера
    courier_plans_file: str = Field("courier_plans.json", validation_alias="COURIER_PLANS_FILE")
    courier_salary_file: str = Field("courier_salary_accruals.json", validation_alias="COURIER_SALARY_FILE")
    courier_mileage_file: str = Field("courier_mileage.json", validation_alias="COURIER_MILEAGE_FILE")
    courier_track_file: str = Field("courier_track.json", validation_alias="COURIER_TRACK_FILE")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    _json_files: ClassVar[tuple[str, ...]] = ("config.json",)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        json_files = cls._resolve_json_files(cls._json_files)

        def json_config_settings_source(
            _settings: BaseSettings | None = None,
        ) -> dict[str, Any]:
            data: dict[str, Any] = {}
            for path in json_files:
                try:
                    raw = path.read_bytes()
                except FileNotFoundError:
                    continue
                if not raw:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except UnicodeDecodeError:
                    try:
                        payload = json.loads(raw.decode("utf-8-sig"))
                    except UnicodeDecodeError:
                        continue
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    data.update(payload)
            # Drop empty strings so Pydantic falls back to field defaults
            return {k: v for k, v in data.items() if v != ""}


        return (
            init_settings,
            env_settings,
            dotenv_settings,
            json_config_settings_source,
            file_secret_settings,
        )

    @staticmethod
    def _resolve_json_files(config_value: Any) -> list[Path]:
        paths: list[Path] = []
        if not config_value:
            return paths
        if isinstance(config_value, (str, Path)):
            return [Path(config_value)]
        if isinstance(config_value, Iterable):
            for item in config_value:
                if isinstance(item, (str, Path)):
                    paths.append(Path(item))
        return paths


settings = Settings()
