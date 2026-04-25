from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agents.base import AgentResult, Finding, ReviewContext, Severity
from app.services.document_ingestion import extract_document_text
from app.services.escalation_repository import EscalationRepository
from app.services.history_repository import APPROVED, PENDING_LEGAL, HistoryRepository
from app.workflows.legal_qa import LegalQARequest, LegalQAWorkflow
from app.workflows.review_contract import ContractReviewWorkflow


router = APIRouter(prefix="/api", tags=["intake"])

APP_NAME = "BMW Legal Agent Platform"
WORKFLOW_NAME = "Ask Donna"
DEMO_QUESTION = "Can I proceed with this IT vendor DPA, or do I need to escalate it to Legal?"
DEMO_CONTEXT = (
    "BMW is reviewing a connected-vehicle analytics pilot. The supplier draft includes employee and driver data, "
    "remote support access from India and the United States, model-improvement rights, and a 72-hour breach notice."
)

SOURCES = [
    {
        "id": "bmw_data_protection_playbook",
        "label": "BMW DPA Playbook",
        "description": "BMW Group DPA negotiation playbook from data/playbook.",
    },
    {
        "id": "bmw_litigation_playbook",
        "label": "BMW Litigation",
        "description": "BMW litigation, liability, and disputes playbook from data/playbook.",
    },
    {
        "id": "legal_data_hub",
        "label": "Otto Schmidt",
        "description": "Live Otto Schmidt / Legal Data Hub evidence when configured; explicit fallback evidence only if unavailable.",
    },
    {
        "id": "uploaded_bundle",
        "label": "Uploaded bundle",
        "description": "Contract, annex, email, spreadsheet, or zipped matter materials uploaded for this run.",
    },
]

AGENTS = [
    {
        "id": "contract_understanding",
        "label": "Contract Understanding",
        "description": "Classifies agreement type, party context, and likely contract domain.",
    },
    {
        "id": "playbook_checker",
        "label": "BMW Playbook Checker",
        "description": "Checks the draft against the BMW playbook files in data/playbook.",
    },
    {
        "id": "legal_checker",
        "label": "German Legal Checker",
        "description": "Uses Otto Schmidt / Legal Data Hub evidence or clearly marked fallback evidence.",
    },
    {
        "id": "risk_aggregator",
        "label": "Risk Aggregator",
        "description": "Combines specialist findings into an escalation recommendation.",
    },
]

AGENT_LABELS = {item["id"]: item["label"] for item in AGENTS}


@router.get("/config")
async def config() -> dict[str, Any]:
    return {
        "app_name": APP_NAME,
        "workflow_name": WORKFLOW_NAME,
        "demo_question": DEMO_QUESTION,
        "demo_context": DEMO_CONTEXT,
        "sources": SOURCES,
        "agents": AGENTS,
        "default_sources": ["bmw_data_protection_playbook", "legal_data_hub", "uploaded_bundle"],
        "default_agents": [],
    }


@router.get("/dashboard")
async def dashboard() -> dict[str, Any]:
    repository = EscalationRepository()
    escalation_metrics = repository.escalation_metrics()
    escalations = repository.list_escalations()
    trigger_counts = Counter(finding_id.replace("-", " ") for item in escalations for finding_id in item["source_finding_ids"])

    return {
        "total_runs": max(escalation_metrics["total_escalations"], len(escalations)),
        "auto_cleared": 3,
        "legal_recommended": escalation_metrics["pending_escalations"],
        "legal_required": escalation_metrics["positive_escalations"] + escalation_metrics["pending_escalations"],
        "missing_docs_rate": 33 if escalations else 0,
        "top_triggers": [
            {"label": label.title(), "value": value}
            for label, value in trigger_counts.most_common(4)
        ],
        "playbook_deviations": [
            {"label": "Red lines", "value": escalation_metrics["positive_escalations"] + escalation_metrics["pending_escalations"], "color": "red"},
            {"label": "Fallback positions", "value": max(1, escalation_metrics["total_escalations"]), "color": "yellow"},
            {"label": "Standard positions", "value": 3, "color": "green"},
        ],
        "recent_runs": [
            {
                "id": item["id"],
                "question": item["reason"],
                "created_at": item["created_at"],
                "state": "Legal review required before signature",
                "confidence": 0.72,
                "findings": len(item["source_finding_ids"]),
            }
            for item in escalations[:5]
        ],
    }


