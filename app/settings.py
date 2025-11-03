from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import JsonConfigSettingsSource


class Settings(BaseSettings):
    """Application settings with sane defaults for local usage."""

    telegram_bot_token: str = Field("dummy", env="TELEGRAM_BOT_TOKEN")
    excel_file: str = Field("data.xlsx", env="EXCEL_FILE")
    users_file: str = Field("user.json", env="USERS_FILE")
    advance_requests_file: str = Field(
        "advance_requests.json", env="ADVANCE_REQUESTS_FILE"
    )
    adjustments_file: str = Field("adjustments.json", env="ADJUSTMENTS_FILE")
    vacations_file: str = Field("vacations.json", env="VACATIONS_FILE")
    bonuses_penalties_file: str = Field(
        "bonuses_penalties.json", env="BONUSES_PENALTIES_FILE"
    )
    assets_file: str = Field("assets.json", env="ASSETS_FILE")
    admin_id: int = Field(0, env="ADMIN_ID")
    admin_chat_id: int = Field(5495663985, env="ADMIN_CHAT_ID")
    admin_login: str = Field("admin", env="ADMIN_LOGIN")
    admin_password: str | None = Field(None, env="ADMIN_PASSWORD")
    user_login: str = Field("user", env="USER_LOGIN")
    user_password: str | None = Field(None, env="USER_PASSWORD")
    admin_token: str | None = Field(None, env="ADMIN_TOKEN")
    font_path: str = Field("fonts/DejaVuSans.ttf", env="FONT_PATH")
    card_dispatch_chat_id: int = Field(-1002667932339, env="CARD_DISPATCH_CHAT_ID")
    max_advance_amount_per_month: int = Field(
        500000000, env="MAX_ADVANCE_AMOUNT_PER_MONTH"
    )
    secret_key: str = Field("change_me", env="SECRET_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        json_file="config.json",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()
