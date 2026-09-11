from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"
    app_secret_key: str
    database_url: str
    session_cookie_name: str = "ai_arbitr_session"
    cors_origins: str = "http://localhost:5173"

    smtp_host: str = "smtp.yandex.ru"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    yandex_gpt_api_key: str = ""
    yandex_gpt_folder_id: str = ""
    yandex_gpt_model_uri: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


def get_cors_origins() -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