@router.post("/demo")
async def demo() -> dict[str, Any]:
    sample_path = Path(__file__).resolve().parents[3] / "data" / "samples" / "sample_dpa.txt"
    contract_text = sample_path.read_text(encoding="utf-8") if sample_path.exists() else DEMO_CONTEXT
    return await _run_intake(
        message=DEMO_QUESTION,
        context=DEMO_CONTEXT,
        mode="contract_review",
        thread_id=None,
        is_final_version=False,
        selected_sources=["bmw_data_protection_playbook", "legal_data_hub", "uploaded_bundle"],
        selected_agents=[],
        uploaded_texts=[{"filename": sample_path.name, "text": contract_text}],
        demo_mode=True,
    )


@router.post("/analyze")
async def analyze(
    question: str | None = Form(default=None),
    message: str | None = Form(default=None),
    context: str = Form(default=""),
    mode: str = Form(default="contract_review"),
    thread_id: str | None = Form(default=None),
    is_final_version: bool = Form(default=False),
    selected_sources: str = Form(default="[]"),
    selected_agents: str = Form(default="[]"),
    demo_mode: bool = Form(default=False),
    files: list[UploadFile] | None = File(default=None),
) -> dict[str, Any]:
    question = _optional_form_value(question)
    message = _optional_form_value(message)
    context = _optional_form_value(context) or ""
    mode = _optional_form_value(mode) or "contract_review"
    thread_id = _optional_form_value(thread_id)
    is_final_version = bool(_optional_form_value(is_final_version) or False)
    selected_sources = _optional_form_value(selected_sources) or "[]"
    selected_agents = _optional_form_value(selected_agents) or "[]"
    demo_mode = bool(_optional_form_value(demo_mode) or False)
    parsed_sources = _parse_json_string_list(selected_sources, "selected_sources")
    parsed_agents = _parse_json_string_list(selected_agents, "selected_agents")
    uploaded_texts = await _extract_uploaded_texts(files or [])
    return await _run_intake(
        message=message if message is not None else question,
        context=context,
        mode=mode,
        thread_id=thread_id,
        is_final_version=is_final_version,
        selected_sources=parsed_sources,
        selected_agents=parsed_agents,
        uploaded_texts=uploaded_texts,
        demo_mode=demo_mode,
    )


