from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.base import Agent, AgentResult, Evidence, Finding, ReviewContext, RulingReference, Severity, Suggestion
from app.agents.trigger_utils import missing_term_trigger, sentence_trigger_for_phrase


class PlaybookCheckerAgent(Agent):
    name = "playbook_checker"

    async def run(self, context: ReviewContext) -> AgentResult:
        findings: list[Finding] = []
        suggestions: list[Suggestion] = []
        text = context.contract_text.lower()
        uploaded_playbook_evidence = _uploaded_playbook_evidence(context.playbook_documents)
        dp_001 = _playbook_rule("data_protection", "DP-001")
        dp_002 = _playbook_rule("data_protection", "DP-002")
        lt_003 = _playbook_rule("litigation", "LT-003")

        if "bmw" not in text:
            ruling = _ruling_reference("BMW mock playbook", "data_protection", dp_001)
            trigger = missing_term_trigger(context.contract_text, "BMW contracting entity is missing from the contract.")
            findings.append(
                Finding(
                    id="missing-bmw-party",
                    title="BMW party reference is missing",
                    description="BMW playbook requires the BMW contracting entity to be explicitly identified.",
                    severity=Severity.HIGH,
                    clause_reference=trigger.text,
                    trigger=trigger,
                    ruling=ruling,
                    evidence=[_evidence_from_ruling(ruling)]
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
            ruling = _ruling_reference("BMW mock playbook", "litigation", lt_003)
            trigger = sentence_trigger_for_phrase(context.contract_text, "unlimited liability")
            findings.append(
                Finding(
                    id="unlimited-liability",
                    title="Unlimited liability exceeds BMW default",
                    description="The draft appears to accept unlimited liability, which exceeds the mock BMW playbook default.",
                    severity=Severity.BLOCKER,
                    clause_reference=trigger.text if trigger else None,
                    trigger=trigger,
                    ruling=ruling,
                    evidence=[_evidence_from_ruling(ruling)]
                    + uploaded_playbook_evidence,
                    requires_escalation=True,
                )
            )
            suggestions.append(
                Suggestion(
                    finding_id="unlimited-liability",
                    proposed_text="Replace unlimited liability with the BMW-approved liability position or route the liability cap to legal for approval.",
                    rationale="BMW Litigation Rule LT-003 requires legal escalation for unlimited liability.",
                )
            )

        if context.playbook_documents and "subprocessor" not in text and "personal data" in text:
            ruling = _ruling_reference("BMW mock playbook", "data_protection", dp_002)
            trigger = sentence_trigger_for_phrase(context.contract_text, "personal data")
            findings.append(
                Finding(
                    id="missing-subprocessor-list",
                    title="Subprocessor position is missing",
                    description="Uploaded company playbook materials were available and the contract does not state whether subprocessors are used.",
                    severity=Severity.MEDIUM,
                    clause_reference=trigger.text if trigger else None,
                    trigger=trigger,
                    ruling=ruling,
                    evidence=uploaded_playbook_evidence
                    or [
                        _evidence_from_ruling(ruling)
                    ],
                    requires_escalation=False,
                )
            )
            suggestions.append(
                Suggestion(
                    finding_id="missing-subprocessor-list",
                    proposed_text="State whether subprocessors are used and attach the approved subprocessor list if applicable.",
                    rationale="BMW Data Protection Rule DP-002 requires either a subprocessor list or an express statement that none are used.",
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


def _playbook_rule(scope: str, rule_id: str) -> dict[str, Any]:
    file_name = "bmw_data_protection.json" if scope == "data_protection" else "bmw_litigation.json"
    path = Path(__file__).resolve().parents[3] / "data" / "playbook" / file_name
    if not path.exists():
        return {"id": rule_id, "title": rule_id, "default": "Playbook rule unavailable."}

    playbook = json.loads(path.read_text(encoding="utf-8"))
    for rule in playbook.get("rules", []):
        if rule.get("id") == rule_id:
            return rule
    return {"id": rule_id, "title": rule_id, "default": "Playbook rule unavailable."}


def _ruling_reference(source: str, scope: str, rule: dict[str, Any]) -> RulingReference:
    return RulingReference(
        source=f"{source}: {scope}",
        citation=f"{rule.get('id', 'unknown')} - {rule.get('title', 'Untitled rule')}",
        quote=str(rule.get("default") or ""),
    )


def _evidence_from_ruling(ruling: RulingReference) -> Evidence:
    return Evidence(
        source=ruling.source,
        citation=ruling.citation,
        quote=ruling.quote,
        url=ruling.url,
    )
