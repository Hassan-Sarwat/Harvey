from app.core.config import get_settings
from app.services.legal_data_hub import LegalDataHubClient


async def test_legal_data_hub_returns_fallback_evidence(monkeypatch):
    monkeypatch.setenv("LDA_CLIENT", "")
    monkeypatch.setenv("LDA_SECRET", "")
    client = LegalDataHubClient()

    evidence = await client.search_evidence("Can we waive data subject rights?", domain="data_protection")

    assert evidence
    assert "citation" in evidence[0]


async def test_legal_data_hub_calls_otto_schmidt_api_when_credentials_are_configured(monkeypatch):
    expected_results = [
        {
            "source": "Otto Schmidt / Legal Data Hub",
            "citation": "BGB Section 276",
            "quote": "Intent cannot be released in advance.",
        }
    ]

    class StubResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[dict[str, str]]]:
            return {"results": expected_results}

    class StubAsyncClient:
        calls: list[dict] = []

        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "StubAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, *, auth: tuple[str, str], json: dict) -> StubResponse:
            self.calls.append({"url": url, "auth": auth, "json": json, "timeout": self.timeout})
            return StubResponse()

    monkeypatch.setenv("LDA_CLIENT", "client-id")
    monkeypatch.setenv("LDA_SECRET", "client-secret")
    monkeypatch.setenv("LEGAL_DATA_HUB_BASE_URL", "https://otto-schmidt.example")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.legal_data_hub.httpx.AsyncClient", StubAsyncClient)

    evidence = await LegalDataHubClient().search_evidence("Can BMW accept unlimited liability?", domain="litigation")

    assert evidence == expected_results
    assert StubAsyncClient.calls == [
        {
            "url": "https://otto-schmidt.example/semantic-search",
            "auth": ("client-id", "client-secret"),
            "json": {"query": "Can BMW accept unlimited liability?", "data_assets": ["Gesetze", "Rechtsprechung"]},
            "timeout": 8.0,
        }
    ]
