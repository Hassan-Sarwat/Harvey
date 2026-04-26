import pytest

from app.agents.base import ReviewContext
from app.core.config import get_settings
from app.services.contract_classifier import ContractClassification
from app.services import contract_classifier
from app.workflows import legal_qa as legal_qa_module
from app.workflows.legal_qa import LegalQARequest, LegalQAWorkflow
from app.workflows.review_contract import ContractReviewWorkflow


@pytest.fixture(autouse=True)
def disable_openai_answers(monkeypatch):
    async def _empty_openai_answer(**_kwargs):
        return ""

    monkeypatch.setattr(legal_qa_module, "_openai_answer", _empty_openai_answer)


async def test_contract_review_workflow_returns_aggregate():
    result = await ContractReviewWorkflow().run(
        ReviewContext(contract_id="c1", contract_text="Supplier accepts unlimited liability.")
    )

    assert result.agent_name == "risk_aggregator"
    assert result.requires_escalation is True
    assert result.metadata["agent_count"] == 5
    assert len(result.metadata["escalation_conditions"]) == 4


async def test_contract_review_uses_llm_classifier(monkeypatch):
    async def _fake_llm_classification(_text: str):
        return ContractClassification(
            contract_type="data_protection",
            confidence=0.91,
            rationale="The LLM identified a DPA/privacy addendum.",
            source="openai_llm",
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(contract_classifier, "_llm_contract_classification", _fake_llm_classification)

    result = await ContractReviewWorkflow().run(
        ReviewContext(contract_id="c1", contract_text="BMW vendor privacy addendum for analytics services.")
    )

    understanding = next(item for item in result.metadata["agent_results"] if item["agent_name"] == "contract_understanding")
    assert understanding["metadata"]["inferred_contract_type"] == "data_protection"
    assert understanding["metadata"]["classification_source"] == "openai_llm"


async def test_contract_review_escalates_when_value_exceeds_threshold():
    result = await ContractReviewWorkflow().run(
        ReviewContext(
            contract_id="c1",
            contract_type="data_protection",
            contract_text="Effective Date: 1 January 2026. BMW contract value is EUR 250,000 for processor services.",
        )
    )

    assert result.requires_escalation is True
    assert any(finding.id == "contract-value-threshold" for finding in result.findings)
    condition = next(item for item in result.metadata["escalation_conditions"] if item["id"] == "contract_value_threshold")
    assert condition["triggered"] is True


async def test_contract_review_escalates_when_matter_not_covered_by_playbook():
    result = await ContractReviewWorkflow().run(
        ReviewContext(
            contract_id="c1",
            contract_type="general",
            contract_text="Effective Date: 1 January 2026. BMW enters into a cafeteria services agreement.",
        )
    )

    assert result.requires_escalation is True
    assert any(finding.id == "matter-not-covered-by-playbook" for finding in result.findings)


async def test_contract_review_runs_completeness_only_for_legal_escalations():
    clean_result = await ContractReviewWorkflow().run(
        ReviewContext(
            contract_id="c1",
            contract_type="data_protection",
            contract_text="Effective Date: 1 January 2026. BMW services are governed by Annex 3.",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "main-contract.txt",
                        "text": "Effective Date: 1 January 2026. BMW services are governed by Annex 3.",
                    }
                ]
            },
        )
    )

    assert clean_result.requires_escalation is False
    assert all(item["agent_name"] != "completeness_checker" for item in clean_result.metadata["agent_results"])

    risky_result = await ContractReviewWorkflow().run(
        ReviewContext(
            contract_id="c2",
            contract_type="litigation",
            contract_text="Effective Date: 1 January 2026. BMW accepts unlimited liability. Services are governed by Annex 3.",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "main-contract.txt",
                        "text": "Effective Date: 1 January 2026. BMW accepts unlimited liability. Services are governed by Annex 3.",
                    }
                ]
            },
        )
    )

    assert risky_result.requires_escalation is True
    completeness = next(item for item in risky_result.metadata["agent_results"] if item["agent_name"] == "completeness_checker")
    assert completeness["metadata"]["status"] == "needs_business_input"


