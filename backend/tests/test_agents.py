from app.agents.base import ReviewContext
from app.agents.completeness_checker import CompletenessCheckerAgent
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


async def test_playbook_checker_records_trigger_and_exact_playbook_ruling():
    result = await PlaybookCheckerAgent().run(
        ReviewContext(contract_id="c1", contract_text="Supplier accepts unlimited liability.")
    )

    liability = next(finding for finding in result.findings if finding.id == "unlimited-liability")
    assert liability.trigger is not None
    assert liability.trigger.text == "Supplier accepts unlimited liability."
    assert liability.trigger.start == 0
    assert liability.ruling is not None
    assert liability.ruling.citation == "LT-003 - Unlimited liability escalation"
    assert liability.ruling.quote == "Unlimited liability must be escalated to legal."


async def test_completeness_checker_flags_missing_referenced_attachment():
    result = await CompletenessCheckerAgent().run(
        ReviewContext(
            contract_id="c1",
            contract_text="",
            user_question="Please escalate this to Legal.",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "main-contract.txt",
                        "text": "Effective Date: 1 January 2026. BMW services are governed by Attachment 8.",
                    }
                ]
            },
        )
    )

    assert result.requires_escalation is False
    assert result.metadata["status"] == "needs_business_input"
    assert any(finding.id == "missing-required-document-annex8" for finding in result.findings)


async def test_completeness_checker_matches_attachment_from_uploaded_heading():
    result = await CompletenessCheckerAgent().run(
        ReviewContext(
            contract_id="c1",
            contract_text="",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "main-contract.txt",
                        "text": "Effective Date: 1 January 2026. BMW services are governed by Annex 3.",
                    },
                    {
                        "filename": "service-levels.txt",
                        "text": "Annex 3 - Service Levels\nThe supplier shall meet the agreed service levels.",
                    },
                ]
            },
        )
    )

    assert result.metadata["status"] == "complete"
    assert not result.findings
