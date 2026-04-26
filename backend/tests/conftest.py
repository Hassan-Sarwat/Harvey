import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def force_offline_legal_data_hub(monkeypatch):
    monkeypatch.setenv("LDA_CLIENT", "")
    monkeypatch.setenv("LDA_SECRET", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
