from __future__ import annotations

from app.agents.base import Agent, AgentResult, Evidence, Finding, ReviewContext, Severity
from app.services.legal_data_hub import LegalDataHubClient


class LegalCheckerAgent(Agent):
    name = "legal_checker"

    def __init__(self, legal_data_hub: LegalDataHubClient | None = None) -> None:
        self.legal_data_hub = legal_data_hub or LegalDataHubClient()

    async def run(self, context: ReviewContext) -> AgentResult:
        evidence = await self.legal_data_hub.search_evidence(
            query=context.user_question or context.contract_text[:500],
            domain=context.contract_type or "general",
        )

        findings: list[Finding] = []
        lower_text = context.contract_text.lower()
        if "waives all data subject rights" in lower_text:
            findings.append(
                Finding(
                    id="illegal-data-subject-right-waiver",
                    title="Potentially unlawful data subject rights waiver",
                    description="The draft appears to waive all data subject rights and needs legal review.",
                    severity=Severity.BLOCKER,
                    evidence=[
                        Evidence(
                            source=item.get("source", "Legal Data Hub fallback"),
                            citation=item.get("citation", "GDPR evidence"),
                            quote=item.get("quote"),
                            url=item.get("url"),
                        )
                        for item in evidence[:2]
                    ],
                    requires_escalation=True,
                )
            )

        return AgentResult(
            agent_name=self.name,
            summary="Checked draft against German legal evidence sources.",
            findings=findings,
            confidence=0.62 if evidence else 0.35,
            requires_escalation=any(f.requires_escalation for f in findings),
            metadata={"evidence_count": len(evidence)},
        )
