from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentResult, ContractTrigger, Evidence, Finding, ReviewContext, RulingReference, Severity, Suggestion
from app.agents.trigger_utils import missing_term_trigger, sentence_trigger_for_phrase
from app.core.config import get_settings
from app.services.model_context import is_model_access_error, openai_model_candidates
from app.services.playbook_repository import get_playbook_rule, load_playbook_markdown, load_playbook_rows, playbook_file_label, playbook_source_label


PLAYBOOK_SOURCE = "BMW playbook"
logger = logging.getLogger(__name__)


class PlaybookJudgeDeviation(BaseModel):
    rule_id: str
    title: str
    description: str
    severity: Literal["info", "low", "medium", "high", "blocker"]
    requires_escalation: bool
    clause_text: str
    approved_fix: str
    rationale: str
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class PlaybookJudgeResult(BaseModel):
    domain: Literal["data_protection", "litigation", "mixed", "general"]
    findings: list[PlaybookJudgeDeviation] = Field(default_factory=list)
    summary: str
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class PlaybookCheckerAgent(Agent):
    name = "playbook_checker"

    async def run(self, context: ReviewContext) -> AgentResult:
        uploaded_playbook_evidence = _uploaded_playbook_evidence(context.playbook_documents)
        fallback_result = await self._fallback_run(context, uploaded_playbook_evidence)

        judge_result = await _openai_playbook_judge(context)
        if judge_result is None:
            fallback_result.metadata["playbook_judge_source"] = "fallback_rules"
            return fallback_result

        llm_findings, llm_suggestions = _findings_from_judge_result(
            judge_result,
            context,
            uploaded_playbook_evidence,
        )
        findings = _dedupe_findings([*llm_findings, *fallback_result.findings])
        suggestions = _dedupe_suggestions([*llm_suggestions, *fallback_result.suggestions], findings)
        return AgentResult(
            agent_name=self.name,
            summary=judge_result.summary or "LLM judge compared draft clauses against the BMW playbook.",
            findings=findings,
            suggestions=suggestions,
            confidence=min(judge_result.confidence, fallback_result.confidence or judge_result.confidence),
            requires_escalation=any(f.requires_escalation for f in findings),
            metadata={
                **fallback_result.metadata,
                "playbook_judge_source": "openai_structured_judge",
                "llm_judge_domain": judge_result.domain,
                "llm_judge_finding_count": len(llm_findings),
                "fallback_finding_count": len(fallback_result.findings),
            },
        )

    async def _fallback_run(
        self,
        context: ReviewContext,
        uploaded_playbook_evidence: list[Evidence] | None = None,
    ) -> AgentResult:
        findings: list[Finding] = []
        suggestions: list[Suggestion] = []
        text = context.contract_text.lower()
        uploaded_playbook_evidence = uploaded_playbook_evidence or _uploaded_playbook_evidence(context.playbook_documents)
        dp_001 = get_playbook_rule("data_protection", "DP-001")
        dp_002 = get_playbook_rule("data_protection", "DPA-002")
        dp_003 = get_playbook_rule("data_protection", "DPA-003")
        dp_004 = get_playbook_rule("data_protection", "DPA-004")
        dp_005 = get_playbook_rule("data_protection", "DPA-007")
        dp_006 = get_playbook_rule("data_protection", "DPA-001")
        dp_007 = get_playbook_rule("data_protection", "DPA-006")
        dp_008 = get_playbook_rule("data_protection", "DPA-003")
        dp_009 = get_playbook_rule("data_protection", "DPA-004")
        dp_011 = get_playbook_rule("data_protection", "DPA-004")
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

        if (
            "ai models" in text
            or "model training" in text
            or "synthetic-data generators" in text
            or "large-language model" in text
            or ("training" in text and "fine-tuning" in text and "personal data" in text)
            or ("embeddings" in text and "weights" in text and "personal data" in text)
        ):
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
                phrase=_first_present_phrase(
                    text,
                    [
                        "large-language model",
                        "training, fine-tuning",
                        "embeddings, weights",
                        "ai models",
                        "model training",
                        "synthetic-data generators",
                    ],
                ),
                severity=Severity.HIGH,
                requires_escalation=True,
                proposed_text=str(dp_011.get("approved_fix") or "Remove AI training rights unless separately approved by BMW."),
            )

        if (
            "standard contractual clauses" in text
            and ("not necessary" in text or "no standard contractual clauses" in text or "shall be entered into" in text)
        ) or (
            ("texas" in text or "singapore" in text or "international waters" in text or "outside the territorial jurisdiction" in text)
            and ("personal data" in text or "processing infrastructure" in text or "backup replication" in text)
        ):
            _add_rule_finding(
                findings,
                suggestions,
                context,
                uploaded_playbook_evidence,
                scope="data_protection",
                rule=dp_007,
                finding_id="third-country-transfer-incomplete",
                title="Third-country safeguards are rejected or incomplete",
                description="The draft treats offshore or third-country processing as outside GDPR safeguards and rejects SCCs, transfer assessment, or supplementary measures.",
                phrase=_first_present_phrase(
                    text,
                    [
                        "no standard contractual clauses",
                        "standard contractual clauses",
                        "transfer impact assessment",
                        "international waters",
                        "backup replication",
                        "texas",
                        "singapore",
                    ],
                ),
                severity=Severity.BLOCKER,
                requires_escalation=True,
                proposed_text=str(dp_007.get("approved_fix") or "List and approve all third-country access before any transfer or remote access."),
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
                "playbook_files": [playbook_file_label("data_protection"), playbook_file_label("litigation")],
            },
        )


