from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.services.document_ingestion import SUPPORTED_DOCUMENT_EXTENSIONS, extract_document_text
from app.workflows.legal_qa import LegalQARequest, LegalQAResponse, LegalQAWorkflow

logger = logging.getLogger(__name__)


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


class GeneralQuestionWorkflow:
    def __init__(self, legal_qa: LegalQAWorkflow | None = None) -> None:
        self.legal_qa = legal_qa or LegalQAWorkflow()

    async def run(self, request: GeneralQuestionRequest) -> GeneralQuestionResponse:
        documents = _clean_documents(request.uploaded_documents)
        domain = _infer_domain(request)
        intent = _classify_intent(request.question, documents)

        if not documents and _asks_for_playbook_file_summary(request.question):
            playbook_document = _resolve_playbook_document(request.question)
            if playbook_document:
                return await _playbook_file_response(request, playbook_document, domain)
            return _missing_playbook_response(request, domain)

        legal_qa: LegalQAResponse | None = None
        if intent["use_external_sources"]:
            legal_qa = await self.legal_qa.run(
                LegalQARequest(
                    question=request.question.strip(),
                    use_case="ask_donna",
                    contract_type=domain,
                    thread_id=request.thread_id,
                )
            )
            domain = legal_qa.domain

        if documents:
            return await _document_response(
                request=request,
                documents=documents,
                domain=domain,
                intent=intent,
                legal_qa=legal_qa,
            )

        if legal_qa:
            return _from_legal_qa(legal_qa, intent)

        summary = "Ask Donna needs either a question or uploaded document content to answer."
        return GeneralQuestionResponse(
            domain=domain,
            summary=summary,
            recommendation="Ask a specific legal, playbook, or document question.",
            answer_kind="general_answer",
            routing_summary="Ask Donna did not find a legal, playbook, or document source to query.",
            routed_agents=[],
            selected_source_ids=[],
        )


async def _document_response(
    *,
    request: GeneralQuestionRequest,
    documents: list[dict[str, str]],
    domain: str,
    intent: dict[str, Any],
    legal_qa: LegalQAResponse | None,
) -> GeneralQuestionResponse:
    answer_kind = intent["answer_kind"]
    if answer_kind == "document_route_pending":
        answer_kind = "document_summary" if intent["asks_summary"] else "document_qa"

    source_context = _document_source_context(request.question, documents, answer_kind, intent["asks_summary"])
    ai_summary = await _openai_general_answer(
        question=request.question,
        context=request.context,
        documents=documents,
        source_context=source_context,
        legal_qa=legal_qa,
        answer_kind=answer_kind,
        thread_id=request.thread_id,
    )
    selected_source_ids = _selected_source_ids(documents=documents, legal_qa=legal_qa, domain=domain)
    return GeneralQuestionResponse(
        domain=legal_qa.domain if legal_qa else domain,
        summary=ai_summary or _answer_generation_unavailable(answer_kind),
        recommendation=_document_recommendation(answer_kind, legal_qa),
        company_basis=legal_qa.company_basis if legal_qa else [],
        legal_basis=legal_qa.legal_basis if legal_qa else [],
        escalate=legal_qa.escalate if legal_qa else False,
        ai_generated=bool(ai_summary),
        answer_kind=answer_kind,
        playbook_row_count=legal_qa.playbook_row_count if legal_qa else 0,
        document_count=len(documents),
        routed_agents=_routed_agents(documents=documents, legal_qa=legal_qa),
        routing_summary=_routing_summary(answer_kind, legal_qa, len(documents)),
        selected_source_ids=selected_source_ids,
    )


def _from_legal_qa(legal_qa: LegalQAResponse, intent: dict[str, Any]) -> GeneralQuestionResponse:
    answer_kind = legal_qa.answer_kind
    if answer_kind == "rule_specific":
        if intent["wants_legal"] and not intent["wants_playbook"]:
            answer_kind = "legal_lookup"
        elif intent["wants_playbook"] and not intent["wants_legal"]:
            answer_kind = "playbook_lookup"

    return GeneralQuestionResponse(
        domain=legal_qa.domain,
        summary=legal_qa.summary,
        recommendation=legal_qa.recommendation,
        company_basis=legal_qa.company_basis,
        legal_basis=legal_qa.legal_basis,
        escalate=legal_qa.escalate,
        ai_generated=legal_qa.ai_generated,
        answer_kind=answer_kind,
        playbook_row_count=legal_qa.playbook_row_count,
        document_count=0,
        routed_agents=["legal_qa"],
        routing_summary=_routing_summary(answer_kind, legal_qa, 0),
        selected_source_ids=_selected_source_ids(documents=[], legal_qa=legal_qa, domain=legal_qa.domain),
    )


