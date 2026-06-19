"""Конфигурация приложения. Все настройки берутся из окружения / файла .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Ollama Cloud ---
    # Ключ обязателен: если его нет, приложение упадёт на старте с понятной
    # ошибкой, а не на каждом запросе. Это правильное поведение fail-fast.
    ollama_api_key: str
    # Тег модели вынесен в .env: облачные теги со временем меняются.
    ollama_model: str = "deepseek-v3.2"
    ollama_base_url: str = "https://ollama.com"
    request_timeout: float = 60.0  # крупные облачные модели бывают неторопливы

    # --- HTTP-сервер ---
    host: str = "127.0.0.1"
    port: int = 8000


settings = Settings()  # type: ignore[call-arg]
