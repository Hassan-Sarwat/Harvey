from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentResult, Evidence, Finding, ReviewContext, RulingReference, Severity, Suggestion
from app.agents.trigger_utils import sentence_trigger_for_phrase
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
        suggestions: list[Suggestion] = []
        lower_text = context.contract_text.lower()
        rights_waiver_phrase = _data_subject_rights_waiver_phrase(lower_text)
        if rights_waiver_phrase:
            ruling = _ruling_reference(evidence)
            trigger = sentence_trigger_for_phrase(context.contract_text, rights_waiver_phrase)
            findings.append(
                Finding(
                    id="illegal-data-subject-right-waiver",
                    title="Potentially unlawful data subject rights waiver",
                    description="The draft appears to waive all data subject rights and needs legal review.",
                    severity=Severity.BLOCKER,
                    clause_reference=trigger.text if trigger else None,
                    trigger=trigger,
                    ruling=ruling,
                    evidence=[
                        Evidence(
                            source=_evidence_source(item),
                            citation=item.get("citation", "GDPR evidence"),
                            quote=item.get("quote"),
                            url=item.get("url"),
                        )
                        for item in evidence[:2]
                    ],
                    requires_escalation=True,
                )
            )
            suggestions.append(
                Suggestion(
                    finding_id="illegal-data-subject-right-waiver",
                    proposed_text="Remove the waiver and preserve statutory GDPR data subject rights, including transparency, access, rectification, erasure, restriction, portability, and objection rights.",
                    rationale="The cited Legal Data Hub evidence identifies these rights as statutory rights that should not be waived in the draft.",
                )
            )

        return AgentResult(
            agent_name=self.name,
            summary="Checked draft against German legal evidence sources.",
            findings=findings,
            suggestions=suggestions,
            confidence=0.62 if evidence else 0.35,
            requires_escalation=any(f.requires_escalation for f in findings),
            metadata={"evidence_count": len(evidence)},
        )


def _ruling_reference(evidence: list[dict[str, Any]]) -> RulingReference | None:
    if not evidence:
        return None

    item = evidence[0]
    return RulingReference(
        source=_evidence_source(item),
        citation=str(item.get("citation") or "Legal Data Hub evidence"),
        quote=str(item.get("quote") or "Legal evidence returned without quoted text."),
        url=item.get("url"),
    )


def _evidence_source(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "Legal Data Hub fallback")
    if source == "Legal Data Hub fallback":
        return "Otto Schmidt / Legal Data Hub fallback"
    return source


def _data_subject_rights_waiver_phrase(text: str) -> str | None:
    for phrase in ("waives all data subject rights", "waive all data subject rights"):
        if phrase in text:
            return phrase
    return None