async def _playbook_file_response(
    request: GeneralQuestionRequest,
    playbook_document: dict[str, Any],
    domain: str,
) -> GeneralQuestionResponse:
    document = {
        "filename": str(playbook_document["path"].name),
        "text": str(playbook_document["text"]),
    }
    source_context = _document_source_context(request.question, [document], "playbook_file_summary", asks_summary=True)
    ai_summary = await _openai_general_answer(
        question=request.question,
        context=request.context,
        documents=[document],
        source_context=source_context,
        legal_qa=None,
        answer_kind="playbook_file_summary",
        thread_id=request.thread_id,
    )
    relative_path = str(playbook_document["path"].relative_to(_playbook_root()))
    company_basis = [
        {
            "source": "Company playbook file",
            "citation": relative_path,
            "quote": str(playbook_document["text"])[:500],
            "severity": "info",
        }
    ]
    return GeneralQuestionResponse(
        domain=domain,
        summary=ai_summary or _answer_generation_unavailable("playbook_file_summary"),
        recommendation="Use this as a working summary of the company playbook document. Upload a newer playbook if this is not the file you meant.",
        company_basis=company_basis,
        legal_basis=[],
        escalate=False,
        ai_generated=bool(ai_summary),
        answer_kind="playbook_file_summary",
        playbook_row_count=0,
        document_count=0,
        routed_agents=["playbook_document_reader"],
        routing_summary=f"Ask Donna found and summarized the company playbook file {relative_path}.",
        selected_source_ids=["company_playbook_file"],
    )


def _missing_playbook_response(request: GeneralQuestionRequest, domain: str) -> GeneralQuestionResponse:
    target = _playbook_target_label(request.question)
    return GeneralQuestionResponse(
        domain=domain,
        summary=(
            f"I could not find a company playbook matching {target} in data/playbook. "
            "Please upload the playbook document or add it to the company playbook folder before I summarize it."
        ),
        recommendation="Upload the requested playbook or add it to data/playbook, then ask Donna to summarize it again.",
        company_basis=[],
        legal_basis=[],
        escalate=False,
        ai_generated=False,
        answer_kind="playbook_file_missing",
        playbook_row_count=0,
        document_count=0,
        routed_agents=["playbook_document_reader"],
        routing_summary=f"Ask Donna searched data/playbook for {target} and did not find a close company playbook match.",
        selected_source_ids=[],
    )


def _classify_intent(question: str, documents: list[dict[str, str]]) -> dict[str, Any]:
    normalized = _normalize(question)
    wants_legal = any(signal in normalized for signal in _LEGAL_SIGNALS)
    wants_playbook = any(signal in normalized for signal in _PLAYBOOK_SIGNALS)
    asks_summary = any(signal in normalized for signal in _SUMMARY_SIGNALS)
    asks_document = bool(documents) and (
        asks_summary
        or any(signal in normalized for signal in _DOCUMENT_SIGNALS)
        or not (wants_legal or wants_playbook)
    )

    answer_kind = "document_route_pending"
    if documents and asks_summary and not (wants_legal or wants_playbook):
        answer_kind = "document_summary"
    elif documents and wants_legal:
        answer_kind = "hybrid_document_legal"
    elif documents and wants_playbook:
        answer_kind = "hybrid_document_playbook"
    elif documents and asks_document:
        answer_kind = "document_qa"

    use_external_sources = wants_legal or wants_playbook or (not documents)
    return {
        "answer_kind": answer_kind,
        "asks_summary": asks_summary,
        "asks_document": asks_document,
        "wants_legal": wants_legal,
        "wants_playbook": wants_playbook,
        "use_external_sources": use_external_sources,
    }


def _asks_for_playbook_file_summary(question: str) -> bool:
    normalized = _normalize(question)
    asks_summary = any(signal in normalized for signal in _SUMMARY_SIGNALS)
    if not asks_summary:
        return False
    if "playbook" in normalized:
        return True
    return _mentions_dpa(normalized) or _mentions_procurement(normalized)


