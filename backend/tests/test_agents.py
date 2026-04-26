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
            contract_text="The technical measures are set out in Attachment 8.",
            user_question="Please escalate this risky DPA.",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "Nimbus_DPA_Test_Contract.pdf",
                        "text": "The technical measures are set out in Attachment 8.",
                    },
                    {"filename": "Attachment_2_Subprocessors.pdf", "text": "Attachment 2 - Subprocessors"},
                ]
            },
        )
    )

    assert result.requires_escalation is False
    assert result.metadata["status"] == "needs_business_input"
    assert result.findings[0].id == "missing-required-document-annex8"
    assert "Attachment 8" in result.metadata["missing_items"][0]["label"]


async def test_completeness_checker_matches_referenced_attachment_by_heading():
    result = await CompletenessCheckerAgent().run(
        ReviewContext(
            contract_id="c1",
            contract_text="The technical measures are set out in Attachment 8.",
            user_question="Please escalate this risky DPA.",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "Nimbus_DPA_Test_Contract.pdf",
                        "text": "The technical measures are set out in Attachment 8.",
                    },
                    {"filename": "Security_Measures.pdf", "text": "Attachment 8 - Technical and Organisational Measures"},
                ]
            },
        )
    )

    assert result.findings == []
    assert result.metadata["status"] == "complete"
    assert result.metadata["found_documents"][0]["matched_filename"] == "Security_Measures.pdf"
