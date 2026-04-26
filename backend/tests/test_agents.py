from app.agents.base import ReviewContext
from app.agents.completeness_checker import CompletenessCheckerAgent
from app.agents.contract_understanding import ContractUnderstandingAgent
from app.agents import playbook_checker
from app.agents.playbook_checker import PlaybookCheckerAgent, PlaybookJudgeDeviation, PlaybookJudgeResult


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


async def test_playbook_checker_escalates_ai_training_and_transfer_safeguard_deviations():
    result = await PlaybookCheckerAgent().run(
        ReviewContext(
            contract_id="c1",
            contract_type="data_protection",
            contract_text=(
                "Effective Date: 1 January 2026. BMW Personal Data may be used for the training, "
                "fine-tuning, and continuous improvement of the Provider's proprietary large-language model. "
                "No Standard Contractual Clauses, Transfer Impact Assessment, or supplementary measures are "
                "necessary. Backup replication to Texas and Singapore is performed at Provider discretion."
            ),
        )
    )

    assert result.requires_escalation is True
    finding_ids = {finding.id for finding in result.findings}
    assert "ai-training-rights" in finding_ids
    assert "third-country-transfer-incomplete" in finding_ids


async def test_playbook_checker_uses_structured_llm_judge(monkeypatch):
    async def _fake_judge(_context):
        return PlaybookJudgeResult(
            domain="data_protection",
            summary="LLM judge found a DPA playbook deviation.",
            confidence=0.93,
            findings=[
                PlaybookJudgeDeviation(
                    rule_id="DPA-004",
                    title="Own-purpose AI training conflicts with BMW instructions",
                    description="The clause permits supplier model training on BMW Personal Data.",
                    severity="blocker",
                    requires_escalation=True,
                    clause_text="Provider may train its proprietary model on BMW Personal Data.",
                    approved_fix="Remove model training unless separately approved by BMW.",
                    rationale="DPA-004 treats indefinite retention for model training or product analytics as a red line.",
                    confidence=0.95,
                )
            ],
        )

    monkeypatch.setattr(playbook_checker, "_openai_playbook_judge", _fake_judge)

    result = await PlaybookCheckerAgent().run(
        ReviewContext(
            contract_id="c1",
            contract_type="data_protection",
            contract_text="Provider may train its proprietary model on BMW Personal Data.",
        )
    )

    assert result.requires_escalation is True
    assert result.metadata["playbook_judge_source"] == "openai_structured_judge"
    finding = next(finding for finding in result.findings if finding.id.startswith("playbook-deviation-dpa-004"))
    assert finding.severity.value == "blocker"
    assert finding.ruling is not None
    assert finding.ruling.citation == "DPA-004 - Data deletion and return at termination"


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


async def test_completeness_checker_flags_missing_agb_reference():
    result = await CompletenessCheckerAgent().run(
        ReviewContext(
            contract_id="c1",
            contract_text="",
            metadata={
                "uploaded_documents": [
                    {
                        "filename": "supplier-order.txt",
                        "text": "This order is subject to the Provider AGB and the applicable Order Form.",
                    }
                ]
            },
        )
    )

    labels = [item["label"] for item in result.metadata["missing_items"]]
    assert result.metadata["status"] == "needs_business_input"
    assert "AGB" in labels
    assert "Order Form" in labels
