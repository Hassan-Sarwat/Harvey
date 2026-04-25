from app.agents.base import ReviewContext
from app.agents.contract_understanding import ContractUnderstandingAgent
from app.agents.playbook_checker import PlaybookCheckerAgent


async def test_contract_understanding_flags_missing_effective_date():
    result = await ContractUnderstandingAgent().run(
        ReviewContext(contract_id="c1", contract_text="BMW processes personal data under this DPA.")
    )

    assert result.findings
    assert result.metadata["inferred_contract_type"] == "data_protection"


async def test_playbook_checker_escalates_missing_bmw_party():
    result = await PlaybookCheckerAgent().run(
        ReviewContext(contract_id="c1", contract_text="Supplier accepts unlimited liability.")
    )

    assert result.requires_escalation is True
    assert {finding.id for finding in result.findings} >= {"missing-bmw-party", "unlimited-liability"}