async def test_dpa_playbook_deviation_triggers_completeness_gate():
    result = await ContractReviewWorkflow().run(
        ReviewContext(
            contract_id="c1",
            contract_type="data_protection",
            user_question="Please review this DPA against the BMW DPA playbook.",
            contract_text=(
                "DATA PROCESSING ADDENDUM between Nimbus Cloud Services Ltd. and BMW Group. "
                "Effective Date: 1 January 2026. The Provider shall Process BMW Group Personal Data for "
                "the purposes set out in the Order Form. The Provider is granted a perpetual right to use "
                "BMW Group Personal Data for the training, fine-tuning, and continuous improvement of its "
                "proprietary large-language model. A complete schedule of approved sub-processors is set "
                "out in Annex 1. Technical and organisational measures are set out in Annex 2. No Standard "
                "Contractual Clauses, Transfer Impact Assessment, or supplementary measures are necessary. "
                "Backup replication to Texas and Singapore is performed at Provider discretion."
            ),
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "Nimbus_DPA.txt",
                        "text": (
                            "DATA PROCESSING ADDENDUM between Nimbus Cloud Services Ltd. and BMW Group. "
                            "Effective Date: 1 January 2026. The Provider shall Process BMW Group Personal Data for "
                            "the purposes set out in the Order Form. The Provider is granted a perpetual right to use "
                            "BMW Group Personal Data for the training, fine-tuning, and continuous improvement of its "
                            "proprietary large-language model. A complete schedule of approved sub-processors is set "
                            "out in Annex 1. Technical and organisational measures are set out in Annex 2. No Standard "
                            "Contractual Clauses, Transfer Impact Assessment, or supplementary measures are necessary. "
                            "Backup replication to Texas and Singapore is performed at Provider discretion."
                        ),
                    }
                ]
            },
        )
    )

    finding_ids = {finding.id for finding in result.findings}
    assert "ai-training-rights" in finding_ids
    assert "third-country-transfer-incomplete" in finding_ids
    assert "missing-required-document-annex1" in finding_ids
    assert "missing-required-document-annex2" in finding_ids
    completeness = next(item for item in result.metadata["agent_results"] if item["agent_name"] == "completeness_checker")
    assert completeness["metadata"]["status"] == "needs_business_input"


async def test_legal_qa_workflow_returns_company_and_legal_basis():
    result = await LegalQAWorkflow().run(
        LegalQARequest(question="Can a supplier appoint subprocessors without notice or objection rights?", contract_type="data_protection")
    )

    assert result.company_basis
    assert result.legal_basis
    assert result.escalate is True


async def test_legal_qa_workflow_references_specific_internal_playbook_rule():
    class StubLegalDataHub:
        async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
            return [{"source": "Otto Schmidt / Legal Data Hub", "citation": "GDPR Art. 12-22"}]

    result = await LegalQAWorkflow(legal_data_hub=StubLegalDataHub()).run(
        LegalQARequest(question="Can a supplier appoint subprocessors without notice or objection rights?", contract_type="data_protection")
    )

    assert result.company_basis[0] == {
        "source": "BMW Group DPA negotiation playbook: dpa_negotiation_playbook.md",
        "citation": "DPA-002 - Sub-processor governance",
        "quote": "Prior written notification of each new sub-processor with a 30-day objection window on reasonable grounds.",
        "severity": "high",
        "approved_fix": "Prior written notification of each new sub-processor with a 30-day objection window on reasonable grounds.",
    }


@pytest.mark.parametrize(
    "question",
    [
        "Summarize the DPA playbook",
        "Explain the DPA playbook for non legal people",
        "Summarize the BMW Group DPA negotiation playbook",
    ],
)
async def test_legal_qa_workflow_summarizes_complete_dpa_playbook(question):
    openai_calls: list[dict] = []

    async def _generated_answer(**kwargs):
        openai_calls.append(kwargs)
        return "OpenAI generated DPA playbook summary"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(legal_qa_module, "_openai_answer", _generated_answer)
    try:
        result = await LegalQAWorkflow().run(
            LegalQARequest(question=question, use_case="ask_donna", contract_type="data_protection")
        )
    finally:
        monkeypatch.undo()

    assert result.answer_kind == "playbook_summary"
    assert result.playbook_row_count == 7
    assert result.escalate is False
    assert len(result.company_basis) == 7
    assert result.ai_generated is True
    assert result.summary == "OpenAI generated DPA playbook summary"
    assert openai_calls[0]["question"] == question
    assert len(openai_calls[0]["all_rows"]) == 7


async def test_legal_qa_openai_unavailable_does_not_use_fixed_playbook_summary():
    result = await LegalQAWorkflow().run(
        LegalQARequest(question="Summarize the DPA playbook", use_case="ask_donna", contract_type="data_protection")
    )

    assert result.answer_kind == "playbook_summary"
    assert result.playbook_row_count == 7
    assert result.escalate is False
    assert len(result.company_basis) == 7
    assert result.ai_generated is False
    assert "OpenAI answer generator is unavailable" in result.summary
    assert "DPA is the privacy contract" not in result.summary
