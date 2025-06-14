from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    excel_file: str = Field(..., env="EXCEL_FILE")
    users_file: str = Field(..., env="USERS_FILE")
    advance_requests_file: str = Field(..., env="ADVANCE_REQUESTS_FILE")
    admin_id: int = Field(0, env="ADMIN_ID")
    admin_chat_id: int = Field(0, env="ADMIN_CHAT_ID")
    admin_login: str = Field("admin", env="ADMIN_LOGIN")
    admin_password: str | None = Field(None, env="ADMIN_PASSWORD")
    user_login: str = Field("user", env="USER_LOGIN")
    user_password: str | None = Field(None, env="USER_PASSWORD")
    admin_token: str | None = Field(None, env="ADMIN_TOKEN")
    font_path: str = Field("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", env="FONT_PATH")
    card_dispatch_chat_id: int = Field(-1002667932339, env="CARD_DISPATCH_CHAT_ID")
    max_advance_amount_per_month: int = Field(500000000, env="MAX_ADVANCE_AMOUNT_PER_MONTH")
    secret_key: str = Field("change_me", env="SECRET_KEY")

    class Config:
        env_file = ".env"

settings = Settings()
