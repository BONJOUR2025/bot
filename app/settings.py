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

    # Firebird database для расчёта зарплаты (продажи)
    firebird_host: str = Field("localhost", validation_alias="FIREBIRD_HOST")
    firebird_port: int = Field(3050, validation_alias="FIREBIRD_PORT")
    firebird_database: str = Field(
        r"C:\Agbis\DB\ARM_13.fdb", validation_alias="FIREBIRD_DATABASE"
    )
    firebird_user: str = Field("SYSDBA", validation_alias="FIREBIRD_USER")
    firebird_password: str = Field("masterkey", validation_alias="FIREBIRD_PASSWORD")
    firebird_charset: str = Field("UTF8", validation_alias="FIREBIRD_CHARSET")

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
