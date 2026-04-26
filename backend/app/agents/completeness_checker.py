from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import Agent, AgentResult, ContractTrigger, Evidence, Finding, ReviewContext, Severity, Suggestion

logger = logging.getLogger(__name__)


CompletenessCategory = Literal[
    "missing_documents",
    "missing_metadata",
    "missing_business_context",
    "unclear_input",
    "inconsistencies",
]


class ExpectedDocument(BaseModel):
    label: str
    normalized_label: str
    category: CompletenessCategory = "missing_documents"
    basis: str
    required: bool = True
    source_file: str | None = None
    source_quote: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class DocumentMatch(BaseModel):
    expected_label: str
    status: Literal["found", "missing", "ambiguous", "unreadable", "not_applicable"]
    matched_filename: str | None = None
    reason: str
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class MissingCompletenessItem(BaseModel):
    label: str
    category: CompletenessCategory = "missing_documents"
    severity: Literal["blocking", "warning", "info"] = "blocking"
    reason: str
    source_file: str | None = None
    source_quote: str | None = None
    user_action: str = "upload_file_or_explain_unavailable"
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class CompletenessCheck(BaseModel):
    can_submit_to_legal: bool
    status: Literal["complete", "needs_business_input"]
    expected_documents: list[ExpectedDocument] = Field(default_factory=list)
    found_documents: list[DocumentMatch] = Field(default_factory=list)
    missing_items: list[MissingCompletenessItem] = Field(default_factory=list)
    user_message: str


class CompletenessCheckerAgent(Agent):
    name = "completeness_checker"

    async def run(self, context: ReviewContext) -> AgentResult:
        uploaded_documents = _uploaded_documents(context)
        check = await _openai_completeness_check(context, uploaded_documents)
        source = "openai" if check is not None else "fallback_parser"
        if check is None:
            check = _fallback_completeness_check(context, uploaded_documents)

        findings = [_finding_from_missing_item(item) for item in check.missing_items]
        suggestions = [
            Suggestion(
                finding_id=finding.id,
                proposed_text="Upload the missing material to the ticket, or record a business explanation that it is unavailable before sending the package to Legal.",
                rationale="Legal should receive a complete escalation package or an auditable explanation for any missing item.",
            )
            for finding in findings
        ]
        blocking_count = sum(1 for item in check.missing_items if item.severity == "blocking")
        return AgentResult(
            agent_name=self.name,
            summary=(
                "Checked whether the ticket package contains the documents and business inputs "
                "expected before Legal escalation."
            ),
            findings=findings,
            suggestions=suggestions,
            confidence=min((item.confidence for item in check.missing_items), default=0.78),
            requires_escalation=False,
            metadata={
                "status": check.status,
                "can_submit_to_legal": check.can_submit_to_legal,
                "blocking_count": blocking_count,
                "missing_items": [item.model_dump() for item in check.missing_items],
                "expected_documents": [item.model_dump() for item in check.expected_documents],
                "found_documents": [item.model_dump() for item in check.found_documents],
                "user_message": check.user_message,
                "source": source,
            },
        )


def _uploaded_documents(context: ReviewContext) -> list[dict[str, str]]:
    raw_documents = context.metadata.get("uploaded_documents") or []
    documents: list[dict[str, str]] = []
    for index, item in enumerate(raw_documents):
        filename = str(item.get("filename") or f"document-{index + 1}")
        text = str(item.get("text") or item.get("text_preview") or "")
        documents.append({"filename": filename, "text": text})

    if not documents and context.contract_text.strip():
        documents.append({"filename": "submitted-contract.txt", "text": context.contract_text})
    return documents


async def _openai_completeness_check(
    context: ReviewContext,
    uploaded_documents: list[dict[str, str]],
) -> CompletenessCheck | None:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package is not installed; using completeness fallback parser")
        return None

    prompt = _completion_prompt(context, uploaded_documents)
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.responses.create(
            model=settings.openai_model,
            reasoning={"effort": settings.openai_reasoning_effort},
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are Harvey's pre-Legal escalation completeness checker. "
                        "Build a dynamic Soll-Liste from the checklist and uploaded document content, "
                        "compare it to the ticket's actual uploaded files, and return JSON only. "
                        "Do not search external company data. Missing blocking information means "
                        "needs_business_input, not Legal escalation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ticket_completeness_check",
                    "strict": True,
                    "schema": _json_schema(),
                },
            },
        )
        raw = response.output_text or ""
        return CompletenessCheck.model_validate(json.loads(raw))
    except Exception as exc:
        logger.warning("OpenAI completeness check failed; using fallback parser: %s", exc)
        return None