async def _run_intake(
    *,
    message: str | None,
    context: str,
    mode: str,
    thread_id: str | None,
    is_final_version: bool,
    selected_sources: list[str],
    selected_agents: list[str],
    uploaded_texts: list[dict[str, str]],
    demo_mode: bool,
) -> dict[str, Any]:
    question = (message or "").strip()
    context = context.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is required")

    mode = _normalize_mode(mode)
    is_final_version = is_final_version or (mode == "contract_review" and _detect_final_version(question))
    if mode == "general_question":
        return await _run_general_question(
            question=question,
            context=context,
            thread_id=thread_id,
            uploaded_texts=uploaded_texts,
            demo_mode=demo_mode,
        )

    contract_text = _combined_contract_text(question, context, uploaded_texts)
    contract_type = _infer_contract_type(contract_text)
    routed_agents = selected_agents or _auto_route_agents(contract_text, contract_type)
    created_at = datetime.now(UTC).isoformat()
    contract_id = f"intake-{uuid4().hex[:10]}"

    review_result = await ContractReviewWorkflow().run(
        ReviewContext(
            contract_id=contract_id,
            contract_text=contract_text,
            contract_type=contract_type,
            user_question=question,
            metadata={
                "demo_mode": demo_mode,
                "selected_sources": selected_sources,
                "selected_agents": selected_agents,
                "uploaded_filenames": [item["filename"] for item in uploaded_texts],
            },
        )
    )
    legal_qa = await LegalQAWorkflow().run(
        LegalQARequest(question=question, use_case="legal_intake", contract_type=contract_type)
    )

    escalation_state = _escalation_state(review_result)
    auto_sources = _auto_sources(contract_type, legal_qa.legal_basis, uploaded_texts)
    selected_sources = selected_sources or auto_sources
    legal_sources = [_legal_source_payload(item) for item in legal_qa.legal_basis]
    source_usage = _source_usage(selected_sources, legal_qa.company_basis, legal_sources, uploaded_texts, contract_type)
    contract_status = _contract_history_status(is_final_version, review_result, legal_qa.escalate)
    escalation = _maybe_create_final_escalation(
        contract_status=contract_status,
        contract_id=contract_id,
        review_result=review_result,
        contract_text=contract_text,
    )
    payload = {
        "id": f"run-{uuid4().hex[:12]}",
        "created_at": created_at,
        "mode": mode,
        "question": question,
        "context": context,
        "selected_sources": selected_sources,
        "selected_agents": selected_agents,
        "agent_routing_mode": "auto" if not selected_agents else "manual",
        "routed_agents": routed_agents,
        "routing_summary": _routing_summary(routed_agents, contract_type, selected_agents),
        "escalation_state": escalation_state,
        "confidence": review_result.confidence,
        "plain_answer": _plain_answer(escalation_state, review_result, legal_qa.escalate, contract_status),
        "legal_answer": _legal_answer(legal_qa),
        "next_action": _next_action(review_result, legal_qa.escalate, contract_status),
        "matter_summary": _matter_summary(contract_text, contract_type, uploaded_texts, review_result),
        "agent_steps": _agent_steps(review_result, created_at),
        "findings": [_finding_payload(finding) for finding in review_result.findings],
        "legal_sources": legal_sources,
        "source_usage": source_usage,
        "suggested_language": _suggested_language(review_result),
        "contract_id": contract_id,
        "contract_status": contract_status,
        "is_final_version": is_final_version,
        "escalation_id": escalation["id"] if escalation else None,
        "metrics": {
            "finding_count": len(review_result.findings),
            "requires_escalation": review_result.requires_escalation,
            "contract_type": contract_type,
            "uploaded_documents": len(uploaded_texts),
            "legal_qa_escalate": legal_qa.escalate,
        },
    }
    detail = HistoryRepository().record_run(
        thread_id=thread_id,
        mode=mode,
        message=_history_message(question, context),
        result_payload=payload,
        reasoning=_visible_reasoning(payload),
        sources_used=source_usage,
        uploaded_filenames=[item["filename"] for item in uploaded_texts],
        is_final_version=is_final_version,
        contract_status=contract_status,
        escalation_id=payload["escalation_id"],
    )
    payload["history_thread_id"] = detail["id"]
    return payload


