from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.services.legal_data_hub import LegalDataHubClient
from app.services.openai_compat import chat_completion_options
from app.services.playbook_repository import (
    load_playbook_markdown,
    load_playbook_rows,
    playbook_file_label,
    playbook_source_label,
)

logger = logging.getLogger(__name__)


DATA_PROTECTION_SOURCE_ID = "bmw_data_protection_playbook"
LITIGATION_SOURCE_ID = "bmw_litigation_playbook"
ACTIVE_PLAYBOOKS = (
    ("data_protection", DATA_PROTECTION_SOURCE_ID),
    ("litigation", LITIGATION_SOURCE_ID),
)
GENERAL_INITIAL_MAX_TOKENS = 2500
GENERAL_FINAL_MAX_TOKENS = 5000


class GeneralQuestionRequest(BaseModel):
    question: str
    context: str = ""
    contract_type: str | None = None
    thread_id: str | None = None
    uploaded_documents: list[dict[str, str]] = Field(default_factory=list)


class GeneralQuestionResponse(BaseModel):
    domain: str
    summary: str
    recommendation: str
    company_basis: list[dict] = Field(default_factory=list)
    legal_basis: list[dict] = Field(default_factory=list)
    escalate: bool = False
    ai_generated: bool = False
    answer_kind: str = "general_answer"
    playbook_row_count: int = 0
    document_count: int = 0
    routed_agents: list[str] = Field(default_factory=list)
    routing_summary: str
    selected_source_ids: list[str] = Field(default_factory=list)
    legal_tool_called: bool = False


class GeneralAnswerGeneration(BaseModel):
    answer: str = ""
    legal_basis: list[dict] = Field(default_factory=list)
    legal_tool_called: bool = False


class GeneralQuestionWorkflow:
    def __init__(self, legal_data_hub: LegalDataHubClient | None = None) -> None:
        self.legal_data_hub = legal_data_hub or LegalDataHubClient()

    async def run(self, request: GeneralQuestionRequest) -> GeneralQuestionResponse:
        documents = _clean_documents(request.uploaded_documents)
        domain = _infer_domain(request, documents)
        playbook_rows = _load_complete_playbook_rows()
        company_basis = _company_basis_from_rows(playbook_rows)

        generated = await _openai_general_answer(
            question=request.question.strip(),
            context=request.context.strip(),
            documents=documents,
            playbook_rows=playbook_rows,
            domain=domain,
            thread_id=request.thread_id,
            legal_data_hub=self.legal_data_hub,
        )
        generated = _coerce_generation(generated)

        selected_sources = [DATA_PROTECTION_SOURCE_ID, LITIGATION_SOURCE_ID]
        if documents:
            selected_sources.append("uploaded_bundle")
        selected_sources.append("legal_data_hub")

        return GeneralQuestionResponse(
            domain=domain,
            summary=generated.answer or _answer_generation_unavailable(),
            recommendation=_recommendation(generated.legal_basis),
            company_basis=company_basis,
            legal_basis=generated.legal_basis,
            escalate=False,
            ai_generated=bool(generated.answer),
            answer_kind="general_answer",
            playbook_row_count=len(playbook_rows),
            document_count=len(documents),
            routed_agents=["legal_qa"],
            routing_summary=_routing_summary(documents, generated.legal_basis),
            selected_source_ids=selected_sources,
            legal_tool_called=True,
        )