async def _openai_playbook_judge(context: ReviewContext) -> PlaybookJudgeResult | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    if settings.openai_api_key == "test-key":
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package is not installed; using playbook fallback rules")
        return None

    rows = _scoped_playbook_rows(context)
    if not rows:
        return None
    playbook_markdown = load_playbook_markdown("data_protection") if _judge_includes_domain(context, "data_protection") else ""

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        last_error: Exception | None = None
        for model in openai_model_candidates(settings):
            try:
                response = await asyncio.wait_for(
                    client.responses.create(
                        model=model,
                        reasoning={"effort": settings.openai_reasoning_effort or "low"},
                        input=[
                            {
                                "role": "system",
                                "content": (
                                    "You are Harvey's BMW playbook clause judge. Compare the submitted contract clauses against "
                                    "the supplied BMW playbook rows. Report only material deviations from preferred, fallback, "
                                    "or red-line positions. Use the playbook severity unless the clause is clearly less serious. "
                                    "Treat red-line language, escalation triggers, AI/model training on BMW personal data, "
                                    "third-country transfers without SCC/TIA safeguards, unlimited liability, and matters outside "
                                    "the active playbooks as escalation-worthy. Return JSON only."
                                ),
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "contract_type": context.contract_type or "unknown",
                                        "playbook_rows": rows,
                                        "full_relevant_playbook_context": playbook_markdown or _format_rows_as_full_context(rows),
                                        "contract_text": _contract_excerpt(context.contract_text),
                                        "required_behavior": (
                                            "Read the contract clause by clause. For each clause that conflicts with the BMW "
                                            "playbook, return the exact clause text, the matched playbook rule id, why it conflicts, "
                                            "whether Legal escalation is required, and the approved BMW fix. Do not report compliant "
                                            "clauses. The full relevant playbook context is authoritative and must be considered "
                                            "for every clause judgment."
                                        ),
                                    },
                                    ensure_ascii=True,
                                ),
                            },
                        ],
                        text={
                            "format": {
                                "type": "json_schema",
                                "name": "bmw_playbook_clause_judge",
                                "strict": True,
                                "schema": _judge_json_schema(),
                            }
                        },
                        max_output_tokens=2600,
                    ),
                    timeout=max(settings.legal_data_hub_timeout, 60.0),
                )
                output_text = getattr(response, "output_text", "") or ""
                return PlaybookJudgeResult.model_validate(json.loads(output_text))
            except Exception as exc:
                last_error = exc
                if not is_model_access_error(exc):
                    raise
                logger.warning("OpenAI model %s unavailable for playbook judge; trying fallback model", model)
        if last_error:
            raise last_error
        return None
    except Exception as exc:
        logger.warning("OpenAI playbook judge failed; using fallback rules: %s", exc)
        return None


