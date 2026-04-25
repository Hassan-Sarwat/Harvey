from __future__ import annotations

from typing import Any
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.services.escalation_repository import (
    DENIED,
    EscalationAlreadyDecidedError,
    EscalationRepository,
)

router = APIRouter(prefix="/escalations", tags=["escalations"])


class LegalDecisionRequest(BaseModel):
    decision: Literal["accepted", "denied"]
    notes: str | None = None
    fix_suggestions: list[str] = Field(default_factory=list)
    decided_by: str | None = None

    @model_validator(mode="after")
    def validate_denial_fixes(self) -> "LegalDecisionRequest":
        self.fix_suggestions = [suggestion.strip() for suggestion in self.fix_suggestions if suggestion.strip()]
        if self.decision == DENIED and not self.fix_suggestions:
            raise ValueError("Denied escalations require at least one legal fix suggestion.")
        if self.decided_by is not None:
            self.decided_by = self.decided_by.strip() or None
        return self


class EscalationChatRequest(BaseModel):
    question: str = Field(min_length=1)

    @model_validator(mode="after")
    def clean_question(self) -> "EscalationChatRequest":
        self.question = self.question.strip()
        if not self.question:
            raise ValueError("question is required")
        return self


@router.get("")
async def list_escalations(
    status: Literal["pending_legal", "accepted", "denied"] | None = Query(default=None),
) -> dict:
    return {"items": EscalationRepository().list_escalations(status=status)}


@router.get("/{escalation_id}")
async def get_escalation(escalation_id: str) -> dict:
    escalation = EscalationRepository().get_escalation(escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found.")
    return escalation


@router.post("/{escalation_id}/chat")
async def ask_escalation_context(escalation_id: str, request: EscalationChatRequest) -> dict:
    escalation = EscalationRepository().get_escalation(escalation_id)
    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found.")

    answer, cited_context = _answer_escalation_question(escalation, request.question)
    return {
        "escalation_id": escalation_id,
        "question": request.question,
        "answer": answer,
        "cited_context": cited_context,
    }


@router.post("/{escalation_id}/decision")
async def decide_escalation(escalation_id: str, request: LegalDecisionRequest) -> dict:
    try:
        escalation = EscalationRepository().decide_escalation(
            escalation_id=escalation_id,
            decision=request.decision,
            notes=request.notes,
            fix_suggestions=request.fix_suggestions,
            decided_by=request.decided_by,
        )
    except EscalationAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail="Escalation already has a legal decision.") from exc

    if escalation is None:
        raise HTTPException(status_code=404, detail="Escalation not found.")

    return escalation


def _answer_escalation_question(escalation: dict[str, Any], question: str) -> tuple[str, list[dict[str, Any]]]:
    normalized_question = question.lower()
    annotations = escalation.get("trigger_annotations") or []
    matched_annotations = _matching_annotations(annotations, normalized_question)

    if _asks_about_history(normalized_question):
        timeline = escalation.get("timeline") or []
        answer = (
            f"Ticket {escalation.get('ticket_id', escalation['id'])} is {escalation['status']} for contract {escalation['contract_id']} "
            f"version {escalation.get('version_number') or 'unversioned'}. "
            f"Reason: {escalation['reason']}. "
            f"Timeline: {_timeline_summary(timeline)}"
        )
        return answer, [{"type": "timeline", "items": timeline}]

    if _asks_about_suggestions(normalized_question):
        suggestions = _suggestions_from_annotations(matched_annotations or annotations)
        if not suggestions:
            suggestions = escalation.get("ai_suggestions") or []
        legal_fixes = escalation.get("fix_suggestions") or []
        answer_parts = ["AI suggestions:"]
        answer_parts.extend(_format_suggestions(suggestions) or ["No AI suggestion is recorded for the matched trigger."])
        if legal_fixes:
            answer_parts.append("Legal fix suggestions: " + "; ".join(legal_fixes))
        return " ".join(answer_parts), [{"type": "suggestions", "items": suggestions}, {"type": "legal_fixes", "items": legal_fixes}]

    if _asks_about_rules(normalized_question):
        cited = matched_annotations or annotations
        answer = "Relevant rulings: " + " ".join(_format_ruling(annotation) for annotation in cited[:4])
        return answer, [{"type": "trigger", "items": cited[:4]}]

    cited = matched_annotations or annotations[:4]
    if cited:
        answer = "Relevant contract triggers: " + " ".join(_format_trigger(annotation) for annotation in cited)
        return answer, [{"type": "trigger", "items": cited}]

    return (
        "I could not find a stored trigger annotation for that question. The escalation record still contains the "
        f"AI summary: {escalation.get('review_result', {}).get('summary', escalation.get('reason'))}",
        [{"type": "review_result", "items": [escalation.get("review_result", {})]}],
    )


def _matching_annotations(annotations: list[dict[str, Any]], normalized_question: str) -> list[dict[str, Any]]:
    terms = [term for term in normalized_question.replace("?", " ").replace(",", " ").split() if len(term) > 3]
    if not terms:
        return []

    matches = []
    for annotation in annotations:
        haystack = " ".join(
            str(annotation.get(key) or "")
            for key in ("finding_id", "title", "description", "severity", "text", "agent_name")
        ).lower()
        ruling = annotation.get("ruling") or {}
        haystack += " " + " ".join(str(ruling.get(key) or "") for key in ("source", "citation", "quote")).lower()
        if any(term in haystack for term in terms):
            matches.append(annotation)
    return matches


def _asks_about_history(normalized_question: str) -> bool:
    return any(term in normalized_question for term in ("history", "timeline", "version", "status", "decision"))


def _asks_about_suggestions(normalized_question: str) -> bool:
    return any(term in normalized_question for term in ("suggest", "fix", "rewrite", "change", "replace"))


def _asks_about_rules(normalized_question: str) -> bool:
    return any(term in normalized_question for term in ("rule", "ruling", "playbook", "evidence", "source", "citation", "otto", "legal data"))


def _suggestions_from_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for annotation in annotations:
        for suggestion in annotation.get("suggestions") or []:
            key = (str(suggestion.get("proposed_text")), str(suggestion.get("rationale")))
            if key in seen:
                continue
            seen.add(key)
            suggestions.append(suggestion)
    return suggestions


def _format_suggestions(suggestions: list[dict[str, Any]]) -> list[str]:
    return [
        f"{index}. {suggestion.get('proposed_text')} Rationale: {suggestion.get('rationale')}"
        for index, suggestion in enumerate(suggestions, start=1)
    ]


def _format_ruling(annotation: dict[str, Any]) -> str:
    ruling = annotation.get("ruling") or {}
    if not ruling:
        return f"{annotation.get('title')}: no ruling reference was recorded."
    return (
        f"{annotation.get('title')} cites {ruling.get('source')} "
        f"{ruling.get('citation')}: {ruling.get('quote')}"
    )


def _format_trigger(annotation: dict[str, Any]) -> str:
    severity = str(annotation.get("severity") or "unknown").upper()
    text = annotation.get("text") or "No contract text range recorded."
    return f"{annotation.get('title')} [{severity}] triggered by: \"{text}\"."


def _timeline_summary(timeline: list[dict[str, Any]]) -> str:
    if not timeline:
        return "no timeline events recorded."
    return "; ".join(f"{item.get('event')} at {item.get('at')}" for item in timeline)
