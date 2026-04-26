from __future__ import annotations

from tempfile import SpooledTemporaryFile

import pytest
from starlette.datastructures import UploadFile

from app.api import intake
from app.core.config import get_settings
from app.services.escalation_repository import EscalationRepository
from app.services.history_repository import HistoryRepository
from app.services.legal_data_hub import LegalDataHubClient
from app.workflows import general_question as general_question_module
from app.workflows import legal_qa as legal_qa_module

ORIGINAL_OPENAI_GENERAL_ANSWER = general_question_module._openai_general_answer


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
    assert payload["escalation_state"] in {"Legal review required before signature", "Needs business input"}
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
async def test_general_question_uses_complete_active_playbooks(message, tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    openai_calls: list[dict] = []

    async def _generated_answer(**kwargs):
        openai_calls.append(kwargs)
        return general_question_module.GeneralAnswerGeneration(answer="OpenAI tailored playbook answer")

    monkeypatch.setattr(general_question_module, "_openai_general_answer", _generated_answer)

    payload = await intake.analyze(
        message=message,
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "general_answer"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["metrics"]["playbook_row_count"] == 19
    assert payload["metrics"]["legal_tool_called"] is True
    assert payload["routed_agents"] == ["legal_qa"]
    assert payload["selected_sources"] == [
        "bmw_data_protection_playbook",
        "bmw_litigation_playbook",
        "legal_data_hub",
    ]
    source_counts = {source["id"]: source["item_count"] for source in payload["source_usage"]}
    assert source_counts == {"bmw_data_protection_playbook": 7, "bmw_litigation_playbook": 12, "legal_data_hub": 0}
    assert payload["plain_answer"] == "OpenAI tailored playbook answer"
    assert openai_calls[0]["question"] == message
    assert {row["_source_id"] for row in openai_calls[0]["playbook_rows"]} == {
        "bmw_data_protection_playbook",
        "bmw_litigation_playbook",
    }

    detail = HistoryRepository(database_url).get_item(payload["history_thread_id"])
    assert detail is not None
    latest_run = detail["runs"][0]
    assert latest_run["result"]["metrics"]["answer_kind"] == "general_answer"
    assert [source["id"] for source in latest_run["sources_used"]] == [
        "bmw_data_protection_playbook",
        "bmw_litigation_playbook",
        "legal_data_hub",
    ]


async def test_general_question_openai_unavailable_still_records_playbooks(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))

    async def _empty_search(self, query: str, domain: str = "general") -> list[dict[str, str]]:
        return []

    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _empty_search)

    payload = await intake.analyze(
        message="Summarize the DPA playbook for non legal people",
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "general_answer"
    assert payload["metrics"]["ai_generated"] is False
    assert payload["metrics"]["playbook_row_count"] == 19
    assert payload["selected_sources"] == [
        "bmw_data_protection_playbook",
        "bmw_litigation_playbook",
        "legal_data_hub",
    ]
    assert "OpenAI answer generator is unavailable" in payload["plain_answer"]
    assert "DPA NEGOTIATION PLAYBOOK" not in payload["plain_answer"]


async def test_general_question_includes_uploaded_documents_as_context(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    openai_calls: list[dict] = []

    async def _generated_answer(**kwargs):
        openai_calls.append(kwargs)
        return general_question_module.GeneralAnswerGeneration(answer="OpenAI document-aware answer")

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

    assert payload["metrics"]["answer_kind"] == "general_answer"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["metrics"]["document_count"] == 1
    assert payload["routed_agents"] == ["legal_qa"]
    assert payload["selected_sources"] == [
        "bmw_data_protection_playbook",
        "bmw_litigation_playbook",
        "uploaded_bundle",
        "legal_data_hub",
    ]
    assert payload["legal_sources"] == []
    assert payload["plain_answer"] == "OpenAI document-aware answer"
    assert "Supplier will provide analytics services to BMW" in openai_calls[0]["documents"][0]["text"]
    assert openai_calls[0]["question"] == "Summarize this document for the business team."
    assert any(source["id"] == "uploaded_bundle" for source in payload["source_usage"])


async def test_openai_general_answer_prefetches_legal_evidence_for_clear_legal_question(monkeypatch):
    queries: list[tuple[str, str]] = []
    completion_calls: list[dict] = []

    class StubLegalDataHub:
        async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
            queries.append((query, domain))
            return [
                {
                    "source": "Otto Schmidt / Legal Data Hub fallback",
                    "citation": "GDPR Art. 28",
                    "quote": "Processing by a processor must be governed by a contract or other legal act.",
                    "retrieval_mode": "fallback",
                    "fallback_reason": "test fallback",
                }
            ]

    class FunctionCall:
        name = "search_german_law"
        arguments = '{"query": "What does GDPR Article 28 require?", "domain": "data_protection"}'

    class ToolCall:
        id = "call-1"
        type = "function"
        function = FunctionCall()

    class Message:
        def __init__(self, content: str, tool_calls: list[ToolCall] | None = None) -> None:
            self.content = content
            self.tool_calls = tool_calls

    class Choice:
        def __init__(self, message: Message) -> None:
            self.message = message

    class Response:
        def __init__(self, message: Message) -> None:
            self.choices = [Choice(message)]

    async def _fake_completion(**kwargs):
        completion_calls.append(kwargs)
        if kwargs.get("tools"):
            return Response(Message("", [ToolCall()]))
        return Response(Message("OpenAI GDPR Article 28 answer with fallback label"))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(general_question_module, "_create_chat_completion", _fake_completion)

    result = await ORIGINAL_OPENAI_GENERAL_ANSWER(
        question="What does GDPR Article 28 require?",
        context="",
        documents=[],
        playbook_rows=[],
        domain="data_protection",
        thread_id=None,
        legal_data_hub=StubLegalDataHub(),
    )

    assert queries == [("What does GDPR Article 28 require?", "data_protection")]
    assert result.answer == "OpenAI GDPR Article 28 answer with fallback label"
    assert result.legal_tool_called is True
    assert result.legal_basis[0]["citation"] == "GDPR Art. 28"
    assert result.legal_basis[0]["retrieval_mode"] == "fallback"
    assert len(completion_calls) == 1
    assert completion_calls[0]["tool_choice"] is None
    assert completion_calls[0]["tools"] is None


async def test_openai_general_answer_returns_live_qna_without_second_model_call(monkeypatch):
    completion_calls: list[dict] = []

    class StubLegalDataHub:
        async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
            return [
                {
                    "source": "Otto Schmidt / Legal Data Hub QnA",
                    "citation": "Tschöpe cloud transfer",
                    "quote": "Cloud transfer source excerpt.",
                    "retrieval_mode": "live",
                    "retrieval_endpoint": "qna",
                    "source_type": "Kommentar",
                    "date": "2025-04-01T00:00:00",
                    "url": "https://online.otto-schmidt.de/db/dokep?parid=tar.06.f.r0265#tar.06.f.r0265",
                    "metadata_source": "[1] Tschöpe, Arbeitsrecht Handbuch, Beschäftigtendatenschutz",
                    "qna_answer": "Die Antwort steht hier als Fließtext.</br><b>Drittlandtransfer</b> braucht Garantien.",
                },
                {
                    "source": "Otto Schmidt / Legal Data Hub QnA",
                    "citation": "DER BETRIEB Drittlandtransfers",
                    "quote": "Article excerpt.",
                    "retrieval_mode": "live",
                    "retrieval_endpoint": "qna",
                    "source_type": "Artikel",
                    "url": "https://online.otto-schmidt.de/db/dokep?parid=db1369631",
                    "metadata_source": "[2] DER BETRIEB, Datenschutzbehörden planen Kontrollen",
                    "qna_answer": "Die Antwort steht hier als Fließtext.</br><b>Drittlandtransfer</b> braucht Garantien.",
                }
            ]

    async def _unexpected_completion(**kwargs):
        completion_calls.append(kwargs)
        raise AssertionError("QnA text should be enough for the direct fast answer")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(general_question_module, "_create_chat_completion", _unexpected_completion)

    result = await ORIGINAL_OPENAI_GENERAL_ANSWER(
        question="Darf ein BMW-Team personenbezogene Fahrzeugdaten an einen externen SaaS-Anbieter senden, wenn der Anbieter außerhalb der EU hostet?",
        context="",
        documents=[],
        playbook_rows=[
            {
                "id": "DPA-007",
                "title": "International data transfers",
                "severity": "blocker",
                "default": "No transfers outside the EU/EEA without prior BMW Group written consent and valid transfer safeguards.",
                "preferred_position": "Keep processing in the EU/EEA or document transfer safeguards before transfer.",
                "red_line": "Third-country transfer without BMW knowledge, SCCs, or safeguards later.",
                "escalation_trigger": "Supplier hosts Company Personal Data outside the EU/EEA.",
            }
        ],
        domain="data_protection",
        thread_id=None,
        legal_data_hub=StubLegalDataHub(),
    )

    assert completion_calls == []
    assert result.legal_tool_called is True
    assert "Die Antwort steht hier als Fließtext." in result.answer
    assert "<b>" not in result.answer
    assert "DPA-007 - International data transfers" in result.answer
    assert result.legal_basis[0]["retrieval_endpoint"] == "qna"
    assert "Sources\n\n- [1] Tschöpe, Arbeitsrecht Handbuch, Beschäftigtendatenschutz (Kommentar, 2025-04-01)" in result.answer
    assert "[Open source](https://online.otto-schmidt.de/db/dokep?parid=tar.06.f.r0265#tar.06.f.r0265)" in result.answer
    assert "- [2] DER BETRIEB, Datenschutzbehörden planen Kontrollen (Artikel)" in result.answer


async def test_openai_general_answer_uses_prefetched_legal_evidence_before_tools(monkeypatch):
    queries: list[tuple[str, str]] = []
    completion_calls: list[dict] = []

    class StubLegalDataHub:
        async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
            queries.append((query, domain))
            return [
                {
                    "source": "Otto Schmidt / Legal Data Hub fallback",
                    "citation": "GDPR Art. 28",
                    "quote": "Processing by a processor must be governed by a contract or other legal act.",
                    "retrieval_mode": "fallback",
                    "fallback_reason": "test fallback",
                }
            ]

    class FunctionCall:
        name = "search_german_law"
        arguments = '{"query": "What does GDPR Article 28 require?", "domain": "data_protection"}'

    class ToolCall:
        id = "call-1"
        type = "function"
        function = FunctionCall()

    class Message:
        def __init__(self, content: str, tool_calls: list[ToolCall] | None = None) -> None:
            self.content = content
            self.tool_calls = tool_calls

    class Choice:
        def __init__(self, message: Message) -> None:
            self.message = message

    class Response:
        def __init__(self, message: Message) -> None:
            self.choices = [Choice(message)]

    async def _fake_completion(**kwargs):
        completion_calls.append(kwargs)
        if kwargs.get("tools"):
            return Response(Message("", [ToolCall()]))
        return Response(Message("OpenAI answer with fallback label"))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(general_question_module, "_create_chat_completion", _fake_completion)

    result = await ORIGINAL_OPENAI_GENERAL_ANSWER(
        question="Please check external authority for this issue.",
        context="",
        documents=[],
        playbook_rows=[],
        domain="data_protection",
        thread_id=None,
        legal_data_hub=StubLegalDataHub(),
    )

    assert queries == [("Please check external authority for this issue.", "data_protection")]
    assert result.answer == "OpenAI answer with fallback label"
    assert result.legal_tool_called is True
    assert result.legal_basis[0]["citation"] == "GDPR Art. 28"
    assert len(completion_calls) == 1
    assert completion_calls[0]["tool_choice"] is None
    assert completion_calls[0]["tools"] is None


async def test_general_question_legal_tool_sources_are_recorded(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))

    async def _generated_answer(**kwargs):
        return general_question_module.GeneralAnswerGeneration(
            answer="OpenAI GDPR Article 28 answer",
            legal_tool_called=True,
            legal_basis=[
                {
                    "source": "Otto Schmidt / Legal Data Hub fallback",
                    "citation": "GDPR Art. 28",
                    "quote": "Processing by a processor must be governed by a contract or other legal act.",
                    "retrieval_mode": "fallback",
                    "fallback_reason": "live Legal Data Hub request failed",
                }
            ],
        )

    monkeypatch.setattr(general_question_module, "_openai_general_answer", _generated_answer)

    payload = await intake.analyze(
        message="What does GDPR Article 28 require?",
        mode="general_question",
        files=[],
    )

    assert payload["metrics"]["answer_kind"] == "general_answer"
    assert payload["metrics"]["ai_generated"] is True
    assert payload["metrics"]["legal_tool_called"] is True
    assert payload["plain_answer"] == "OpenAI GDPR Article 28 answer"
    assert "legal_data_hub" in payload["selected_sources"]
    legal_usage = next(source for source in payload["source_usage"] if source["id"] == "legal_data_hub")
    assert legal_usage["item_count"] == 1
    assert legal_usage["items"][0]["fallback"] is True
    assert legal_usage["items"][0]["fallback_reason"] == "live Legal Data Hub request failed"


async def test_final_contract_review_sets_history_status(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    monkeypatch.setattr(intake, "EscalationRepository", lambda: EscalationRepository(database_url))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    approved = await intake.analyze(
        message=(
            "This is the final version. Effective Date: 1 January 2026. "
            "BMW is controller and Supplier is processor of personal data under GDPR. "
            "Supplier processes personal data only on BMW documented instructions, uses named approved subprocessors, "
            "notifies BMW without undue delay after any personal data breach, maintains TOMs, allows audits, "
            "does not transfer data outside the EU/EEA, and deletes or returns data within 10 business days."
        ),
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


async def test_final_escalation_waits_for_missing_referenced_attachment(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(intake, "HistoryRepository", lambda: HistoryRepository(database_url))
    monkeypatch.setattr(intake, "EscalationRepository", lambda: EscalationRepository(database_url))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    payload = await intake.analyze(
        message="This is the final version. Please escalate if needed.",
        mode="contract_review",
        is_final_version=True,
        files=[
            _upload_file(
                "main-contract.txt",
                (
                    "Effective Date: 1 January 2026. BMW accepts unlimited liability. "
                    "The services are governed by Annex 2 and Annex 3."
                ).encode("utf-8"),
            ),
            _upload_file("annex-2.txt", b"Annex 2 - Data Processing Terms"),
        ],
    )

    assert payload["escalation_state"] == "Needs business input"
    assert payload["contract_status"] == "needs_business_input"
    assert payload["escalation_id"] is None
    assert payload["metrics"]["needs_business_input"] is True
    assert "Annex 3" in payload["matter_summary"]["missing_documents"]
    assert payload["business_input"]["status"] == "needs_business_input"
    assert payload["business_input"]["blocking_count"] == 1
    assert payload["business_input"]["missing_items"][0]["label"] == "Annex 3"
    assert "governed by Annex 2 and Annex 3" in payload["business_input"]["missing_items"][0]["source_quote"]

    detail = HistoryRepository(database_url).get_item(payload["history_thread_id"])
    assert detail is not None
    assert detail["contract_status"] == "needs_business_input"
    assert any(event["event_type"] == "needs_business_input" for event in detail["events"])


async def test_pdf_upload_uses_openai_pdf_fallback_when_local_extraction_is_empty(monkeypatch):
    monkeypatch.setattr(intake, "extract_document_text", lambda _filename, _content: "")

    async def _fake_openai_pdf_text(filename: str, content: bytes) -> str:
        assert filename == "scanned-dpa.pdf"
        assert content.startswith(b"%PDF")
        return "DATA PROCESSING ADDENDUM\nBMW Group personal data is processed under Annex 1."

    monkeypatch.setattr(intake, "_extract_pdf_text_with_openai", _fake_openai_pdf_text)

    extracted = await intake._extract_uploaded_texts([_upload_file("scanned-dpa.pdf", b"%PDF-1.4 image only")])

    assert extracted == [
        {
            "filename": "scanned-dpa.pdf",
            "text": "DATA PROCESSING ADDENDUM\nBMW Group personal data is processed under Annex 1.",
            "character_count": 76,
            "extraction_method": "openai_pdf_input",
        }
    ]


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
