from __future__ import annotations

from tempfile import SpooledTemporaryFile

import pytest
from starlette.datastructures import UploadFile

from app.api import intake
from app.services.escalation_repository import EscalationRepository
from app.services.history_repository import HistoryRepository
from app.services.legal_data_hub import LegalDataHubClient
from app.workflows import general_question as general_question_module
from app.workflows import legal_qa as legal_qa_module


@pytest.fixture(autouse=True)
def disable_openai_answers(monkeypatch):
    async def _empty_openai_answer(**_kwargs):
        return ""

    monkeypatch.setattr(legal_qa_module, "_openai_answer", _empty_openai_answer)
    monkeypatch.setattr(general_question_module, "_openai_general_answer", _empty_openai_answer)


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


@pytest.mark.parametrize(
    "message",
    [
        "Summarize the DPA playbook for non legal people",
        "Summarize the data protection agreement playbook",
    ],
)
async def test_general_question_dpa_summary_uses_company_playbook_file(message, tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    openai_calls: list[dict] = []

    async def _unexpected_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        raise AssertionError(f"Legal Data Hub should not be called for company playbook summaries: {query}")

    async def _generated_answer(**kwargs):
        openai_calls.append(kwargs)
        return "OpenAI tailored DPA playbook summary"

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _unexpected_search)
    monkeypatch.setattr(general_question_module, "_openai_general_answer", _generated_answer)

    payload = await intake.analyze(
        message=message,
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "playbook_file_summary"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["routed_agents"] == ["playbook_document_reader"]
    assert payload["selected_sources"] == ["company_playbook_file"]
    playbook_usage = next(source for source in payload["source_usage"] if source["id"] == "company_playbook_file")
    assert playbook_usage["item_count"] == 1
    assert playbook_usage["items"][0]["title"] == "dpa.docx"
    assert payload["plain_answer"] == "OpenAI tailored DPA playbook summary"
    assert openai_calls[0]["answer_kind"] == "playbook_file_summary"
    assert openai_calls[0]["question"] == message
    assert openai_calls[0]["documents"][0]["filename"] == "dpa.docx"
    assert "DPA NEGOTIATION PLAYBOOK" in openai_calls[0]["documents"][0]["text"]

    detail = HistoryRepository(database_url).get_item(payload["history_thread_id"])
    assert detail is not None
    latest_run = detail["runs"][0]
    assert latest_run["result"]["metrics"]["answer_kind"] == "playbook_file_summary"
    assert latest_run["sources_used"][0]["id"] == "company_playbook_file"
    assert "dpa.docx" in latest_run["sources_used"][0]["items"][0]["title"]


async def test_general_question_dpa_playbook_openai_unavailable_does_not_return_fixed_summary(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))

    async def _unexpected_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        raise AssertionError(f"Legal Data Hub should not be called for company playbook summaries: {query}")

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _unexpected_search)

    payload = await intake.analyze(
        message="Summarize the DPA playbook for non legal people",
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "playbook_file_summary"
    assert payload["metrics"]["ai_generated"] is False
    assert "OpenAI answer generator is unavailable" in payload["plain_answer"]
    assert "DPA NEGOTIATION PLAYBOOK" not in payload["plain_answer"]


async def test_general_question_procurement_playbook_missing_asks_for_upload(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))

    async def _unexpected_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        raise AssertionError(f"Legal Data Hub should not be called for missing playbook lookups: {query}")

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _unexpected_search)

    payload = await intake.analyze(
        message="Summarize the procurement playbook",
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "playbook_file_missing"
    assert payload["selected_sources"] == []
    assert "could not find a company playbook" in payload["plain_answer"].lower()
    assert "upload" in payload["plain_answer"].lower()


async def test_general_question_summarizes_uploaded_document_without_legal_lookup(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    openai_calls: list[dict] = []

    async def _unexpected_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        raise AssertionError(f"Legal Data Hub should not be called for document-only summaries: {query}")

    async def _generated_answer(**kwargs):
        openai_calls.append(kwargs)
        return "OpenAI document summary for business"

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _unexpected_search)
    monkeypatch.setattr(general_question_module, "_openai_general_answer", _generated_answer)

    payload = await intake.analyze(
        message="Summarize this document for the business team.",
        mode="general_question",
        files=[
            _upload_file(
                "supplier-note.txt",
                b"Supplier will provide analytics services to BMW. The services start on 1 May 2026. "
                b"The supplier may use aggregated operational data for service reporting.",
            )
        ],
    )

    assert payload["metrics"]["answer_kind"] == "document_summary"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["routed_agents"] == ["document_summarizer"]
    assert payload["selected_sources"] == ["uploaded_bundle"]
    assert payload["legal_sources"] == []
    assert payload["plain_answer"] == "OpenAI document summary for business"
    assert "Supplier will provide analytics services to BMW" in openai_calls[0]["documents"][0]["text"]
    assert openai_calls[0]["question"] == "Summarize this document for the business team."
    assert payload["source_usage"][0]["id"] == "uploaded_bundle"


async def test_general_question_legal_lookup_uses_legal_hub_without_playbook(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    queries: list[str] = []
    openai_calls: list[dict] = []

    async def _capture_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        queries.append(query)
        return [
            {
                "source": "Otto Schmidt / Legal Data Hub",
                "citation": "GDPR Art. 28",
                "quote": "Processing by a processor must be governed by a contract or other legal act.",
            }
        ]

    async def _generated_legal_answer(**kwargs):
        openai_calls.append(kwargs)
        return "OpenAI GDPR Article 28 answer"

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _capture_search)
    monkeypatch.setattr(legal_qa_module, "_openai_answer", _generated_legal_answer)

    payload = await intake.analyze(
        message="What does GDPR Article 28 require?",
        mode="general_question",
        files=[],
    )

    assert queries == ["What does GDPR Article 28 require?"]
    assert payload["metrics"]["answer_kind"] == "legal_lookup"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["plain_answer"] == "OpenAI GDPR Article 28 answer"
    assert openai_calls[0]["question"] == "What does GDPR Article 28 require?"
    assert openai_calls[0]["legal_basis"][0]["citation"] == "GDPR Art. 28"
    assert payload["selected_sources"] == ["legal_data_hub"]
    assert payload["source_usage"][0]["id"] == "legal_data_hub"
    assert payload["source_usage"][0]["item_count"] == 1


async def test_general_question_legal_lookup_openai_unavailable_keeps_sources(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))

    async def _capture_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        return [
            {
                "source": "Otto Schmidt / Legal Data Hub",
                "citation": "GDPR Art. 28",
                "quote": "Processing by a processor must be governed by a contract or other legal act.",
            }
        ]

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _capture_search)

    payload = await intake.analyze(
        message="What does GDPR Article 28 require?",
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "legal_lookup"
    assert payload["metrics"]["ai_generated"] is False
    assert "OpenAI answer generator is unavailable" in payload["plain_answer"]
    assert payload["selected_sources"] == ["legal_data_hub"]
    assert payload["source_usage"][0]["item_count"] == 1


async def test_general_question_hybrid_document_legal_uses_question_as_legal_query(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    queries: list[str] = []
    openai_calls: list[dict] = []

    async def _capture_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        queries.append(query)
        return [
            {
                "source": "Otto Schmidt / Legal Data Hub",
                "citation": "GDPR Art. 33",
                "quote": "Personal data breach notification must follow statutory timing requirements.",
            }
        ]

    async def _generated_answer(**kwargs):
        openai_calls.append(kwargs)
        return "OpenAI hybrid document legal answer"

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _capture_search)
    monkeypatch.setattr(general_question_module, "_openai_general_answer", _generated_answer)

    payload = await intake.analyze(
        message="Does this breach notice comply with GDPR?",
        mode="general_question",
        files=[
            _upload_file(
                "breach-clause.txt",
                b"The supplier must notify BMW of confirmed personal data breaches within 96 hours after completing its investigation.",
            )
        ],
    )

    assert queries == ["Does this breach notice comply with GDPR?"]
    assert payload["metrics"]["answer_kind"] == "hybrid_document_legal"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["plain_answer"] == "OpenAI hybrid document legal answer"
    assert payload["routed_agents"] == ["document_summarizer", "legal_qa"]
    assert "legal_data_hub" in payload["selected_sources"]
    assert "uploaded_bundle" in payload["selected_sources"]
    assert "96 hours" in openai_calls[0]["documents"][0]["text"]
    assert openai_calls[0]["legal_qa"].legal_basis[0]["citation"] == "GDPR Art. 33"


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
