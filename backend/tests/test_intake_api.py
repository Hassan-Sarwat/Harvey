from __future__ import annotations

from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile

from app.api import intake
from app.services.escalation_repository import EscalationRepository
from app.services.history_repository import HistoryRepository
from app.services.legal_data_hub import LegalDataHubClient


async def test_intake_analyze_returns_louis_frontend_shape(monkeypatch):
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    payload = await intake.analyze(
        question="Can BMW accept a DPA with a 72 hour breach notice?",
        context="The supplier will process BMW employee personal data.",
        selected_sources='["bmw_data_protection_playbook","legal_data_hub"]',
        selected_agents="[]",
        demo_mode=False,
        files=[_upload_file("supplier-dpa.txt", b"BMW supplier processes personal data and gives breach notice within 72 hours.")],
    )

    assert payload["agent_routing_mode"] == "auto"
    assert "legal_checker" in payload["routed_agents"]
    assert payload["matter_summary"]["agreement_type"] == "Data processing agreement / privacy addendum"
    assert payload["agent_steps"]
    assert payload["legal_sources"][0]["source"] == "Otto Schmidt / Legal Data Hub"
    assert payload["escalation_state"] in {
        "No legal escalation recommended",
        "Legal review recommended",
        "Legal review required before signature",
    }


async def test_intake_demo_uses_sample_contract_and_returns_findings(monkeypatch):
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    payload = await intake.demo()

    assert payload["question"] == intake.DEMO_QUESTION
    assert payload["findings"]
    assert payload["escalation_state"] == "Legal review required before signature"
    assert payload["suggested_language"]


async def test_general_question_is_stored_in_history(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    payload = await intake.analyze(
        message="Can BMW accept a 72 hour breach notice?",
        mode="general_question",
        files=[],
    )

    assert payload["mode"] == "general_question"
    assert payload["history_thread_id"]
    detail = HistoryRepository(database_url).get_item(payload["history_thread_id"])
    assert detail is not None
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["runs"][0]["sources_used"]


async def test_final_contract_review_sets_history_status(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    monkeypatch.setattr(intake, "EscalationRepository", lambda: EscalationRepository(database_url))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    approved = await intake.analyze(
        message="This is the final version. Effective Date: 1 January 2026. Services agreement between BMW and ACME for a training workshop.",
        mode="contract_review",
        is_final_version=True,
        files=[],
    )
    pending = await intake.analyze(
        message="This is the final version. Supplier accepts unlimited liability for all consequential damages.",
        mode="contract_review",
        is_final_version=True,
        files=[],
    )

    assert approved["contract_status"] == "approved"
    assert pending["contract_status"] == "pending_legal"
    assert pending["history_thread_id"]
    detail = HistoryRepository(database_url).get_item(pending["history_thread_id"])
    assert detail is not None
    assert detail["contract_status"] == "pending_legal"
    assert any(event["event_type"] == "pending_legal" for event in detail["events"])


def _upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file, filename=filename)


async def _fake_search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
    return [
        {
            "source": "Otto Schmidt / Legal Data Hub",
            "citation": "GDPR Art. 33",
            "quote": "Controllers must notify personal data breaches within statutory deadlines.",
            "url": "https://example.test/gdpr-33",
        }
    ]