async def _openai_general_answer(
    *,
    question: str,
    context: str,
    documents: list[dict[str, str]],
    playbook_rows: list[dict[str, str]],
    domain: str,
    thread_id: str | None,
    legal_data_hub: LegalDataHubClient,
) -> GeneralAnswerGeneration:
    from app.core.config import get_settings

    settings = get_settings()
    legal_basis: list[dict] = []
    legal_tool_called = True
    legal_domain = _legal_search_domain(None, fallback_domain=domain, query=question)
    try:
        evidence = await legal_data_hub.search_evidence(question, domain=legal_domain)
        legal_basis = [_normalize_legal_basis(item) for item in evidence[:3]]
    except Exception as exc:
        logger.warning("Legal Data Hub prefetch failed: %s", exc)

    direct_qna_answer = _direct_qna_answer(question=question, legal_basis=legal_basis, playbook_rows=playbook_rows)
    if direct_qna_answer:
        return GeneralAnswerGeneration(
            answer=direct_qna_answer,
            legal_basis=legal_basis,
            legal_tool_called=legal_tool_called,
        )

    if not settings.openai_api_key:
        return GeneralAnswerGeneration(legal_basis=legal_basis, legal_tool_called=legal_tool_called)

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package is not installed; general answer generation is unavailable")
        return GeneralAnswerGeneration(legal_basis=legal_basis, legal_tool_called=legal_tool_called)

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        system_prompt = _system_prompt(playbook_rows, legal_evidence_prefetched=bool(legal_basis))
        user_prompt = _user_prompt(question=question, context=context, documents=documents, legal_basis=legal_basis)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if thread_id:
            messages.extend(_fetch_thread_messages(thread_id))
        messages.append({"role": "user", "content": user_prompt})

        if legal_basis:
            response = await _create_chat_completion(
                client=client,
                model=settings.openai_model,
                messages=messages,
                tools=None,
                tool_choice=None,
                max_tokens=GENERAL_FINAL_MAX_TOKENS,
            )
            message = response.choices[0].message
            return GeneralAnswerGeneration(
                answer=message.content or "",
                legal_basis=legal_basis,
                legal_tool_called=legal_tool_called,
            )

        first_response = await _create_chat_completion(
            client=client,
            model=settings.openai_model,
            messages=messages,
            tools=[_legal_search_tool_schema()],
            tool_choice="auto",
            max_tokens=GENERAL_INITIAL_MAX_TOKENS,
        )
        first_message = first_response.choices[0].message
        tool_calls = list(getattr(first_message, "tool_calls", None) or [])
        if not tool_calls:
            return GeneralAnswerGeneration(
                answer=first_message.content or "",
                legal_basis=legal_basis,
                legal_tool_called=legal_tool_called,
            )

        messages.append(_assistant_tool_call_message(first_message))
        for tool_call in tool_calls:
            if _tool_call_name(tool_call) != "search_german_law":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": getattr(tool_call, "id", ""),
                        "name": _tool_call_name(tool_call),
                        "content": json.dumps({"error": "Unsupported tool call."}),
                    }
                )
                continue
            args = _tool_call_arguments(tool_call)
            query = str(args.get("query") or question).strip() or question
            legal_domain = _legal_search_domain(args.get("domain"), fallback_domain=domain, query=query)
            evidence = await legal_data_hub.search_evidence(query, domain=legal_domain)
            normalized = [_normalize_legal_basis(item) for item in evidence[:3]]
            legal_basis.extend(normalized)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(tool_call, "id", ""),
                    "name": "search_german_law",
                    "content": json.dumps({"evidence": normalized}),
                }
            )

        final_response = await _create_chat_completion(
            client=client,
            model=settings.openai_model,
            messages=messages,
            tools=None,
            tool_choice=None,
            max_tokens=GENERAL_FINAL_MAX_TOKENS,
        )
        final_message = final_response.choices[0].message
        return GeneralAnswerGeneration(
            answer=final_message.content or "",
            legal_basis=legal_basis,
            legal_tool_called=legal_tool_called,
        )
    except Exception as exc:
        logger.warning("OpenAI general answer failed: %s", exc)
        return GeneralAnswerGeneration(legal_basis=legal_basis, legal_tool_called=legal_tool_called)


async def _create_chat_completion(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: str | None,
    max_tokens: int,
) -> Any:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    kwargs.update(chat_completion_options(model, max_tokens=max_tokens))
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice
    return await client.chat.completions.create(**kwargs)


