from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Harvey BMW Contract Assistant"
    lda_client: str | None = None
    lda_secret: str | None = None
    openai_api_key: str | None = None
    legal_data_hub_base_url: str = "https://api.legal-data-analytics.com"
    legal_data_hub_search_path: str = "/semantic-search"
    legal_data_hub_data_assets: str = "Gesetze,Rechtsprechung"
    legal_data_hub_auth_mode: str = "basic"
    legal_data_hub_timeout: float = 8.0
    use_legal_fallback: bool = True
    upload_storage_dir: str = "storage"
    database_url: str | None = None

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
