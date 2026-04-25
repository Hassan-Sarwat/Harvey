from __future__ import annotations

from app.agents.base import Agent, AgentResult, Evidence, Finding, ReviewContext, Severity, Suggestion


class PlaybookCheckerAgent(Agent):
    name = "playbook_checker"

    async def run(self, context: ReviewContext) -> AgentResult:
        findings: list[Finding] = []
        suggestions: list[Suggestion] = []
        text = context.contract_text.lower()
        uploaded_playbook_evidence = _uploaded_playbook_evidence(context.playbook_documents)

        if "bmw" not in text:
            findings.append(
                Finding(
                    id="missing-bmw-party",
                    title="BMW party reference is missing",
                    description="BMW playbook requires the BMW contracting entity to be explicitly identified.",
                    severity=Severity.HIGH,
                    evidence=[
                        Evidence(
                            source="BMW mock playbook",
                            citation="Data Protection Rule DP-001",
                            quote="Contracts must identify the BMW contracting entity.",
                        )
                    ]
                    + uploaded_playbook_evidence,
                    requires_escalation=True,
                )
            )
            suggestions.append(
                Suggestion(
                    finding_id="missing-bmw-party",
                    proposed_text="Add the applicable BMW contracting entity and registered address.",
                    rationale="Required for internal routing, accountability, and signature authority.",
                )
            )

        if "unlimited liability" in text:
            findings.append(
                Finding(
                    id="unlimited-liability",
                    title="Unlimited liability exceeds BMW default",
                    description="The draft appears to accept unlimited liability, which exceeds the mock BMW playbook default.",
                    severity=Severity.BLOCKER,
                    evidence=[
                        Evidence(
                            source="BMW mock playbook",
                            citation="Litigation Rule LT-003",
                            quote="Unlimited liability must be escalated to legal.",
                        )
                    ]
                    + uploaded_playbook_evidence,
                    requires_escalation=True,
                )
            )

        if context.playbook_documents and "subprocessor" not in text and "personal data" in text:
            findings.append(
                Finding(
                    id="missing-subprocessor-list",
                    title="Subprocessor position is missing",
                    description="Uploaded company playbook materials were available and the contract does not state whether subprocessors are used.",
                    severity=Severity.MEDIUM,
                    evidence=uploaded_playbook_evidence
                    or [
                        Evidence(
                            source="BMW mock playbook",
                            citation="Data Protection Rule DP-002",
                            quote="Processor must list subprocessors or state that none are used.",
                        )
                    ],
                    requires_escalation=False,
                )
            )

        return AgentResult(
            agent_name=self.name,
            summary="Checked draft against mock BMW playbook rules.",
            findings=findings,
            suggestions=suggestions,
            confidence=0.7,
            requires_escalation=any(f.requires_escalation for f in findings),
            metadata={
                "playbook_document_count": len(context.playbook_documents),
                "playbook_sources": [document.get("filename") for document in context.playbook_documents],
            },
        )


def _uploaded_playbook_evidence(documents: list[dict]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for document in documents[:3]:
        text = str(document.get("text") or document.get("text_preview") or "").strip()
        evidence.append(
            Evidence(
                source=f"Uploaded company playbook: {document.get('filename', 'document')}",
                citation="Uploaded playbook document",
                quote=text[:240] or None,
            )
        )
    return evidence
