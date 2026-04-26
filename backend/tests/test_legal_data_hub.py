from app.core.config import get_settings
from app.services.legal_data_hub import LegalDataHubClient


async def test_legal_data_hub_returns_fallback_evidence(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LDA_CLIENT", "")
    monkeypatch.setenv("LDA_SECRET", "")
    client = LegalDataHubClient()

    evidence = await client.search_evidence("Can we waive data subject rights?", domain="data_protection")

    assert evidence
    assert "citation" in evidence[0]


async def test_legal_data_hub_calls_otto_schmidt_api_when_credentials_are_configured(monkeypatch):
    """OAuth2 + Elasticsearch DSL: token fetch then per-asset search."""
    es_hit = {
        "_id": "bgb-276",
        "_score": 0.92,
        "_source": {
            "title": "BGB Section 276",
            "content": "Intent cannot be released in advance.",
        },
        "highlight": {
            "content": ["Intent cannot be released in advance."],
        },
    }

    class StubResponse:
        def __init__(self, url: str) -> None:
            self._url = url

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            if "token" in self._url:
                return {"access_token": "test-bearer-token", "expires_in": 3600}
            return {"hits": {"hits": [es_hit]}}

    class StubAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout
            self.calls: list[dict] = []

        async def __aenter__(self) -> "StubAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> StubResponse:
            self.calls.append({"url": url, **{k: v for k, v in kwargs.items()}})
            return StubResponse(url)

    # Patch at module level so _get_bearer_token and search_evidence both use the stub.
    instances: list[StubAsyncClient] = []

    def stub_client_factory(*, timeout: float) -> StubAsyncClient:
        instance = StubAsyncClient(timeout=timeout)
        instances.append(instance)
        return instance

    monkeypatch.setenv("LDA_CLIENT", "client-id")
    monkeypatch.setenv("LDA_SECRET", "client-secret")
    monkeypatch.setenv("LEGAL_DATA_HUB_BASE_URL", "https://otto-schmidt.example")
    monkeypatch.setenv("LEGAL_DATA_HUB_AUTH_MODE", "oauth2")
    monkeypatch.setenv("LEGAL_DATA_HUB_TOKEN_URL", "https://online.otto-schmidt.de/token")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.legal_data_hub.httpx.AsyncClient", stub_client_factory)

    evidence = await LegalDataHubClient().search_evidence(
        "Can BMW accept unlimited liability?", domain="litigation"
    )

    assert evidence, "Expected at least one evidence item"
    assert evidence[0]["citation"] == "BGB Section 276"
    assert evidence[0]["retrieval_mode"] == "live"

    # Collect all calls across all stub instances
    all_calls = [call for instance in instances for call in instance.calls]

    # Token was fetched via client_credentials
    token_calls = [c for c in all_calls if "token" in c["url"]]
    assert token_calls, "Expected an OAuth2 token request"
    token_data = token_calls[0].get("data", {})
    assert token_data.get("grant_type") == "authorization_code"
    assert token_data.get("client_id") == "client-id"
    assert token_data.get("client_secret") == "client-secret"

    # Search was made against both data assets with bearer token
    # Semantic search is attempted first; keyword search is the fallback.
    semantic_calls = [c for c in all_calls if "semantic-search" in c["url"]]
    keyword_calls = [c for c in all_calls if "_search" in c["url"]]
    search_calls = semantic_calls or keyword_calls
    assert len(search_calls) == 2, f"Expected 2 search calls (one per asset), got: {[c['url'] for c in all_calls]}"
    for call in search_calls:
        headers = call.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-bearer-token"

    # After test, clear cache so other tests are not affected
    get_settings.cache_clear()


async def test_legal_data_hub_prefers_otto_schmidt_qna_endpoint(monkeypatch):
    qna_payload = {
        "response_id": "response-123",
        "text": "Die Antwort steht hier als Fließtext.",
        "sourcedocuments": [
            {
                "content": "Quellenauszug zum grenzueberschreitenden Datentransfer.",
                "metadata": {
                    "source": "[1] Tschoepe, Arbeitsrecht Handbuch",
                    "dokumententyp": "Kommentar",
                    "datum": "2025-04-01T00:00:00",
                    "aktenzeichen": "",
                    "oso_url": "https://online.otto-schmidt.de/db/dokep?parid=tar.06.f.r0265#tar.06.f.r0265",
                },
            }
        ],
    }

    class StubResponse:
        def __init__(self, url: str) -> None:
            self._url = url

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            if "token" in self._url:
                return {"access_token": "test-bearer-token", "expires_in": 3600}
            return qna_payload

    class StubAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout
            self.calls: list[dict] = []

        async def __aenter__(self) -> "StubAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> StubResponse:
            self.calls.append({"url": url, **{k: v for k, v in kwargs.items()}})
            return StubResponse(url)

    instances: list[StubAsyncClient] = []

    def stub_client_factory(*, timeout: float) -> StubAsyncClient:
        instance = StubAsyncClient(timeout=timeout)
        instances.append(instance)
        return instance

    monkeypatch.setenv("LDA_CLIENT", "client-id")
    monkeypatch.setenv("LDA_SECRET", "client-secret")
    monkeypatch.setenv("LEGAL_DATA_HUB_BASE_URL", "https://otto-schmidt.legal-data-hub.com")
    monkeypatch.setenv("LEGAL_DATA_HUB_AUTH_MODE", "oauth2")
    monkeypatch.setenv("LEGAL_DATA_HUB_TOKEN_URL", "https://online.otto-schmidt.de/token")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.legal_data_hub.httpx.AsyncClient", stub_client_factory)

    evidence = await LegalDataHubClient().search_evidence(
        "Darf BMW personenbezogene Fahrzeugdaten an einen externen SaaS-Anbieter senden?",
        domain="data_protection",
    )

    assert len(evidence) == 1
    assert evidence[0]["source"] == "Otto Schmidt / Legal Data Hub QnA"
    assert evidence[0]["citation"] == "[1] Tschoepe, Arbeitsrecht Handbuch - Kommentar - 2025-04-01"
    assert evidence[0]["quote"] == "Quellenauszug zum grenzueberschreitenden Datentransfer."
    assert evidence[0]["url"] == "https://online.otto-schmidt.de/db/dokep?parid=tar.06.f.r0265#tar.06.f.r0265"
    assert evidence[0]["retrieval_endpoint"] == "qna"
    assert evidence[0]["qna_answer"] == "Die Antwort steht hier als Fließtext."

    all_calls = [call for instance in instances for call in instance.calls]
    qna_calls = [call for call in all_calls if call["url"].endswith("/api/qna")]
    assert len(qna_calls) == 1
    assert qna_calls[0]["headers"]["Authorization"] == "Bearer test-bearer-token"
    assert qna_calls[0]["json"] == {
        "prompt": "Darf BMW personenbezogene Fahrzeugdaten an einen externen SaaS-Anbieter senden?",
        "data_asset": "*",
        "mode": "attribution",
        "filter": [{}],
    }
    assert not [call for call in all_calls if "semantic-search" in call["url"]]
    get_settings.cache_clear()