def _resolve_playbook_document(question: str) -> dict[str, Any] | None:
    root = _playbook_root()
    if not root.exists():
        return None

    normalized = _normalize(question)
    if _mentions_dpa(normalized):
        dpa_path = root / "dpa.docx"
        if dpa_path.exists():
            return _load_playbook_document(dpa_path)

    candidates = _candidate_playbook_files(root)
    if not candidates:
        return None

    query_terms = _playbook_query_terms(question)
    if _mentions_procurement(normalized):
        query_terms |= {"procurement", "purchasing", "purchase"}
    if not query_terms:
        return None

    scored: list[tuple[float, Path]] = []
    for path in candidates:
        file_terms = _playbook_query_terms(path.stem.replace("_", " ").replace("-", " "))
        overlap = query_terms & file_terms
        if not overlap:
            continue
        score = float(len(overlap))
        if path.suffix.lower() == ".docx":
            score += 0.25
        if path.name.lower() == "dpa.docx" and _mentions_dpa(normalized):
            score += 10
        scored.append((score, path))

    if not scored:
        return None
    best_score, best_path = sorted(scored, key=lambda item: item[0], reverse=True)[0]
    if best_score < 1:
        return None
    return _load_playbook_document(best_path)


def _load_playbook_document(path: Path) -> dict[str, Any] | None:
    try:
        text = extract_document_text(path.name, path.read_bytes()).strip()
    except Exception as exc:
        logger.warning("Could not read playbook document %s: %s", path, exc)
        return None
    if not text:
        return None
    return {"path": path, "text": text}


def _candidate_playbook_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS
        and not path.name.startswith(".")
        and not path.name.endswith(":Zone.Identifier")
    )


def _playbook_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "playbook"


def _playbook_target_label(question: str) -> str:
    normalized = _normalize(question)
    if _mentions_dpa(normalized):
        return "the DPA playbook"
    if _mentions_procurement(normalized):
        return "the procurement or purchasing playbook"
    terms = sorted(_playbook_query_terms(question))
    return f"'{', '.join(terms)}'" if terms else "the requested playbook"


def _mentions_dpa(normalized_question: str) -> bool:
    return any(
        term in normalized_question
        for term in (
            "dpa",
            "data processing agreement",
            "data protection agreement",
            "data protection playbook",
            "datenschutz",
        )
    )


def _mentions_procurement(normalized_question: str) -> bool:
    return any(term in normalized_question for term in ("procurement", "purchasing", "purchase"))


def _playbook_query_terms(value: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", value.lower())
        if len(token) >= 3
    }
    return tokens - _PLAYBOOK_MATCH_STOP_WORDS


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


def _document_source_context(
    question: str,
    documents: list[dict[str, str]],
    answer_kind: str,
    asks_summary: bool,
) -> str:
    if answer_kind in {"document_summary", "playbook_file_summary"} or asks_summary:
        return "Use the uploaded/source document text directly. Generate the summary according to the user's requested audience, format, and level of detail."
    return _answer_from_documents(question, documents)


def _answer_from_documents(question: str, documents: list[dict[str, str]]) -> str:
    sections = ["Answer from uploaded document content:"]
    for document in documents:
        snippets = _relevant_snippets(question, document["text"], limit=4)
        sections.append(f"\n{document['filename']}")
        if snippets:
            for snippet in snippets:
                sections.append(f"- {snippet}")
        else:
            sections.append("- I could not find a direct passage matching the question in this document.")
    return "\n".join(sections)


def _answer_generation_unavailable(answer_kind: str) -> str:
    source_label = "source context"
    if answer_kind == "playbook_file_summary":
        source_label = "company playbook document"
    elif answer_kind in {"document_summary", "document_qa"}:
        source_label = "uploaded document"
    elif answer_kind == "hybrid_document_legal":
        source_label = "uploaded document and legal evidence"
    elif answer_kind == "hybrid_document_playbook":
        source_label = "uploaded document and BMW playbook context"
    return (
        f"I found the relevant {source_label}, but the OpenAI answer generator is unavailable. "
        "I cannot generate a tailored answer from the source material right now."
    )