def _system_prompt(playbook_rows: list[dict[str, str]], *, legal_evidence_prefetched: bool = False) -> str:
    legal_instructions = (
        [
            "German/EU legal evidence has already been provided in the user message; use it and do not call a legal tool.",
        ]
        if legal_evidence_prefetched
        else [
            "If the user needs a German or EU legal reference, call the search_german_law tool before answering.",
            "Call the legal tool for questions about GDPR, BGB, ZPO, statutes, legality, legal requirements, German courts, EU law, or case law.",
        ]
    )
    return "\n".join(
        [
            "You are Ask Donna, BMW Group's in-house legal assistant.",
            "Answer the user's general intake question from the user input, uploaded context, and the complete BMW playbook context below.",
            "Use only the provided BMW playbook context for BMW policy or negotiation positions.",
            *legal_instructions,
            "Do not call the legal tool merely to summarize the playbook, define playbook terms such as processor/controller, or explain what contract type the playbook covers.",
            "Do not call the legal tool merely because a playbook row mentions GDPR; the playbook context is enough unless the user asks for external law.",
            "If legal evidence is marked as fallback, explicitly say it is fallback evidence and not live Otto Schmidt research.",
            "Do not present yourself as replacing Legal. Flag red lines and legal judgment calls clearly.",
            "Keep the answer practical and cite BMW playbook rule IDs where relevant.",
            "",
            "## Complete Active BMW Playbooks",
            _format_playbooks_for_context(playbook_rows),
            _format_markdown_playbooks_for_context(),
        ]
    )


def _user_prompt(
    *,
    question: str,
    context: str,
    documents: list[dict[str, str]],
    legal_basis: list[dict] | None = None,
) -> str:
    parts = [f"## User Question\n{question}"]
    if context:
        parts.append(f"## Business Context\n{context}")
    if documents:
        parts.append("## Uploaded Documents")
        for document in documents:
            parts.append(f"### {document['filename']}\n{document['text'][:8000]}")
    if legal_basis:
        parts.append("## Otto Schmidt / Legal Data Hub Evidence\n" + _format_legal_evidence_for_prompt(legal_basis))
    return "\n\n".join(parts)


def _format_legal_evidence_for_prompt(legal_basis: list[dict]) -> str:
    parts: list[str] = []
    qna_answer = next((str(item.get("qna_answer") or "").strip() for item in legal_basis if item.get("qna_answer")), "")
    if qna_answer:
        parts.append(f"QnA answer text:\n{qna_answer[:2400]}")

    for index, item in enumerate(legal_basis[:3], start=1):
        citation = str(item.get("citation") or item.get("title") or f"Legal source {index}")
        source = str(item.get("source") or "Otto Schmidt / Legal Data Hub")
        quote = str(item.get("quote") or item.get("excerpt") or "").strip()
        retrieval = str(item.get("retrieval_mode") or "live")
        fallback_reason = str(item.get("fallback_reason") or "").strip()
        lines = [f"{index}. {citation}", f"Source: {source}", f"Retrieval mode: {retrieval}"]
        if fallback_reason:
            lines.append(f"Fallback reason: {fallback_reason}")
        if quote:
            lines.append(f"Excerpt: {quote[:800]}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _direct_qna_answer(
    *,
    question: str,
    legal_basis: list[dict],
    playbook_rows: list[dict[str, str]],
) -> str:
    qna_answer = next((str(item.get("qna_answer") or "").strip() for item in legal_basis if item.get("qna_answer")), "")
    if not qna_answer:
        return ""

    parts = [
        _clean_qna_text(qna_answer),
    ]
    relevant_rows = _relevant_playbook_rows(question, playbook_rows)
    if relevant_rows:
        parts.append(_format_relevant_playbook_notes(relevant_rows))
    parts.append(
        "This does not replace Legal review. Treat this as intake guidance and involve Legal before sending "
        "personal data to a third-country hosted SaaS provider."
    )
    footnotes = _qna_source_footnotes(legal_basis)
    if footnotes:
        parts.append(footnotes)
    return "\n\n".join(part for part in parts if part).strip()