def _completion_prompt(context: ReviewContext, uploaded_documents: list[dict[str, str]]) -> str:
    inventory = [
        {
            "filename": item["filename"],
            "text_preview": _compact(item["text"])[:3000],
        }
        for item in uploaded_documents
    ]
    checklist = [
        "All annexes, attachments, schedules, exhibits, appendices, Anlagen, and Anhange referenced as part of the contract package must be present.",
        "If only an order form is present but it references a master agreement, the master agreement should be requested.",
        "If a data processing agreement mentions technical and organisational measures, subprocessors, Standard Contractual Clauses, or transfer assessments, those referenced materials should be present.",
        "Missing business context such as supplier, BMW entity, use case, data categories, processing start, contract value, and deadline should be flagged as business input, not as a Legal escalation.",
        "Contradictions between the user's statement and the uploaded documents should be flagged.",
    ]
    return json.dumps(
        {
            "ticket_question": context.user_question or "",
            "contract_type": context.contract_type or "unknown",
            "checklist": checklist,
            "uploaded_file_inventory": [{"filename": item["filename"]} for item in uploaded_documents],
            "uploaded_document_previews": inventory,
            "required_behavior": (
                "Return every expected document or business input that is material before Legal receives the ticket. "
                "If a document reference is found in the contract but no uploaded file clearly matches it, mark it as blocking."
            ),
        },
        ensure_ascii=False,
    )


def _json_schema() -> dict[str, Any]:
    item_category = {
        "type": "string",
        "enum": [
            "missing_documents",
            "missing_metadata",
            "missing_business_context",
            "unclear_input",
            "inconsistencies",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "can_submit_to_legal": {"type": "boolean"},
            "status": {"type": "string", "enum": ["complete", "needs_business_input"]},
            "expected_documents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "normalized_label": {"type": "string"},
                        "category": item_category,
                        "basis": {"type": "string"},
                        "required": {"type": "boolean"},
                        "source_file": {"type": ["string", "null"]},
                        "source_quote": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "label",
                        "normalized_label",
                        "category",
                        "basis",
                        "required",
                        "source_file",
                        "source_quote",
                        "confidence",
                    ],
                },
            },
            "found_documents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "expected_label": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["found", "missing", "ambiguous", "unreadable", "not_applicable"],
                        },
                        "matched_filename": {"type": ["string", "null"]},
                        "reason": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["expected_label", "status", "matched_filename", "reason", "confidence"],
                },
            },
            "missing_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "category": item_category,
                        "severity": {"type": "string", "enum": ["blocking", "warning", "info"]},
                        "reason": {"type": "string"},
                        "source_file": {"type": ["string", "null"]},
                        "source_quote": {"type": ["string", "null"]},
                        "user_action": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "label",
                        "category",
                        "severity",
                        "reason",
                        "source_file",
                        "source_quote",
                        "user_action",
                        "confidence",
                    ],
                },
            },
            "user_message": {"type": "string"},
        },
        "required": [
            "can_submit_to_legal",
            "status",
            "expected_documents",
            "found_documents",
            "missing_items",
            "user_message",
        ],
    }


REFERENCE_PATTERN = re.compile(
    r"\b(?P<label>annex|attachment|appendix|schedule|exhibit|anlage|anhang|anl\.)s?"
    r"\s+(?P<values>[A-Z0-9]+(?:\s*(?:,|and|or|&|und|/)\s*[A-Z0-9]+)*)",
    re.IGNORECASE,
)


def _fallback_completeness_check(
    context: ReviewContext,
    uploaded_documents: list[dict[str, str]],
) -> CompletenessCheck:
    references = _extract_references(uploaded_documents)
    expected_documents: list[ExpectedDocument] = []
    found_documents: list[DocumentMatch] = []
    missing_items: list[MissingCompletenessItem] = []

    seen: set[str] = set()
    for reference in references:
        normalized = _normalize_label(reference["label"])
        if normalized in seen:
            continue
        seen.add(normalized)
        expected_documents.append(
            ExpectedDocument(
                label=reference["label"],
                normalized_label=normalized,
                basis="document_reference",
                required=True,
                source_file=reference["source_file"],
                source_quote=reference["source_quote"],
                confidence=0.86,
            )
        )
        matched = _match_reference(reference["label"], reference["source_file"], uploaded_documents)
        if matched:
            found_documents.append(
                DocumentMatch(
                    expected_label=reference["label"],
                    status="found",
                    matched_filename=matched,
                    reason="An uploaded file name or document heading appears to match the referenced material.",
                    confidence=0.82,
                )
            )
        else:
            missing_items.append(
                MissingCompletenessItem(
                    label=reference["label"],
                    reason=f"The uploaded materials refer to {reference['label']}, but the ticket bundle does not include a clearly matching file.",
                    source_file=reference["source_file"],
                    source_quote=reference["source_quote"],
                    confidence=0.88,
                )
            )

    vague_question = _is_vague_question(context.user_question or "")
    if vague_question:
        missing_items.append(
            MissingCompletenessItem(
                label="Concrete business question",
                category="missing_business_context",
                severity="warning",
                reason="The business request is too vague for a complete Legal submission package.",
                source_file=None,
                source_quote=context.user_question,
                user_action="add_specific_business_question",
                confidence=0.68,
            )
        )

    blocking = [item for item in missing_items if item.severity == "blocking"]
    status = "needs_business_input" if blocking else "complete"
    user_message = (
        "The ticket package is missing material referenced by the uploaded contract. Ask the business owner to upload it or record why it is unavailable."
        if blocking
        else "The completeness gate did not find blocking missing documents in the current ticket package."
    )
    return CompletenessCheck(
        can_submit_to_legal=not blocking,
        status=status,
        expected_documents=expected_documents,
        found_documents=found_documents,
        missing_items=missing_items,
        user_message=user_message,
    )