async def _openai_general_answer(
    *,
    question: str,
    context: str,
    documents: list[dict[str, str]],
    source_context: str,
    legal_qa: LegalQAResponse | None,
    answer_kind: str,
    thread_id: str | None,
) -> str:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        return ""

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package is not installed; using deterministic document answer")
        return ""

    system_prompt = "\n".join(
        [
            "You are Ask Donna, BMW Group's in-house legal assistant.",
            "Answer only from the uploaded document excerpts, BMW playbook context, and legal evidence provided.",
            "Generate a fresh answer tailored to the user's request; do not follow a fixed summary template.",
            "If the user asks for a summary, adapt the structure, depth, and emphasis to the user's wording.",
            "If live legal evidence is marked as fallback, say it is fallback evidence.",
            "Do not present yourself as replacing Legal; flag where legal judgment is needed.",
            "Keep summaries practical and preserve source names such as uploaded filenames, playbook IDs, and legal citations.",
        ]
    )
    context_parts = [_format_documents_for_prompt(documents)]
    if source_context:
        context_parts.append("\n## Retrieved Source Context\n" + source_context)
    if context:
        context_parts.append("\n## Business Context\n" + context.strip())
    if legal_qa:
        if legal_qa.recommendation:
            context_parts.append("\n## Recommendation\n" + legal_qa.recommendation)
        if legal_qa.legal_basis:
            context_parts.append("\n## Legal Evidence\n" + _format_legal_basis(legal_qa.legal_basis))
        if legal_qa.company_basis:
            context_parts.append("\n## BMW Playbook Evidence\n" + _format_company_basis(legal_qa.company_basis))

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if thread_id:
        messages.extend(_fetch_thread_messages(thread_id))
    messages.append(
        {
            "role": "user",
            "content": "\n".join(context_parts) + f"\n\nUser request: {question}\nAnswer kind: {answer_kind}",
        }
    )

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            max_tokens=1400,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("OpenAI document answer failed; using deterministic answer: %s", exc)
        return ""


def _format_documents_for_prompt(documents: list[dict[str, str]]) -> str:
    parts = ["## Uploaded Documents"]
    for document in documents:
        parts.append(f"\n### {document['filename']}\n{document['text'][:6000]}")
    return "\n".join(parts)


def _format_legal_basis(legal_basis: list[dict]) -> str:
    lines: list[str] = []
    for item in legal_basis[:5]:
        mode = item.get("retrieval_mode")
        mode_note = "fallback evidence" if mode == "fallback" else "live evidence"
        citation = item.get("citation") or item.get("title") or "Legal source"
        quote = item.get("quote") or item.get("excerpt") or ""
        lines.append(f"- {citation} ({mode_note}): {quote}")
    return "\n".join(lines)


