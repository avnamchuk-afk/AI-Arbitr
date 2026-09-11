from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_base_url: str = "http://localhost:5173"
    app_secret_key: str
    database_url: str

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
