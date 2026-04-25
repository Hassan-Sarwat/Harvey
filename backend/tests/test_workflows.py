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