def _clean_qna_text(text: str) -> str:
    cleaned = re.sub(r"</br\s*/?>|<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _qna_source_footnotes(legal_basis: list[dict]) -> str:
    footnotes: list[tuple[int, str]] = []
    seen_numbers: set[int] = set()
    for fallback_index, item in enumerate(legal_basis, start=1):
        if item.get("retrieval_endpoint") != "qna":
            continue
        source = str(item.get("metadata_source") or item.get("citation") or "").strip()
        if not source:
            continue
        number, label = _qna_source_number_and_label(source, fallback_index)
        if number in seen_numbers:
            continue
        seen_numbers.add(number)
        footnotes.append((number, _format_qna_source_footnote(number, label, item)))

    if not footnotes:
        return ""
    ordered = [entry for _, entry in sorted(footnotes, key=lambda item: item[0])]
    return "Sources\n\n" + "\n".join(ordered)


def _qna_source_number_and_label(source: str, fallback_index: int) -> tuple[int, str]:
    match = re.match(r"^\[(\d+)]\s*(.*)$", source)
    if not match:
        return fallback_index, source
    number = int(match.group(1))
    label = match.group(2).strip() or source
    return number, label


def _format_qna_source_footnote(number: int, label: str, item: dict) -> str:
    details = [
        str(item.get("source_type") or item.get("metadata_dokumententyp") or "").strip(),
        str(item.get("date") or item.get("metadata_datum") or "").strip()[:10],
        str(item.get("aktenzeichen") or item.get("metadata_aktenzeichen") or "").strip(),
    ]
    detail_text = ", ".join(detail for detail in details if detail)
    url = str(item.get("url") or item.get("metadata_oso_url") or "").strip()

    line = f"- [{number}] {label}"
    if detail_text:
        line += f" ({detail_text})"
    if url:
        line += f" [Open source]({url})"
    return line


def _relevant_playbook_rows(question: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = question.lower()
    forced_ids: list[str] = []
    if any(term in normalized for term in ("außerhalb der eu", "ausserhalb der eu", "third country", "drittland", "outside the eu", "hostet")):
        forced_ids.append("DPA-007")
    if any(term in normalized for term in ("saas", "cloud", "anbieter", "provider")):
        forced_ids.append("DPA-005")

    by_id = {row.get("id"): row for row in rows}
    selected = [by_id[rule_id] for rule_id in forced_ids if rule_id in by_id]
    if selected:
        return selected[:3]

    terms = {term for term in re.split(r"\W+", normalized) if len(term) >= 5}
    scored: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        searchable = " ".join(str(row.get(key) or "") for key in row).lower()
        score = sum(1 for term in terms if term in searchable)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[:3]]


def _format_relevant_playbook_notes(rows: list[dict[str, str]]) -> str:
    lines = ["BMW playbook points:"]
    for row in rows:
        rule = f"{row.get('id', 'Rule')} - {row.get('title', 'Untitled rule')}"
        severity = str(row.get("severity") or "medium").upper()
        lines.append(f"- {rule} [{severity}]")
        default = str(row.get("default") or "").strip()
        preferred = str(row.get("preferred_position") or "").strip()
        red_line = str(row.get("red_line") or "").strip()
        escalation = str(row.get("escalation_trigger") or "").strip()
        if default:
            lines.append(f"  BMW standard: {default}")
        if preferred:
            lines.append(f"  Preferred position: {preferred}")
        if red_line:
            lines.append(f"  Red line: {red_line}")
        if escalation:
            lines.append(f"  Escalate if: {escalation}")
    return "\n".join(lines)


def _legal_search_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "search_german_law",
            "description": (
                "Search Otto Schmidt / Legal Data Hub for German or EU legal evidence. "
                "Use only when the answer needs statutory, regulatory, or case-law support."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The precise German/EU legal research question to search for.",
                    },
                    "domain": {
                        "type": "string",
                        "enum": ["data_protection", "litigation", "general"],
                        "description": "Use data_protection for GDPR/privacy questions and litigation for BGB/ZPO/dispute questions.",
                    },
                },
                "required": ["query"],
            },
        },
    }


