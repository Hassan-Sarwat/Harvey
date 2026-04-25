from app.agents.base import ReviewContext
from app.workflows.legal_qa import LegalQARequest, LegalQAWorkflow
from app.workflows.review_contract import ContractReviewWorkflow


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
