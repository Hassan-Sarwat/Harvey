from __future__ import annotations

from app.agents.base import Agent, AgentResult, Finding, ReviewContext, Severity
from app.agents.trigger_utils import missing_term_trigger


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

        inferred_type = context.contract_type or (
            "data_protection" if "personal data" in lower_text or "gdpr" in lower_text else "litigation"
        )

        return AgentResult(
            agent_name=self.name,
            summary=f"Contract classified as {inferred_type}.",
            findings=findings,
            confidence=0.55,
            metadata={"inferred_contract_type": inferred_type},
            requires_escalation=any(f.requires_escalation for f in findings),
        )
