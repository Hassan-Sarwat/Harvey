from __future__ import annotations

from typing import Any

from app.agents.base import Agent, AgentResult, Evidence, Finding, ReviewContext, RulingReference, Severity, Suggestion
from app.agents.trigger_utils import missing_term_trigger, sentence_trigger_for_phrase
from app.services.playbook_repository import get_playbook_rule, playbook_source_label


PLAYBOOK_SOURCE = "BMW playbook"


class PlaybookCheckerAgent(Agent):
    name = "playbook_checker"

    async def run(self, context: ReviewContext) -> AgentResult:
        findings: list[Finding] = []
        suggestions: list[Suggestion] = []
        text = context.contract_text.lower()
        uploaded_playbook_evidence = _uploaded_playbook_evidence(context.playbook_documents)
        dp_001 = get_playbook_rule("data_protection", "DP-001")
        dp_002 = get_playbook_rule("data_protection", "DPA-002")
        dp_003 = get_playbook_rule("data_protection", "DPA-003")
        dp_004 = get_playbook_rule("data_protection", "DPA-001")
        dp_005 = get_playbook_rule("data_protection", "DPA-005")
        dp_006 = get_playbook_rule("data_protection", "DPA-004")
        dp_007 = get_playbook_rule("data_protection", "DPA-007")
        dp_008 = get_playbook_rule("data_protection", "DPA-008")
        dp_009 = get_playbook_rule("data_protection", "DPA-006")
        dp_011 = get_playbook_rule("data_protection", "DPA-001")
        lt_002 = get_playbook_rule("litigation", "LT-002")
        lt_003 = get_playbook_rule("litigation", "LT-003")
        lt_004 = get_playbook_rule("litigation", "LT-004")
        lt_005 = get_playbook_rule("litigation", "LT-005")
        lt_007 = get_playbook_rule("litigation", "LT-007")
        lt_008 = get_playbook_rule("litigation", "LT-008")
        lt_009 = get_playbook_rule("litigation", "LT-009")
        lt_011 = get_playbook_rule("litigation", "LT-011")

        if "bmw" not in text:
            ruling = _ruling_reference(PLAYBOOK_SOURCE, "data_protection", dp_001)
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
            ruling = _ruling_reference(PLAYBOOK_SOURCE, "litigation", lt_003)
            trigger = sentence_trigger_for_phrase(context.contract_text, "unlimited liability")
            findings.append(
                Finding(
                    id="unlimited-liability",
                    title="Unlimited liability exceeds BMW default",
                    description="The draft appears to accept unlimited liability, which exceeds the BMW litigation playbook default.",
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
            ruling = _ruling_reference(PLAYBOOK_SOURCE, "data_protection", dp_002)
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

        if "waive all data subject rights" in text or "waives all data subject rights" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_003,
                finding_id="data-subject-rights-waiver-playbook",
                title="Data subject rights waiver violates BMW playbook",
                description="The draft tries to waive statutory data subject rights, which is a blocker under the BMW Datenschutz playbook.",
                phrase="waives all data subject rights" if "waives all data subject rights" in text else "waive all data subject rights",
                severity=Severity.BLOCKER,
                requires_escalation=True,
                proposed_text=str(dp_003.get("approved_fix") or "Remove the waiver and preserve statutory data subject rights."),
            )

        if "own product improvement" in text or ("analytics purposes" in text and "company personal data" in text):
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_004,
                finding_id="processor-purpose-drift",
                title="Processor own-purpose use conflicts with BMW instructions",
                description="The draft allows processor use of BMW personal data for product improvement, analytics, benchmarking, or similar own purposes.",
                phrase="own product improvement" if "own product improvement" in text else "analytics purposes",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(dp_004.get("approved_fix") or "Restrict processing to documented BMW instructions and remove own-purpose use."),
            )

        if "any subprocessor on general authorization" in text or "subprocessors at its discretion" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_002,
                finding_id="subprocessor-general-authorization",
                title="Subprocessor authorization is too broad",
                description="The draft gives broad subprocessor authorization without the BMW notice and objection controls required by the playbook.",
                phrase="any subprocessor on general authorization" if "any subprocessor on general authorization" in text else "subprocessors at its discretion",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(dp_002.get("approved_fix") or "Require a named subprocessor list and prior notice with objection rights."),
            )

        breach_notice_phrase = None
        if "as soon as reasonably practicable" in text and "breach" in text:
            breach_notice_phrase = "as soon as reasonably practicable"
        elif "72 hours" in text and "breach" in text:
            breach_notice_phrase = "72 hours"
        if breach_notice_phrase:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_006,
                finding_id="breach-notice-too-long",
                title="Breach notice exceeds BMW default",
                description="The draft uses a vague or delayed breach notice position instead of BMW's prompt processor notice default.",
                phrase=breach_notice_phrase,
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(dp_006.get("approved_fix") or "Require notice within 24 hours after awareness of a suspected or actual breach."),
            )

        if "commercially reasonable security measures" in text or "as it deems appropriate" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_005,
                finding_id="generic-security-measures",
                title="Security measures are too generic",
                description="The draft relies on generic commercially reasonable security language instead of concrete technical and organizational measures.",
                phrase="commercially reasonable security measures" if "commercially reasonable security measures" in text else "as it deems appropriate",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(dp_005.get("approved_fix") or "Attach concrete technical and organizational measures under GDPR Art. 32."),
            )

        if ("united states" in text or "india" in text) and ("to be agreed" in text or "remote access" in text):
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_007,
                finding_id="third-country-transfer-incomplete",
                title="Third-country safeguards are incomplete",
                description="The draft permits third-country access before SCCs, transfer assessment, and BMW approval are complete.",
                phrase="to be agreed" if "to be agreed" in text else "remote access",
                severity=Severity.BLOCKER,
                requires_escalation=True,
                proposed_text=str(dp_007.get("approved_fix") or "List and approve all third-country access before any transfer or remote access."),
            )

        if "will not permit onsite audits" in text or "security questionnaire once" in text or "once every three years" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_008,
                finding_id="audit-rights-too-limited",
                title="Audit rights are too limited",
                description="The draft limits BMW to questionnaire-only evidence and excludes meaningful audit rights.",
                phrase="will not permit onsite audits" if "will not permit onsite audits" in text else "security questionnaire once" if "security questionnaire once" in text else "once every three years",
                severity=Severity.MEDIUM,
                requires_escalation=False,
                proposed_text=str(dp_008.get("approved_fix") or "Require evidence access and proportionate audit rights."),
            )

        if "delete active production data within 180 days" in text or ("180 days" in text and "delete" in text):
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_009,
                finding_id="deletion-period-too-long",
                title="Deletion period exceeds BMW default",
                description="The draft allows active data retention for 180 days after termination, above the BMW 30-day default.",
                phrase="180 days",
                severity=Severity.MEDIUM,
                requires_escalation=False,
                proposed_text=str(dp_009.get("approved_fix") or "Require return or deletion within 30 days and backup purge within 90 days."),
            )

        if "ai models" in text or "model training" in text or "synthetic-data generators" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_011,
                finding_id="ai-training-rights",
                title="Supplier AI training rights need approval",
                description="The draft lets the supplier use BMW data or derived data for model improvement without a separate BMW approval path.",
                phrase="ai models" if "ai models" in text else "model training" if "model training" in text else "synthetic-data generators",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(dp_011.get("approved_fix") or "Remove AI training rights unless separately approved by BMW."),
            )

        if "may recommend and negotiate nuisance settlements" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_002,
                finding_id="settlement-authority-delegated",
                title="Settlement authority is delegated outside BMW Legal",
                description="The draft lets the service provider negotiate settlements and relies on business approval rather than BMW Legal authority.",
                phrase="may recommend and negotiate nuisance settlements",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(lt_002.get("approved_fix") or "Reserve all settlements and admissions for BMW Legal approval."),
            )

        if "paid preservation work order" in text or "routine deletion" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_004,
                finding_id="legal-hold-conditioned-on-payment",
                title="Legal hold preservation is not immediate",
                description="The draft allows ordinary deletion until a paid preservation work order is approved.",
                phrase="paid preservation work order" if "paid preservation work order" in text else "routine deletion",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(lt_004.get("approved_fix") or "Require immediate preservation and suspension of deletion after BMW legal hold notice."),
            )

        if "may nevertheless disclose investigation notes" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_005,
                finding_id="privilege-disclosure-risk",
                title="Privilege and investigation material disclosure risk",
                description="The draft permits disclosure of investigation notes and expert drafts without BMW Legal control.",
                phrase="may nevertheless disclose investigation notes",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(lt_005.get("approved_fix") or "Route privileged and investigation materials through BMW Legal approval."),
            )

        if "courts of dublin" in text or "rules agreed after a dispute arises" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_007,
                finding_id="forum-selection-risk",
                title="Forum clause deviates from BMW litigation default",
                description="The draft uses a non-BMW forum position and may block urgent relief.",
                phrase="courts of dublin" if "courts of dublin" in text else "rules agreed after a dispute arises",
                severity=Severity.MEDIUM,
                requires_escalation=False,
                proposed_text=str(lt_007.get("approved_fix") or "Use an approved German or neutral forum clause."),
            )

        if "expire six months" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_008,
                finding_id="short-limitation-period",
                title="Limitation period is too short",
                description="The draft applies a six-month limitation period even to high-risk claims.",
                phrase="expire six months",
                severity=Severity.MEDIUM,
                requires_escalation=True,
                proposed_text=str(lt_008.get("approved_fix") or "Preserve statutory limitation periods for high-risk and mandatory claims."),
            )

        if "bmw shall indemnify service provider" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_009,
                finding_id="broad-indemnity",
                title="Broad one-sided indemnity",
                description="The draft imposes a broad indemnity on BMW for claims, fines, sanctions, fees, and settlement amounts.",
                phrase="bmw shall indemnify service provider",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(lt_009.get("approved_fix") or "Limit indemnities to direct third-party claims caused by the indemnifying party's breach."),
            )

        if "may communicate with regulators" in text:
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="litigation",
                rule=lt_011,
                finding_id="unilateral-regulatory-communications",
                title="Supplier can make unilateral regulatory communications",
                description="The draft allows the supplier to contact regulators, claimants, courts, and opposing experts without BMW Legal approval.",
                phrase="may communicate with regulators",
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(lt_011.get("approved_fix") or "Require BMW Legal approval before voluntary communications or admissions."),
            )

        return AgentResult(
            agent_name=self.name,
            summary="Checked draft against the BMW playbook files in data/playbook.",
            findings=findings,
            suggestions=suggestions,
            confidence=0.7,
            requires_escalation=any(f.requires_escalation for f in findings),
            metadata={
                "playbook_document_count": len(context.playbook_documents),
                "playbook_sources": [playbook_source_label("data_protection"), playbook_source_label("litigation")]
                + [str(document.get("filename")) for document in context.playbook_documents],
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


def _add_rule_finding(
    findings: list[Finding],
    suggestions: list[Suggestion],
    context: ReviewContext,
    uploaded_playbook_evidence: list[Evidence],
    *,
    scope: str,
    rule: dict[str, Any],
    finding_id: str,
    title: str,
    description: str,
    phrase: str,
    severity: Severity,
    requires_escalation: bool,
    proposed_text: str,
) -> None:
    ruling = _ruling_reference(PLAYBOOK_SOURCE, scope, rule)
    trigger = sentence_trigger_for_phrase(context.contract_text, phrase)
    findings.append(
        Finding(
            id=finding_id,
            title=title,
            description=description,
            severity=severity,
            clause_reference=trigger.text if trigger else None,
            trigger=trigger,
            ruling=ruling,
            evidence=[_evidence_from_ruling(ruling)] + uploaded_playbook_evidence,
            requires_escalation=requires_escalation,
        )
    )
    suggestions.append(
        Suggestion(
            finding_id=finding_id,
            proposed_text=proposed_text,
            rationale=f"BMW playbook rule {rule.get('id', 'unknown')} sets this as the approved position.",
        )
    )


def _ruling_reference(source: str, scope: str, rule: dict[str, Any]) -> RulingReference:
    return RulingReference(
        source=f"{source}: {playbook_source_label(scope)}",
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