def _format_company_basis(company_basis: list[dict]) -> str:
    return "\n".join(
        f"- {item.get('citation', 'BMW playbook')}: {item.get('quote', '')}"
        for item in company_basis[:8]
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


def _document_recommendation(answer_kind: str, legal_qa: LegalQAResponse | None) -> str:
    if legal_qa and legal_qa.escalate:
        return "Escalate to Legal before relying on this position."
    if legal_qa and legal_qa.recommendation:
        return legal_qa.recommendation
    if answer_kind == "document_summary":
        return "Use this as a working summary and ask a follow-up question for any clause or legal issue."
    return "Use this answer as document context; run contract review for formal clause risk assessment."


def _selected_source_ids(
    *,
    documents: list[dict[str, str]],
    legal_qa: LegalQAResponse | None,
    domain: str,
) -> list[str]:
    source_ids: list[str] = []
    if legal_qa and legal_qa.company_basis:
        source_ids.append("bmw_litigation_playbook" if domain == "litigation" else "bmw_data_protection_playbook")
    if legal_qa and legal_qa.legal_basis:
        source_ids.append("legal_data_hub")
    if documents:
        source_ids.append("uploaded_bundle")
    return list(dict.fromkeys(source_ids))


def _routed_agents(*, documents: list[dict[str, str]], legal_qa: LegalQAResponse | None) -> list[str]:
    routed: list[str] = []
    if documents:
        routed.append("document_summarizer")
    if legal_qa:
        routed.append("legal_qa")
    return routed


def _routing_summary(answer_kind: str, legal_qa: LegalQAResponse | None, document_count: int) -> str:
    if answer_kind == "playbook_file_summary":
        return "Ask Donna summarized a company playbook document from data/playbook."
    if answer_kind == "playbook_file_missing":
        return "Ask Donna searched data/playbook but did not find a close company playbook match."
    if answer_kind == "document_summary":
        return f"Ask Donna summarized {document_count} uploaded document(s) without running a legal lookup."
    if answer_kind == "document_qa":
        return f"Ask Donna answered from {document_count} uploaded document(s) without running a legal lookup."
    if answer_kind == "hybrid_document_legal":
        return f"Ask Donna used {document_count} uploaded document(s) and checked German/EU legal evidence."
    if answer_kind == "hybrid_document_playbook":
        return f"Ask Donna used {document_count} uploaded document(s) and checked the BMW playbook."
    if answer_kind == "legal_lookup":
        return "Ask Donna treated this as a German/EU law question and queried Otto Schmidt / Legal Data Hub."
    if answer_kind == "playbook_lookup":
        return "Ask Donna treated this as a BMW playbook question and used internal playbook rows."
    if legal_qa:
        return "Ask Donna treated this as a general legal/playbook question and selected sources automatically."
    return "Ask Donna answered the general question from the available context."


def _infer_domain(request: GeneralQuestionRequest) -> str:
    supplied = (request.contract_type or "").strip()
    if supplied and supplied != "general":
        return supplied
    text = " ".join(
        [
            request.question,
            request.context,
            " ".join(document.get("text", "")[:1200] for document in request.uploaded_documents),
        ]
    ).lower()
    litigation_terms = ("litigation", "settlement", "liability", "indemnity", "court", "arbitration", "legal hold")
    if any(term in text for term in litigation_terms):
        return "litigation"
    return "data_protection"


def _document_sentences(text: str) -> list[str]:
    compact = " ".join(text.split())
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", compact) if item.strip()]
    if len(sentences) > 1:
        return [sentence[:500] for sentence in sentences]
    paragraphs = [item.strip() for item in text.split("\n") if item.strip()]
    return [paragraph[:500] for paragraph in paragraphs[:8]]


def _relevant_snippets(question: str, text: str, limit: int) -> list[str]:
    terms = _query_terms(question)
    sentences = _document_sentences(text)
    if not sentences:
        return []
    if not terms:
        return sentences[:limit]

    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        normalized = sentence.lower()
        score = sum(1 for term in terms if term in normalized)
        if score:
            scored.append((score, -index, sentence))
    if not scored:
        return sentences[: min(limit, len(sentences))]
    return [
        sentence
        for _, _, sentence in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[:limit]
    ]


def _query_terms(question: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9§]+", question.lower())
        if len(token) > 3 and token not in _STOP_WORDS
    }


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("/", " ").replace("-", " ").split())


_LEGAL_SIGNALS = {
    "german law",
    "eu law",
    "gdpr",
    "bgb",
    "article",
    "art.",
    "§",
    "court ruling",
    "court decision",
    "case law",
    "legal basis",
    "statutory",
    "regulation",
    "directive",
    "rechtsprechung",
    "gesetze",
    "precedent",
    "ruling",
    "what does the law",
    "legally required",
    "legally permitted",
    "is it legal",
}

_PLAYBOOK_SIGNALS = {
    "bmw",
    "playbook",
    "our position",
    "company position",
    "internal policy",
    "red line",
    "fallback position",
    "standard position",
    "approved clause",
    "preferred clause",
}

_DOCUMENT_SIGNALS = {
    "document",
    "upload",
    "uploaded",
    "file",
    "clause",
    "this says",
    "what does this",
    "in this",
    "from this",
    "according to this",
}

_SUMMARY_SIGNALS = {
    "summarize",
    "summarise",
    "summary",
    "overview",
    "what is this document",
    "what is this file",
    "what is the document",
    "what is the file",
}

_STOP_WORDS = {
    "about",
    "according",
    "answer",
    "bmw",
    "clause",
    "does",
    "document",
    "file",
    "from",
    "have",
    "legal",
    "please",
    "question",
    "should",
    "summarize",
    "summarise",
    "tell",
    "that",
    "this",
    "uploaded",
    "what",
    "with",
}

_PLAYBOOK_MATCH_STOP_WORDS = _STOP_WORDS | {
    "agreement",
    "bmw",
    "company",
    "data",
    "document",
    "file",
    "for",
    "group",
    "negotiation",
    "playbook",
    "protection",
    "processing",
    "summarize",
    "summarise",
    "summary",
    "the",
}