def _extract_references(uploaded_documents: list[dict[str, str]]) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for document in uploaded_documents:
        text = document.get("text") or ""
        filename = document.get("filename") or "document"
        for match in REFERENCE_PATTERN.finditer(text):
            prefix = _canonical_prefix(match.group("label"))
            for value in _split_reference_values(match.group("values")):
                label = f"{prefix} {value.upper() if len(value) == 1 and value.isalpha() else value}"
                quote = _sentence_around(text, match.start())
                references.append({"label": label, "source_file": filename, "source_quote": quote})
    return references


def _split_reference_values(raw: str) -> list[str]:
    values = re.split(r"\s*(?:,|and|or|&|und|/)\s*", raw, flags=re.IGNORECASE)
    return [value.strip().strip(".:;,)(") for value in values if value.strip()]


def _canonical_prefix(raw: str) -> str:
    normalized = raw.lower().rstrip(".")
    if normalized == "anlage":
        return "Anlage"
    if normalized == "anhang":
        return "Anhang"
    if normalized in {"anl"}:
        return "Anlage"
    return normalized.capitalize()


def _match_reference(label: str, source_file: str, uploaded_documents: list[dict[str, str]]) -> str | None:
    normalized = _normalize_label(label)
    heading_pattern = re.compile(rf"\b{re.escape(label)}\b\s*[-:–—]?", re.IGNORECASE)
    for document in uploaded_documents:
        filename = document.get("filename") or ""
        filename_normalized = _normalize_label(filename)
        if normalized and normalized in filename_normalized:
            return filename

        first_page = (document.get("text") or "")[:1000]
        if filename != source_file and heading_pattern.search(first_page):
            return filename
        if filename == source_file and heading_pattern.match(_compact(first_page)[:160]):
            return filename
    return None


def _normalize_label(value: str) -> str:
    value = value.lower()
    replacements = {
        "anlage": "annex",
        "anhang": "annex",
        "attachment": "annex",
        "appendix": "annex",
        "schedule": "annex",
        "exhibit": "annex",
    }
    for source, target in replacements.items():
        value = re.sub(rf"\b{source}\b", target, value)
    return re.sub(r"[^a-z0-9]+", "", value)


def _sentence_around(text: str, index: int) -> str:
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index))
    end_candidates = [position for position in (text.find(".", index), text.find("\n", index)) if position != -1]
    end = min(end_candidates) + 1 if end_candidates else min(len(text), index + 240)
    return _compact(text[start + 1 : end]).strip()


def _finding_from_missing_item(item: MissingCompletenessItem) -> Finding:
    suffix = _normalize_label(item.label) or re.sub(r"[^a-z0-9]+", "-", item.label.lower()).strip("-")
    severity = Severity.HIGH if item.severity == "blocking" else Severity.MEDIUM if item.severity == "warning" else Severity.INFO
    trigger = (
        ContractTrigger(text=item.source_quote, start=None, end=None)
        if item.source_quote
        else None
    )
    return Finding(
        id=f"missing-required-document-{suffix}" if item.category == "missing_documents" else f"missing-business-input-{suffix}",
        title=f"{item.label} missing before Legal submission",
        description=item.reason,
        severity=severity,
        clause_reference=item.source_quote,
        trigger=trigger,
        evidence=[
            Evidence(
                source=f"Completeness check: {item.source_file or 'ticket intake'}",
                citation=item.label,
                quote=item.source_quote,
            )
        ],
        requires_escalation=False,
    )


def _is_vague_question(question: str) -> bool:
    compact = _compact(question).lower()
    return compact in {"is this ok?", "is this okay?", "can we sign?", "please review", "review this", "is this acceptable?"}


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