def _scoped_playbook_rows(context: ReviewContext) -> list[dict[str, str]]:
    domain = context.contract_type or ""
    domains = ["data_protection"] if domain == "data_protection" else ["litigation"] if domain == "litigation" else ["data_protection", "litigation"]
    rows: list[dict[str, str]] = []
    for item in domains:
        for row in load_playbook_rows(item):
            rows.append(
                {
                    "domain": item,
                    "id": str(row.get("id") or ""),
                    "title": str(row.get("title") or ""),
                    "severity": str(row.get("severity") or ""),
                    "default": str(row.get("default") or ""),
                    "preferred_position": str(row.get("preferred_position") or ""),
                    "fallback_1": str(row.get("fallback_1") or ""),
                    "fallback_2": str(row.get("fallback_2") or ""),
                    "red_line": str(row.get("red_line") or ""),
                    "escalation_trigger": str(row.get("escalation_trigger") or ""),
                    "legal_basis": str(row.get("legal_basis") or ""),
                    "approved_fix": str(row.get("approved_fix") or ""),
                }
            )
    return rows


def _judge_includes_domain(context: ReviewContext, domain: str) -> bool:
    if context.contract_type == domain:
        return True
    return context.contract_type not in {"data_protection", "litigation"}


def _format_rows_as_full_context(rows: list[dict[str, str]]) -> str:
    parts = []
    for row in rows:
        parts.append(
            "\n".join(
                [
                    f"{row.get('id')} - {row.get('title')} [{row.get('severity')}]",
                    f"Standard: {row.get('preferred_position') or row.get('default')}",
                    f"Fall-back 1: {row.get('fallback_1')}",
                    f"Fall-back 2: {row.get('fallback_2')}",
                    f"Red line: {row.get('red_line')}",
                    f"Escalation trigger: {row.get('escalation_trigger')}",
                    f"Approved fix: {row.get('approved_fix')}",
                ]
            )
        )
    return "\n\n".join(parts)


def _judge_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "domain": {"type": "string", "enum": ["data_protection", "litigation", "mixed", "general"]},
            "summary": {"type": "string"},
            "confidence": {"type": "number"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "rule_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "severity": {"type": "string", "enum": ["info", "low", "medium", "high", "blocker"]},
                        "requires_escalation": {"type": "boolean"},
                        "clause_text": {"type": "string"},
                        "approved_fix": {"type": "string"},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "rule_id",
                        "title",
                        "description",
                        "severity",
                        "requires_escalation",
                        "clause_text",
                        "approved_fix",
                        "rationale",
                        "confidence",
                    ],
                },
            },
        },
        "required": ["domain", "summary", "confidence", "findings"],
    }


