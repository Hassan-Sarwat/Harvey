import pytest

from app.agents.base import ReviewContext
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
    assert result.metadata["agent_count"] == 3


async def test_legal_qa_workflow_returns_company_and_legal_basis():
    result = await LegalQAWorkflow().run(
        LegalQARequest(question="Can a supplier waive GDPR data subject rights?", contract_type="data_protection")
    )

    assert result.company_basis
    assert result.legal_basis
    assert result.escalate is True


async def test_legal_qa_workflow_references_specific_internal_playbook_rule():
    class StubLegalDataHub:
        async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
            return [{"source": "Otto Schmidt / Legal Data Hub", "citation": "GDPR Art. 12-22"}]

    result = await LegalQAWorkflow(legal_data_hub=StubLegalDataHub()).run(
        LegalQARequest(question="Can a supplier waive GDPR data subject rights?", contract_type="data_protection")
    )

    assert result.company_basis[0] == {
        "source": "BMW Group DPA negotiation playbook: bmw_group_dpa_negotiation_playbook.csv",
        "citation": "DPA-003 - Data subject rights assistance",
        "quote": "Processor must promptly notify BMW Group of requests and assist BMW Group without responding directly unless instructed or legally required.",
        "severity": "high",
        "approved_fix": "Processor shall promptly notify BMW Group and provide reasonable assistance with data subject requests without separate charge unless BMW Group approves an exceptional fee.",
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
    assert result.playbook_row_count == 8
    assert result.escalate is False
    assert len(result.company_basis) == 8
    assert result.ai_generated is True
    assert result.summary == "OpenAI generated DPA playbook summary"
    assert openai_calls[0]["question"] == question
    assert len(openai_calls[0]["all_rows"]) == 8


async def test_legal_qa_openai_unavailable_does_not_use_fixed_playbook_summary():
    result = await LegalQAWorkflow().run(
        LegalQARequest(question="Summarize the DPA playbook", use_case="ask_donna", contract_type="data_protection")
    )

    assert result.answer_kind == "playbook_summary"
    assert result.playbook_row_count == 8
    assert result.escalate is False
    assert len(result.company_basis) == 8
    assert result.ai_generated is False
    assert "OpenAI answer generator is unavailable" in result.summary
    assert "DPA is the privacy contract" not in result.summary
