from __future__ import annotations

from app.agents.base import Agent, AgentResult, Finding, ReviewContext, Severity
from app.agents.trigger_utils import missing_term_trigger
from app.services.contract_classifier import classify_contract_type


class ContractUnderstandingAgent(Agent):
    name = "contract_understanding"

    async def run(self, context: ReviewContext) -> AgentResult:
        findings: list[Finding] = []
        lower_text = context.contract_text.lower()

        if "effective date" not in lower_text and "commencement date" not in lower_text:
            trigger = missing_term_trigger(context.contract_text, "Effective date or commencement date is missing.")
            findings.append(
                Finding(
                    id="missing-effective-date",
                    title="Effective date is missing",
                    description="The contract text does not clearly identify an effective or commencement date.",
                    severity=Severity.MEDIUM,
                    clause_reference=trigger.text,
                    trigger=trigger,
                    requires_escalation=False,
                )
            )

        classification = await classify_contract_type(context.contract_text, provided_type=context.contract_type)
        inferred_type = classification.contract_type

        return AgentResult(
            agent_name=self.name,
            summary=f"Contract classified as {inferred_type}.",
            findings=findings,
            confidence=0.55,
            metadata={
                "inferred_contract_type": inferred_type,
                "classification_source": classification.source,
                "classification_confidence": classification.confidence,
                "classification_rationale": classification.rationale,
            },
            requires_escalation=any(f.requires_escalation for f in findings),
        )