def _findings_from_judge_result(
    judge_result: PlaybookJudgeResult,
    context: ReviewContext,
    uploaded_playbook_evidence: list[Evidence],
) -> tuple[list[Finding], list[Suggestion]]:
    findings: list[Finding] = []
    suggestions: list[Suggestion] = []
    for index, deviation in enumerate(judge_result.findings, start=1):
        scope = _scope_for_rule_id(deviation.rule_id, judge_result.domain)
        rule = get_playbook_rule(scope, deviation.rule_id)
        ruling = _ruling_reference(PLAYBOOK_SOURCE, scope, rule)
        trigger = _trigger_for_clause(context.contract_text, deviation.clause_text)
        finding_id = f"playbook-deviation-{_slugify(deviation.rule_id or str(index))}"
        if len(judge_result.findings) > 1:
            finding_id = f"{finding_id}-{_slugify(deviation.title)[:36]}"
        findings.append(
            Finding(
                id=finding_id,
                title=deviation.title,
                description=deviation.description,
                severity=Severity(deviation.severity),
                clause_reference=trigger.text if trigger else deviation.clause_text,
                trigger=trigger,
                ruling=ruling,
                evidence=[
                    Evidence(
                        source="OpenAI playbook clause judge",
                        citation=f"{deviation.rule_id} deviation rationale",
                        quote=deviation.rationale,
                    ),
                    _evidence_from_ruling(ruling),
                    *uploaded_playbook_evidence,
                ],
                requires_escalation=deviation.requires_escalation,
            )
        )
        suggestions.append(
            Suggestion(
                finding_id=finding_id,
                proposed_text=deviation.approved_fix or str(rule.get("approved_fix") or ""),
                rationale=deviation.rationale or f"BMW playbook rule {deviation.rule_id} sets the approved position.",
            )
        )
    return findings, suggestions


def _scope_for_rule_id(rule_id: str, fallback_domain: str) -> str:
    normalized = rule_id.upper()
    if normalized.startswith("LT-"):
        return "litigation"
    if normalized.startswith(("DPA-", "DP-")):
        return "data_protection"
    if fallback_domain == "litigation":
        return "litigation"
    return "data_protection"


def _trigger_for_clause(contract_text: str, clause_text: str) -> ContractTrigger | None:
    compact_clause = _compact(clause_text)
    if not compact_clause:
        return None
    compact_contract = _compact(contract_text)
    compact_index = compact_contract.lower().find(compact_clause.lower())
    if compact_index >= 0:
        original_start = _approximate_original_offset(contract_text, compact_index)
        original_end = min(len(contract_text), original_start + len(compact_clause))
        return ContractTrigger(text=compact_clause, start=original_start, end=original_end)
    key_phrase = " ".join(compact_clause.split()[:8])
    return sentence_trigger_for_phrase(contract_text, key_phrase) or missing_term_trigger(contract_text, compact_clause[:180])


def _approximate_original_offset(text: str, compact_index: int) -> int:
    compact_seen = 0
    in_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space:
                if compact_seen >= compact_index:
                    return index
                compact_seen += 1
            in_space = True
            continue
        in_space = False
        if compact_seen >= compact_index:
            return index
        compact_seen += 1
    return 0


def _contract_excerpt(contract_text: str) -> str:
    compact = _compact(contract_text)
    if len(compact) <= 16000:
        return compact
    return f"{compact[:8000]}\n\n[...middle omitted for token budget...]\n\n{compact[-8000:]}"


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    deduped: list[Finding] = []
    seen_ids: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for finding in findings:
        pair = (_compact(finding.clause_reference or ""), finding.ruling.citation if finding.ruling else finding.id)
        if finding.id in seen_ids or pair in seen_pairs:
            continue
        seen_ids.add(finding.id)
        seen_pairs.add(pair)
        deduped.append(finding)
    return deduped


def _dedupe_suggestions(suggestions: list[Suggestion], findings: list[Finding]) -> list[Suggestion]:
    finding_ids = {finding.id for finding in findings}
    deduped: list[Suggestion] = []
    seen: set[tuple[str, str]] = set()
    for suggestion in suggestions:
        if suggestion.finding_id not in finding_ids:
            continue
        key = (suggestion.finding_id, suggestion.proposed_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(suggestion)
    return deduped


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


def _first_present_phrase(text: str, phrases: list[str]) -> str:
    for phrase in phrases:
        if phrase.lower() in text:
            return phrase
    return phrases[0]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "finding"


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
