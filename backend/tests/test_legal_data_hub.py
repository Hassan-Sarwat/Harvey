from app.services.legal_data_hub import LegalDataHubClient


async def test_legal_data_hub_returns_fallback_evidence(monkeypatch):
    monkeypatch.setenv("LDA_CLIENT", "")
    monkeypatch.setenv("LDA_SECRET", "")
    client = LegalDataHubClient()

    evidence = await client.search_evidence("Can we waive data subject rights?", domain="data_protection")

    assert evidence
    assert "citation" in evidence[0]
