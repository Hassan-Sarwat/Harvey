from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Harvey BMW Contract Assistant"
    lda_client: str | None = None
    lda_secret: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_reasoning_effort: str = "medium"
    legal_data_hub_base_url: str = "https://otto-schmidt.legal-data-hub.com"
    legal_data_hub_qna_path: str = "/api/qna"
    legal_data_hub_search_path: str = "/api/search"
    legal_data_hub_token_url: str = "https://online.otto-schmidt.de/token"
    legal_data_hub_data_assets: str = "Gesetze,Rechtsprechung"
    legal_data_hub_auth_mode: str = "oauth2"
    legal_data_hub_timeout: float = 20.0
    use_legal_fallback: bool = True
    upload_storage_dir: str = "storage"
    database_url: str | None = None

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