async def _run_general_question(
    *,
    question: str,
    context: str,
    thread_id: str | None,
    uploaded_texts: list[dict[str, str]],
    demo_mode: bool,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    qa_text = _combined_contract_text(question, context, uploaded_texts)
    contract_type = _infer_contract_type(qa_text)
    legal_qa = await LegalQAWorkflow().run(
        LegalQARequest(question=qa_text, use_case="ask_donna", contract_type=contract_type)
    )
    legal_sources = [_legal_source_payload(item) for item in legal_qa.legal_basis]
    selected_sources = _auto_sources(contract_type, legal_qa.legal_basis, uploaded_texts)
    source_usage = _source_usage(selected_sources, legal_qa.company_basis, legal_sources, uploaded_texts, contract_type)
    escalation_state = "Legal review required before signature" if legal_qa.escalate else "No legal escalation recommended"
    payload = {
        "id": f"run-{uuid4().hex[:12]}",
        "created_at": created_at,
        "mode": "general_question",
        "question": question,
        "context": context,
        "selected_sources": selected_sources,
        "selected_agents": [],
        "agent_routing_mode": "auto",
        "routed_agents": ["legal_qa"],
        "routing_summary": "Ask Donna treated this as a general legal/playbook question and selected playbook and legal evidence automatically.",
        "escalation_state": escalation_state,
        "confidence": 0.72,
        "plain_answer": f"{legal_qa.summary} {legal_qa.recommendation}".strip(),
        "legal_answer": _legal_answer(legal_qa),
        "next_action": "Escalate to Legal before proceeding." if legal_qa.escalate else "Use the cited playbook position and keep Legal available for ambiguity.",
        "matter_summary": {
            "agreement_type": "General legal/playbook question",
            "counterparty": "Not applicable",
            "governing_law": "German law / EU GDPR" if contract_type == "data_protection" else "German law",
            "contract_value": "Not provided",
            "personal_data": "personal data" in qa_text.lower() or "gdpr" in qa_text.lower(),
            "uploaded_documents": len(uploaded_texts),
            "missing_documents": [],
        },
        "agent_steps": [
            {
                "id": "legal_qa",
                "label": "Legal and Playbook Q&A",
                "agent": "Legal and Playbook Q&A",
                "status": "completed",
                "summary": legal_qa.summary,
                "detail": f"{len(legal_qa.company_basis)} playbook source(s), {len(legal_qa.legal_basis)} legal source(s).",
                "started_at": created_at,
                "completed_at": created_at,
            }
        ],
        "findings": [],
        "legal_sources": legal_sources,
        "source_usage": source_usage,
        "suggested_language": legal_qa.recommendation,
        "contract_id": None,
        "contract_status": None,
        "is_final_version": False,
        "escalation_id": None,
        "metrics": {
            "finding_count": 0,
            "requires_escalation": legal_qa.escalate,
            "contract_type": contract_type,
            "uploaded_documents": len(uploaded_texts),
            "legal_qa_escalate": legal_qa.escalate,
            "demo_mode": demo_mode,
        },
    }
    detail = HistoryRepository().record_run(
        thread_id=thread_id,
        mode="general_question",
        message=_history_message(question, context),
        result_payload=payload,
        reasoning=_visible_reasoning(payload),
        sources_used=source_usage,
        uploaded_filenames=[item["filename"] for item in uploaded_texts],
        is_final_version=False,
        contract_status=None,
    )
    payload["history_thread_id"] = detail["id"]
    return payload


async def _extract_uploaded_texts(files: list[UploadFile]) -> list[dict[str, str]]:
    extracted: list[dict[str, str]] = []
    for file in files:
        filename = file.filename or "uploaded-document"
        content = await file.read()
        if not content:
            continue
        try:
            text = extract_document_text(filename, content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if text.strip():
            extracted.append({"filename": filename, "text": text})
    return extracted


def _parse_json_string_list(raw: str, field_name: str) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a JSON list") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise HTTPException(status_code=422, detail=f"{field_name} must be a JSON list of strings")
    return parsed


def _normalize_mode(mode: str) -> str:
    normalized = (mode or "contract_review").strip().lower()
    aliases = {
        "general": "general_question",
        "question": "general_question",
        "legal_qa": "general_question",
        "contract": "contract_review",
        "review": "contract_review",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"general_question", "contract_review"}:
        raise HTTPException(status_code=422, detail="mode must be general_question or contract_review")
    return normalized


def _detect_final_version(message: str) -> bool:
    normalized = message.lower()
    phrases = (
        "this is the final version",
        "this is final",
        "final version",
        "final draft",
        "ready for approval",
        "ready to approve",
        "approve this version",
    )
    return any(phrase in normalized for phrase in phrases)


def _optional_form_value(value):
    if type(value).__module__ == "fastapi.params" and type(value).__name__ == "Form":
        return None
    return value


def _history_message(question: str, context: str) -> str:
    if context:
        return f"{question}\n\nBusiness context:\n{context}"
    return question


def _combined_contract_text(question: str, context: str, uploaded_texts: list[dict[str, str]]) -> str:
    parts = [f"User question: {question}"]
    if context:
        parts.append(f"Business context:\n{context}")
    for item in uploaded_texts:
        parts.append(f"Uploaded document: {item['filename']}\n{item['text']}")
    if len(parts) == 1:
        parts.append(question)
    return "\n\n".join(parts)


def _infer_contract_type(text: str) -> str:
    normalized = text.lower()
    data_terms = (
        "gdpr",
        "personal data",
        "data subject",
        "processor",
        "controller",
        "subprocessor",
        "breach notification",
        "third-country",
        "third country",
        "tom",
    )
    litigation_terms = (
        "litigation",
        "settlement",
        "liability",
        "indemnity",
        "court",
        "arbitration",
        "legal hold",
        "governing law",
        "claims",
    )
    data_score = sum(1 for term in data_terms if term in normalized)
    litigation_score = sum(1 for term in litigation_terms if term in normalized)
    if data_score >= litigation_score and data_score > 0:
        return "data_protection"
    if litigation_score > 0:
        return "litigation"
    return "general"


def _auto_route_agents(text: str, contract_type: str) -> list[str]:
    routed = ["contract_understanding", "playbook_checker", "risk_aggregator"]
    if contract_type in {"data_protection", "litigation"} or any(term in text.lower() for term in ("gdpr", "liability", "waive")):
        routed.insert(2, "legal_checker")
    return routed


def _auto_sources(contract_type: str, legal_basis: list[dict[str, Any]], uploaded_texts: list[dict[str, str]]) -> list[str]:
    sources = ["bmw_litigation_playbook" if contract_type == "litigation" else "bmw_data_protection_playbook"]
    if legal_basis:
        sources.append("legal_data_hub")
    if uploaded_texts:
        sources.append("uploaded_bundle")
    return list(dict.fromkeys(sources))


def _source_usage(
    selected_sources: list[str],
    company_basis: list[dict[str, Any]],
    legal_sources: list[dict[str, Any]],
    uploaded_texts: list[dict[str, str]],
    contract_type: str,
) -> list[dict[str, Any]]:
    labels = {item["id"]: item["label"] for item in SOURCES}
    descriptions = {item["id"]: item["description"] for item in SOURCES}
    usage: list[dict[str, Any]] = []
    for source_id in selected_sources:
        if source_id == "uploaded_bundle":
            items = [
                {
                    "title": item["filename"],
                    "source": "Uploaded bundle",
                    "excerpt": item["text"][:280],
                    "fallback": False,
                }
                for item in uploaded_texts
            ]
        elif source_id == "legal_data_hub":
            items = [
                {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "excerpt": item.get("excerpt"),
                    "url": item.get("url"),
                    "fallback": item.get("retrieval_mode") == "fallback" or "fallback" in str(item.get("source") or "").lower(),
                    "fallback_reason": item.get("fallback_reason"),
                }
                for item in legal_sources
            ]
        else:
            items = [
                {
                    "title": item.get("citation"),
                    "source": item.get("source"),
                    "excerpt": item.get("quote"),
                    "fallback": False,
                }
                for item in company_basis
            ]
        usage.append(
            {
                "id": source_id,
                "label": labels.get(source_id, source_id.replace("_", " ").title()),
                "description": descriptions.get(source_id, f"Automatically selected for {contract_type}."),
                "items": items,
                "item_count": len(items),
            }
        )
    return usage


def _routing_summary(routed_agents: list[str], contract_type: str, selected_agents: list[str]) -> str:
    if selected_agents:
        return "Manual Mode used the selected specialist agents."
    labels = ", ".join(AGENT_LABELS.get(agent, agent) for agent in routed_agents)
    return f"Auto Mode inferred {contract_type.replace('_', ' ')} context and routed to {labels}."


def _escalation_state(result: AgentResult) -> str:
    if result.requires_escalation:
        return "Legal review required before signature"
    if result.findings:
        return "Legal review recommended"
    return "No legal escalation recommended"


def _plain_answer(
    escalation_state: str,
    result: AgentResult,
    legal_qa_escalate: bool,
    contract_status: str | None,
) -> str:
    if contract_status == APPROVED:
        return "The final version is approved for the demo workflow because the review found no unresolved playbook or legal checks."
    if contract_status == PENDING_LEGAL:
        return "The final version is stored as pending Legal because unresolved findings or escalation triggers remain."
    if escalation_state == "Legal review required before signature" or legal_qa_escalate:
        return "Do not proceed on the current draft without Legal review. The run found red-line or high-risk positions that need a legal decision."
    if result.findings:
        return "You can continue business review only after addressing the listed playbook deviations and keeping Legal available for unresolved points."
    return "No legal escalation is recommended based on the submitted context and BMW playbook checks."


def _legal_answer(legal_qa: Any) -> str:
    legal_sources = ", ".join(
        item.get("citation", "legal evidence") for item in legal_qa.legal_basis[:2]
    )
    suffix = f" Supporting legal evidence: {legal_sources}." if legal_sources else ""
    return f"{legal_qa.summary} {legal_qa.recommendation}{suffix}".strip()


def _next_action(result: AgentResult, legal_qa_escalate: bool, contract_status: str | None = None) -> str:
    if contract_status == APPROVED:
        return "The contract is stored in History as approved."
    if contract_status == PENDING_LEGAL:
        return "Open the History record or escalation context for Legal review before signature."
    if result.requires_escalation or legal_qa_escalate:
        return "Prepare an escalation packet with the flagged clauses, BMW playbook citations, and Legal Data Hub evidence."
    if result.suggestions:
        return "Send the suggested language to the counterparty and re-run the review on the revised draft."
    return "Record the AI review result and continue normal approval routing."


def _contract_history_status(is_final_version: bool, result: AgentResult, legal_qa_escalate: bool) -> str | None:
    if not is_final_version:
        return None
    if result.findings or result.requires_escalation:
        return PENDING_LEGAL
    return APPROVED


def _maybe_create_final_escalation(
    *,
    contract_status: str | None,
    contract_id: str,
    review_result: AgentResult,
    contract_text: str,
) -> dict[str, Any] | None:
    if contract_status != PENDING_LEGAL:
        return None
    return EscalationRepository().create_from_review(
        contract_id=contract_id,
        review_result=review_result,
        contract_text=contract_text,
        business_reason="Final version still contains unresolved Ask Donna review findings.",
        requested_by="Ask Donna",
        force=True,
    )


def _visible_reasoning(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "routing_summary": payload.get("routing_summary"),
        "escalation_state": payload.get("escalation_state"),
        "next_action": payload.get("next_action"),
        "agent_steps": payload.get("agent_steps") or [],
        "findings": payload.get("findings") or [],
        "source_usage": payload.get("source_usage") or [],
        "contract_status": payload.get("contract_status"),
        "is_final_version": payload.get("is_final_version", False),
    }


def _matter_summary(
    contract_text: str,
    contract_type: str,
    uploaded_texts: list[dict[str, str]],
    result: AgentResult,
) -> dict[str, Any]:
    missing_documents = []
    finding_ids = {finding.id for finding in result.findings}
    if "missing-subprocessor-list" in finding_ids or "subprocessor-general-authorization" in finding_ids:
        missing_documents.append("Named subprocessor list")
    if "generic-security-measures" in finding_ids or "audit-rights-too-limited" in finding_ids:
        missing_documents.append("Detailed TOM / security annex")
    if "third-country-transfer-incomplete" in finding_ids:
        missing_documents.append("SCCs and transfer impact assessment")

    return {
        "agreement_type": _agreement_type(contract_type),
        "counterparty": _counterparty(contract_text),
        "governing_law": "German law / EU GDPR" if contract_type == "data_protection" else "German law",
        "contract_value": "Not provided",
        "personal_data": any(term in contract_text.lower() for term in ("personal data", "gdpr", "data subject")),
        "uploaded_documents": len(uploaded_texts),
        "missing_documents": missing_documents,
    }


def _agreement_type(contract_type: str) -> str:
    if contract_type == "data_protection":
        return "Data processing agreement / privacy addendum"
    if contract_type == "litigation":
        return "Litigation or dispute-support agreement"
    return "Contract intake matter"


def _counterparty(text: str) -> str:
    markers = (" and ", " with ", " between ")
    compact = " ".join(text.split())
    for marker in markers:
        if marker in compact.lower():
            fragment = compact.lower().split(marker, 1)[1]
            words = compact[compact.lower().find(fragment):].split(" ")[:4]
            candidate = " ".join(word.strip(".,;:()") for word in words).strip()
            if candidate:
                return candidate
    return "Counterparty not confirmed"


def _agent_steps(result: AgentResult, created_at: str) -> list[dict[str, str]]:
    agent_results = result.metadata.get("agent_results", [])
    steps: list[dict[str, str]] = []
    for agent_result in agent_results:
        agent_name = str(agent_result.get("agent_name") or "unknown_agent")
        steps.append(
            {
                "id": agent_name,
                "label": AGENT_LABELS.get(agent_name, agent_name.replace("_", " ").title()),
                "agent": AGENT_LABELS.get(agent_name, agent_name.replace("_", " ").title()),
                "status": "completed",
                "summary": str(agent_result.get("summary") or "Completed."),
                "detail": _agent_detail(agent_result),
                "started_at": created_at,
                "completed_at": created_at,
            }
        )
    steps.append(
        {
            "id": "risk_aggregator",
            "label": AGENT_LABELS["risk_aggregator"],
            "agent": AGENT_LABELS["risk_aggregator"],
            "status": "completed",
            "summary": result.summary,
            "detail": f"{len(result.findings)} consolidated finding(s).",
            "started_at": created_at,
            "completed_at": created_at,
        }
    )
    return steps


def _agent_detail(agent_result: dict[str, Any]) -> str:
    finding_count = len(agent_result.get("findings") or [])
    passed = agent_result.get("metadata", {}).get("passed")
    status = "passed" if passed else "flagged issues"
    return f"{finding_count} finding(s), {status}."


def _finding_payload(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "title": finding.title,
        "category": _finding_category(finding),
        "severity": _frontend_severity(finding.severity),
        "band": _finding_band(finding),
        "description": finding.description,
        "recommendation": "Use the suggested language or route the issue to Legal.",
        "evidence": [
            {
                "source_type": item.source,
                "title": item.citation,
                "quote": item.quote or "",
                "locator": finding.clause_reference,
                "url": item.url,
            }
            for item in finding.evidence
        ],
        "confidence": 0.78 if finding.requires_escalation else 0.66,
    }


def _finding_category(finding: Finding) -> str:
    if "data" in finding.id or "subprocessor" in finding.id or "breach" in finding.id:
        return "Data protection"
    if "liability" in finding.id or "settlement" in finding.id or "privilege" in finding.id:
        return "Litigation"
    if "bmw" in finding.id:
        return "Completeness"
    return "Playbook"


def _frontend_severity(severity: Severity) -> str:
    if severity in {Severity.BLOCKER, Severity.HIGH}:
        return "High"
    if severity == Severity.MEDIUM:
        return "Medium"
    return "Low"


def _finding_band(finding: Finding) -> str:
    if finding.requires_escalation or finding.severity in {Severity.BLOCKER, Severity.HIGH}:
        return "redline"
    if finding.severity == Severity.MEDIUM:
        return "fallback"
    return "standard"


def _legal_source_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(item.get("citation") or item.get("title") or "Legal source"),
        "source": str(item.get("source") or "Otto Schmidt / Legal Data Hub"),
        "excerpt": str(item.get("quote") or item.get("excerpt") or "No excerpt returned."),
        "url": item.get("url"),
        "confidence": float(item.get("confidence") or 0.72),
        "retrieval_mode": item.get("retrieval_mode"),
        "fallback_reason": item.get("fallback_reason"),
    }


def _suggested_language(result: AgentResult) -> str:
    if result.suggestions:
        return result.suggestions[0].proposed_text
    return "No fallback clause language was required for this run."