def _assistant_tool_call_message(message: Any) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": getattr(message, "content", None) or "",
        "tool_calls": [
            {
                "id": getattr(call, "id", ""),
                "type": getattr(call, "type", "function"),
                "function": {
                    "name": _tool_call_name(call),
                    "arguments": getattr(getattr(call, "function", None), "arguments", "{}") or "{}",
                },
            }
            for call in (getattr(message, "tool_calls", None) or [])
        ],
    }


def _tool_call_name(tool_call: Any) -> str:
    return str(getattr(getattr(tool_call, "function", None), "name", "") or "")


def _tool_call_arguments(tool_call: Any) -> dict[str, Any]:
    raw = getattr(getattr(tool_call, "function", None), "arguments", "{}") or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _legal_search_domain(raw_domain: Any, *, fallback_domain: str, query: str) -> str:
    domain = str(raw_domain or "").strip()
    if domain in {"data_protection", "litigation"}:
        return domain
    inferred = _infer_domain_from_text(query)
    if inferred in {"data_protection", "litigation"}:
        return inferred
    if fallback_domain in {"data_protection", "litigation"}:
        return fallback_domain
    return "data_protection"


def _should_prefetch_legal_evidence(
    *,
    question: str,
    context: str,
    documents: list[dict[str, str]],
) -> bool:
    text = " ".join(
        [
            question,
            context,
            " ".join(document.get("text", "")[:1200] for document in documents),
        ]
    ).lower()
    if _asks_only_for_playbook_or_terms(text):
        return False
    legal_terms = (
        "gdpr",
        "dsgvo",
        "bgb",
        "zpo",
        "article 28",
        "art. 28",
        "art 28",
        "article 44",
        "art. 44",
        "art 44",
        "personenbezogene",
        "personal data",
        "datenschutz",
        "außerhalb der eu",
        "ausserhalb der eu",
        "outside the eu",
        "third-country",
        "third country",
        "drittland",
        "standard contractual clauses",
        "scc",
        "rechtsprechung",
        "gesetz",
        "zulässig",
        "zulaessig",
        "darf ",
    )
    return any(term in text for term in legal_terms)


def _asks_only_for_playbook_or_terms(text: str) -> bool:
    asks_summary = any(term in text for term in ("summarize", "summary", "what is", "explain", "define"))
    playbook_only = "playbook" in text and asks_summary
    terminology_only = any(term in text for term in ("controller", "processor", "subprocessor")) and any(
        term in text for term in ("difference", "define", "what is", "what's")
    )
    return playbook_only or terminology_only


def _load_complete_playbook_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for domain, source_id in ACTIVE_PLAYBOOKS:
        for row in load_playbook_rows(domain):
            enriched = dict(row)
            enriched["_domain"] = domain
            enriched["_source_id"] = source_id
            enriched["_source"] = playbook_source_label(domain)
            enriched["_file"] = playbook_file_label(domain)
            rows.append(enriched)
    return rows


def _format_playbooks_for_context(rows: list[dict[str, str]]) -> str:
    sections: list[str] = []
    current_group = ""
    for row in rows:
        group = f"{row.get('_source', 'BMW playbook')}: {row.get('_file', '')}"
        if group != current_group:
            sections.append(f"\n### {group}")
            current_group = group

        rule_id = row.get("id", "")
        title = row.get("title", "")
        severity = (row.get("severity") or "medium").upper()
        lines = [f"{rule_id} - {title} [{severity}]"]
        for key, label in [
            ("default", "BMW standard position"),
            ("preferred_position", "Preferred position"),
            ("why_it_matters", "Why it matters"),
            ("fallback_1", "Fallback 1"),
            ("fallback_2", "Fallback 2"),
            ("red_line", "Red line"),
            ("escalation_trigger", "Escalation trigger"),
            ("legal_basis", "Legal basis noted in playbook"),
            ("approved_fix", "Approved fix"),
        ]:
            value = str(row.get(key) or "").strip()
            if value:
                lines.append(f"{label}: {value}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) if sections else "No active playbook rows were found."


def _format_markdown_playbooks_for_context() -> str:
    dpa_markdown = load_playbook_markdown("data_protection").strip()
    if not dpa_markdown:
        return ""
    return "\n\n## Source Markdown DPA Playbook\n\n" + dpa_markdown


def _company_basis_from_rows(rows: list[dict[str, str]]) -> list[dict]:
    return [
        {
            "source_id": row.get("_source_id"),
            "domain": row.get("_domain"),
            "source": f"{row.get('_source')}: {row.get('_file')}",
            "citation": f"{row.get('id', 'unknown')} - {row.get('title', 'Untitled rule')}",
            "quote": row.get("default") or row.get("preferred_position") or "",
            "severity": row.get("severity"),
            "approved_fix": row.get("approved_fix"),
        }
        for row in rows
    ]


def _clean_documents(uploaded_documents: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for document in uploaded_documents:
        raw_text = str(document.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r"[ \t]+", " ", raw_text)
        if not text:
            continue
        cleaned.append(
            {
                "filename": str(document.get("filename") or "uploaded-document"),
                "text": text,
            }
        )
    return cleaned


def _infer_domain(request: GeneralQuestionRequest, documents: list[dict[str, str]]) -> str:
    supplied = (request.contract_type or "").strip()
    if supplied in {"data_protection", "litigation"}:
        return supplied
    text = " ".join(
        [
            request.question,
            request.context,
            " ".join(document.get("text", "")[:1200] for document in documents),
        ]
    )
    inferred = _infer_domain_from_text(text)
    return inferred if inferred in {"data_protection", "litigation"} else "data_protection"


def _infer_domain_from_text(text: str) -> str:
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
        "datenschutz",
    )
    litigation_terms = (
        "litigation",
        "settlement",
        "liability",
        "indemnity",
        "court",
        "arbitration",
        "legal hold",
        "zpo",
        "bgb",
    )
    data_score = sum(1 for term in data_terms if term in normalized)
    litigation_score = sum(1 for term in litigation_terms if term in normalized)
    if litigation_score > data_score and litigation_score > 0:
        return "litigation"
    if data_score > 0:
        return "data_protection"
    return "general"


def _normalize_legal_basis(item: dict) -> dict:
    normalized = dict(item)
    source = str(normalized.get("source") or "")
    if not source:
        normalized["source"] = "Otto Schmidt / Legal Data Hub"
    elif "fallback" in source.lower() and "Otto Schmidt" not in source:
        normalized["source"] = f"Otto Schmidt / {source}"
    return normalized


def _coerce_generation(value: Any) -> GeneralAnswerGeneration:
    if isinstance(value, GeneralAnswerGeneration):
        return value
    if isinstance(value, dict):
        return GeneralAnswerGeneration(**value)
    if isinstance(value, str):
        return GeneralAnswerGeneration(answer=value)
    return GeneralAnswerGeneration()


def _recommendation(legal_basis: list[dict]) -> str:
    if legal_basis:
        return "Use the playbook answer with the cited legal evidence as context, and keep Legal available for interpretation or judgment calls."
    return "Use the cited BMW playbook position as the working answer and escalate red-line or unusual fallback positions to Legal."


def _routing_summary(documents: list[dict[str, str]], legal_basis: list[dict]) -> str:
    parts = ["Ask Donna answered from the complete active BMW playbooks"]
    if documents:
        parts.append(f"{len(documents)} uploaded document(s)")
    if legal_basis:
        parts.append("Otto Schmidt / Legal Data Hub evidence")
    return " and ".join(parts) + "."


def _answer_generation_unavailable() -> str:
    return (
        "I loaded the complete active BMW playbooks, but the OpenAI answer generator is unavailable. "
        "I cannot generate a tailored general-intake answer right now."
    )


def _fetch_thread_messages(thread_id: str) -> list[dict[str, str]]:
    try:
        from app.services.history_repository import HistoryRepository

        history = HistoryRepository().get_item(thread_id)
        if not history:
            return []
        recent = history.get("messages", [])[-8:]
        return [
            {"role": message["role"], "content": message["content"]}
            for message in recent
            if message.get("role") in {"user", "assistant"} and message.get("content")
        ]
    except Exception as exc:
        logger.warning("Could not fetch thread history for %s: %s", thread_id, exc)
        return []
