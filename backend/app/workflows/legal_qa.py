from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.services.legal_data_hub import LegalDataHubClient
from app.services.playbook_repository import load_playbook_rows, playbook_file_label, playbook_source_label

logger = logging.getLogger(__name__)


class LegalQARequest(BaseModel):
    question: str
    use_case: str | None = None
    contract_type: str | None = None
    thread_id: str | None = None  # passed for multi-turn conversation history


class LegalQAResponse(BaseModel):
    domain: str
    summary: str
    recommendation: str
    company_basis: list[dict]
    legal_basis: list[dict]
    escalate: bool
    ai_generated: bool = False  # True when OpenAI generated the summary
    answer_kind: str = "rule_specific"
    playbook_row_count: int = 0


class LegalQAWorkflow:
    def __init__(self, legal_data_hub: LegalDataHubClient | None = None) -> None:
        self.legal_data_hub = legal_data_hub or LegalDataHubClient()

    async def run(self, request: LegalQARequest) -> LegalQAResponse:
        domain = _infer_domain(request)
        want_playbook, want_legal = _detect_query_intent(request.question, request.use_case or "")
        answer_kind = _classify_answer_kind(request.question, want_playbook)

        # Full playbook for LLM context; keyword scoring for structured company_basis
        all_rows = load_playbook_rows(domain) if want_playbook else []
        if answer_kind == "playbook_summary" and all_rows:
            selected_rows, matched_playbook_terms = all_rows, True
        else:
            selected_rows, matched_playbook_terms = (
                _select_playbook_rows(request.question, domain) if want_playbook else ([], False)
            )

        legal_basis: list[dict] = []
        if want_legal:
            raw_legal = await self.legal_data_hub.search_evidence(request.question, domain=domain)
            legal_basis = [_normalize_legal_basis(item) for item in raw_legal[:3]]

        company_basis = _company_basis_from_rows(selected_rows, domain) if selected_rows else []
        escalate = (
            False
            if answer_kind in {"playbook_summary", "terminology_explainer"}
            else _requires_escalation(request.question, selected_rows, matched_playbook_terms)
        )
        ai_summary = await _openai_answer(
            question=request.question,
            all_rows=all_rows,
            legal_basis=legal_basis,
            thread_id=request.thread_id,
            want_playbook=want_playbook,
            want_legal=want_legal,
            answer_kind=answer_kind,
        )
        summary = ai_summary or _answer_generation_unavailable(
            answer_kind=answer_kind,
            want_playbook=want_playbook,
            want_legal=want_legal,
            has_playbook=bool(company_basis),
            has_legal=bool(legal_basis),
        )

        return LegalQAResponse(
            domain=domain,
            summary=summary,
            recommendation=_recommendation(selected_rows, legal_basis, escalate, answer_kind),
            company_basis=company_basis,
            legal_basis=legal_basis,
            escalate=escalate,
            ai_generated=bool(ai_summary),
            answer_kind=answer_kind,
            playbook_row_count=len(selected_rows) if want_playbook else 0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI integration
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_CORE = """\
You are Ask Donna, BMW Group's in-house legal assistant specialising in contract negotiation, \
data protection, and litigation support. You help BMW's legal and business teams.

Your responsibilities:
- Answer questions about BMW's internal negotiation positions using the provided playbook
- Explain applicable German and EU law, citing specific articles when relevant
- Flag RED LINES (positions BMW never accepts) clearly and prominently
- State when an issue must be escalated to the Legal team
- Translate complex legal terms into plain language inline when they first appear
- When asked to summarise a document or all rules, cover every rule provided — do not omit any

Style:
- Reference BMW playbook rules by their ID (e.g. DPA-001) when citing BMW's position
- Use bullet points for lists of issues or rules
- Keep answers focused and practical — this is an operational tool, not a textbook
- Draw only on the playbook and legal evidence provided below; do not invent BMW policies
"""


async def _openai_answer(
    *,
    question: str,
    all_rows: list[dict[str, str]],
    legal_basis: list[dict],
    thread_id: str | None,
    want_playbook: bool,
    want_legal: bool,
    answer_kind: str,
) -> str:
    """Call OpenAI with full playbook context and return a natural language answer.

    Returns an empty string if OpenAI is not configured or the call fails.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.openai_api_key:
        return ""

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package is not installed; falling back to template summary")
        return ""

    # Build system prompt: role + playbook context + legal evidence
    system_parts = [_SYSTEM_PROMPT_CORE]

    if want_playbook and all_rows:
        system_parts.append(
            "\n## BMW Negotiation Playbook (complete)\n\n"
            + _format_playbook_for_context(all_rows)
        )
    elif want_playbook:
        system_parts.append("\n## BMW Negotiation Playbook\nNo playbook rules were found for this domain.")

    if want_legal and legal_basis:
        system_parts.append(
            "\n## German/EU Legal Evidence\n\n"
            + _format_legal_basis_for_context(legal_basis)
        )
    elif want_legal:
        system_parts.append("\n## German/EU Legal Evidence\nNo live legal evidence was retrieved for this query.")

    system_parts.append(
        "\n## Answer Instructions\n"
        "Generate a fresh answer tailored to the user's exact request. Do not use a fixed template. "
        "Base the answer only on the provided playbook and legal evidence. If the available source context "
        "does not support part of the request, say so clearly."
    )

    system_prompt = "\n".join(system_parts)

    # Build message list: system + conversation history + current question
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if thread_id:
        messages.extend(_fetch_thread_messages(thread_id))
    messages.append({"role": "user", "content": question})

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.responses.create(
            model=settings.openai_model,
            input=messages,
            max_output_tokens=1800 if answer_kind == "playbook_summary" else 1000,
            reasoning={"effort": settings.openai_reasoning_effort},
        )
        return response.output_text or ""
    except Exception as exc:
        logger.warning("OpenAI call failed: %s", exc)
        return ""


def _format_playbook_for_context(rows: list[dict[str, str]]) -> str:
    """Serialize all playbook rows as readable structured text for the LLM system prompt."""
    parts: list[str] = []
    for row in rows:
        rule_id = row.get("id", "")
        title = row.get("title", "")
        severity = (row.get("severity") or "medium").upper()
        lines = [f"**{rule_id} — {title}** [{severity}]"]

        for key, label in [
            ("default", "BMW standard position"),
            ("preferred_position", "Preferred position"),
            ("why_it_matters", "Why it matters"),
            ("fallback_1", "Acceptable fallback 1"),
            ("fallback_2", "Acceptable fallback 2"),
            ("red_line", "Red line (never accept)"),
            ("escalation_trigger", "Escalation trigger"),
            ("legal_basis", "Legal basis"),
            ("approved_fix", "Approved fix"),
        ]:
            value = row.get(key, "").strip()
            if value:
                lines.append(f"{label}: {value}")

        parts.append("\n".join(lines))

    return "\n\n---\n\n".join(parts)


def _format_legal_basis_for_context(legal_basis: list[dict]) -> str:
    """Serialize legal hub evidence items as readable text for the LLM system prompt."""
    parts: list[str] = []
    for item in legal_basis:
        citation = item.get("citation", "Legal source")
        source = item.get("source", "")
        quote = (item.get("quote") or item.get("excerpt") or "").strip()
        retrieval = item.get("retrieval_mode", "")
        mode_note = " [fallback evidence]" if retrieval == "fallback" else " [Otto Schmidt live]"

        lines = [f"**{citation}**{mode_note}"]
        if source and source not in citation:
            lines.append(f"Source: {source}")
        if quote:
            lines.append(f'"{quote[:500]}"')

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _fetch_thread_messages(thread_id: str) -> list[dict[str, str]]:
    """Return the last 8 messages from a history thread (4 user+assistant turns)."""
    try:
        from app.services.history_repository import HistoryRepository
        history = HistoryRepository().get_item(thread_id)
        if not history:
            return []
        recent = history.get("messages", [])[-8:]
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in recent
            if msg.get("role") in ("user", "assistant") and msg.get("content")
        ]
    except Exception as exc:
        logger.warning("Could not fetch thread history for %s: %s", thread_id, exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Intent detection
# ─────────────────────────────────────────────────────────────────────────────

# Signals that the user is asking specifically about the BMW/company playbook position
_PLAYBOOK_SIGNALS = {
    "bmw",
    "playbook",
    "our position",
    "company position",
    "company policy",
    "internal policy",
    "red line",
    "fallback position",
    "standard position",
    "approved clause",
    "preferred clause",
    "bmw group",
    "bmw standard",
    "what does bmw",
    "bmw require",
    "bmw accept",
    "bmw allow",
}

# Signals that the user is asking specifically about German/EU law, statutes, or rulings
_LEGAL_SIGNALS = {
    "german law",
    "eu law",
    "gdpr",
    "article 28",
    "article 32",
    "article 44",
    "bürgerliches gesetzbuch",
    "bgb",
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
    "bundesgerichtshof",
    "bgh",
    "oberlandesgericht",
    "olg",
    "what does the law",
    "legally required",
    "legally permitted",
    "is it legal",
    "german court",
}

# Signals that the question is about contract negotiation/positions (not a pure statute lookup).
# When present alongside legal signals, the playbook is also consulted.
_CONTRACT_NEGOTIATION_SIGNALS = {
    "waive", "waiver", "accept", "allow", "must", "can a",
    "can we", "can the", "acceptable", "clause",
    "supplier", "vendor", "in a contract", "in the contract",
    "negotiate", "sign", "agree to", "permitted", "obligated",
}

_PLAYBOOK_SUMMARY_SIGNALS = {
    "summarize",
    "summarise",
    "summary",
    "overview",
    "explain",
    "walk me through",
    "plain words",
    "simple words",
    "non legal",
    "non-legal",
    "business people",
    "all rules",
    "entire playbook",
}

_PLAYBOOK_SUMMARY_TARGETS = {
    "dpa playbook",
    "data protection playbook",
    "bmw group dpa",
    "negotiation playbook",
    "playbook document",
    "entire playbook",
    "all rules",
}

_TERMINOLOGY_SIGNALS = {
    "what is",
    "what are",
    "what does",
    "meaning",
    "mean",
    "definition",
    "define",
    "terminology",
    "jargon",
    "simple words",
    "plain language",
    "plain english",
}


def _detect_query_intent(question: str, use_case: str) -> tuple[bool, bool]:
    """Return (want_playbook, want_legal_hub).

    Contract review and intake always use both sources.
    General questions are routed to the source(s) the question clearly targets.
    If a question mentions legal terms but also has contract/negotiation context
    (e.g. "can a supplier waive GDPR rights?"), both sources are used because
    the playbook position is relevant alongside the legal answer.
    If a question is a pure statute lookup with no contract context, only the
    legal hub is queried.
    """
    if use_case in ("legal_intake", "contract_review"):
        return True, True

    q = question.lower()
    wants_playbook = any(signal in q for signal in _PLAYBOOK_SIGNALS)
    wants_legal = any(signal in q for signal in _LEGAL_SIGNALS)
    wants_contract_context = any(signal in q for signal in _CONTRACT_NEGOTIATION_SIGNALS)

    # Explicitly BMW/playbook-only question
    if wants_playbook and not wants_legal:
        return True, False

    # Legal signal present — include playbook if there is also contract/negotiation context
    if wants_legal and not wants_playbook:
        if wants_contract_context:
            return True, True
        return False, True

    # Unclear or both mentioned — use both (safest default)
    return True, True


def _classify_answer_kind(question: str, want_playbook: bool) -> str:
    if not want_playbook:
        return "legal_lookup"

    normalized = _normalized_question(question)
    if _asks_for_playbook_summary(normalized):
        return "playbook_summary"
    if _asks_for_terminology(normalized):
        return "terminology_explainer"
    return "rule_specific"


def _normalized_question(question: str) -> str:
    return " ".join(question.lower().replace("/", " ").replace("-", " ").split())


def _asks_for_playbook_summary(normalized_question: str) -> bool:
    mentions_summary_target = any(target in normalized_question for target in _PLAYBOOK_SUMMARY_TARGETS)
    asks_to_summarize = any(signal in normalized_question for signal in _PLAYBOOK_SUMMARY_SIGNALS)
    if mentions_summary_target and asks_to_summarize:
        return True
    if "playbook" in normalized_question and "what is" in normalized_question:
        return True
    return False


def _asks_for_terminology(normalized_question: str) -> bool:
    if any(signal in normalized_question for signal in ("bmw require", "bmw accept", "bmw allow")):
        return False
    if not any(signal in normalized_question for signal in _TERMINOLOGY_SIGNALS):
        return False
    return any(term in normalized_question for term in _JARGON_GLOSSARY)


# ─────────────────────────────────────────────────────────────────────────────
# Domain inference
# ─────────────────────────────────────────────────────────────────────────────

def _infer_domain(request: LegalQARequest) -> str:
    supplied = (request.contract_type or "").strip()
    if supplied and supplied != "general":
        return supplied
    question = request.question.lower()
    litigation_terms = ("litigation", "settlement", "liability", "indemnity", "court", "arbitration", "legal hold")
    if any(term in question for term in litigation_terms):
        return "litigation"
    return "data_protection"


# ─────────────────────────────────────────────────────────────────────────────
# Playbook helpers
# ─────────────────────────────────────────────────────────────────────────────

_PLAYBOOK_QUERY_STOP_WORDS = {
    "about",
    "business",
    "could",
    "document",
    "donna",
    "easy",
    "explain",
    "general",
    "group",
    "legal",
    "non",
    "people",
    "plain",
    "playbook",
    "question",
    "simple",
    "summarise",
    "summarize",
    "summary",
    "tell",
    "through",
    "user",
    "what",
    "words",
}


def _company_basis(question: str, domain: str) -> list[dict]:
    selected, _ = _select_playbook_rows(question, domain)
    return _company_basis_from_rows(selected, domain)


def _select_playbook_rows(question: str, domain: str) -> tuple[list[dict[str, str]], bool]:
    rows = load_playbook_rows(domain)
    if not rows:
        return [], False

    normalized_question = question.lower()
    terms = {
        term.strip(".,;:?!()[]")
        for term in normalized_question.replace("/", " ").replace("-", " ").split()
        if len(term) > 3
    } - _PLAYBOOK_QUERY_STOP_WORDS
    scored: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        searchable = " ".join(
            str(row.get(key, ""))
            for key in (
                "id",
                "title",
                "default",
                "preferred_position",
                "fallback_1",
                "fallback_2",
                "red_line",
                "escalation_trigger",
                "legal_basis",
            )
        ).lower()
        score = sum(1 for term in terms if term in searchable)
        if terms & {"waive", "waiver", "waived"} and any(term in searchable for term in ("waive", "waiver", "waived")):
            score += 5
            if "data subject rights" in normalized_question and "data subject rights" in searchable:
                score += 8
            if "rights cannot be waived" in searchable or "statutory data subject rights" in searchable:
                score += 8
        if "unlimited" in terms and "unlimited" in searchable:
            score += 5
        if {"breach", "72"}.issubset(terms) and "breach" in searchable:
            score += 3
        if score:
            scored.append((score, row))
    if scored:
        return [row for _, row in sorted(scored, key=lambda item: (item[0], _severity_score(item[1])), reverse=True)[:3]], True
    return rows[:3], False


def _company_basis_from_rows(rows: list[dict[str, str]], domain: str) -> list[dict]:
    if not rows:
        return [
            {
                "source": "BMW playbook",
                "citation": "Fallback company rule unavailable",
                "quote": "High-risk deviations from BMW defaults must be escalated to legal.",
            }
        ]

    return [
        {
            "source": f"{playbook_source_label(domain)}: {playbook_file_label(domain)}",
            "citation": f"{row.get('id', 'unknown')} - {row.get('title', 'Untitled rule')}",
            "quote": row.get("default") or row.get("preferred_position") or "",
            "severity": row.get("severity"),
            "approved_fix": row.get("approved_fix"),
        }
        for row in rows
    ]


def _load_playbook_rows(domain: str) -> list[dict[str, str]]:
    return load_playbook_rows(domain)


def _severity_score(row: dict[str, str]) -> int:
    return {"blocker": 3, "high": 2, "medium": 1, "low": 0}.get((row.get("severity") or "").lower(), 0)


def _recommendation(rows: list[dict[str, str]], legal_basis: list[dict], escalate: bool, answer_kind: str) -> str:
    if answer_kind == "playbook_summary":
        return "Use this overview to identify the DPA topic in the supplier wording, then apply the cited BMW rule or escalate red lines to Legal."
    if answer_kind == "terminology_explainer":
        return "Use the plain-language definition to understand the issue, then check the relevant BMW playbook rule before negotiating."
    if rows:
        rule = rows[0]
        fix = rule.get("approved_fix") or rule.get("preferred_position") or rule.get("default")
        if fix:
            prefix = "Escalate to Legal and use this as the proposed fix" if escalate else "Use this as the working position"
            return f"{prefix}: {fix}"
    if escalate:
        return "Escalate to Legal before the business team proceeds."
    return "Use the cited playbook rule as the internal default and keep legal review available for ambiguity or high-value deviations."


def _requires_escalation(question: str, rows: list[dict[str, str]], matched_playbook_terms: bool) -> bool:
    normalized = question.lower()
    explicit_triggers = (
        "unlimited",
        "waive",
        "waiver",
        "illegal",
        "blocker",
        "third-country",
        "third country",
        "without scc",
        "72 hours",
        "settlement authority",
    )
    if any(term in normalized for term in explicit_triggers):
        return True
    if not matched_playbook_terms:
        return False
    return any((row.get("severity") or "").lower() in {"blocker", "high"} for row in rows[:1])


def _normalize_legal_basis(item: dict) -> dict:
    normalized = dict(item)
    source = str(normalized.get("source") or "")
    if not source:
        normalized["source"] = "Otto Schmidt / Legal Data Hub"
    elif "fallback" in source.lower() and "Otto Schmidt" not in source:
        normalized["source"] = f"Otto Schmidt / {source}"
    return normalized


def _answer_generation_unavailable(
    *,
    answer_kind: str,
    want_playbook: bool,
    want_legal: bool,
    has_playbook: bool,
    has_legal: bool,
) -> str:
    if (want_playbook and has_playbook) or (want_legal and has_legal):
        source_parts: list[str] = []
        if want_playbook and has_playbook:
            source_parts.append("BMW playbook context")
        if want_legal and has_legal:
            source_parts.append("German/EU legal evidence")
        sources = " and ".join(source_parts)
        return (
            f"I found the relevant {sources}, but the OpenAI answer generator is unavailable. "
            "I cannot generate a tailored answer from the source material right now."
        )
    if answer_kind == "legal_lookup":
        return "I could not retrieve legal evidence for this question, so I cannot generate a supported legal answer."
    if answer_kind in {"playbook_summary", "rule_specific", "terminology_explainer"}:
        return "I could not find supporting BMW playbook context for this question, so I cannot generate a supported answer."
    return "I could not find enough supporting source material to generate an answer."


# ─────────────────────────────────────────────────────────────────────────────
# Plain-language jargon helper (used by template fallback)
# ─────────────────────────────────────────────────────────────────────────────

_JARGON_GLOSSARY: dict[str, str] = {
    "processor": "processor (the company that handles data on behalf of another)",
    "controller": "controller (the company that decides how and why data is processed)",
    "data subject": "data subject (the individual whose personal data is being used)",
    "subprocessor": "subprocessor (a third party the processor sub-contracts data work to)",
    "tom": "technical and organisational measures / TOMs (security safeguards like encryption and access controls)",
    "toms": "technical and organisational measures / TOMs (security safeguards like encryption and access controls)",
    "scc": "Standard Contractual Clauses / SCCs (EU-approved contract templates required when transferring data outside the EEA)",
    "sccs": "Standard Contractual Clauses / SCCs (EU-approved contract templates required when transferring data outside the EEA)",
    "tia": "Transfer Impact Assessment / TIA (risk assessment required before sending EU personal data to high-risk countries)",
    "dpa": "Data Processing Agreement / DPA (contract required by GDPR Art. 28 when a processor handles data for a controller)",
    "gdpr": "GDPR (EU General Data Protection Regulation — the main EU privacy law)",
    "bgb": "BGB (Bürgerliches Gesetzbuch — Germany's civil code covering contracts, liability, and obligations)",
    "indemnity": "indemnity (a promise to compensate the other party for specific losses)",
    "liability cap": "liability cap (the maximum amount one party can be made to pay for damages)",
    "unlimited liability": "unlimited liability (no cap on damages — BMW's red line in most contracts)",
    "governing law": "governing law (which country's legal system applies to disputes under the contract)",
    "jurisdiction": "jurisdiction (which country's courts have authority to hear disputes)",
    "force majeure": "force majeure (events beyond a party's control, like natural disasters, that excuse non-performance)",
    "breach notification": "breach notification (the legal obligation to report a data security incident, usually within 72 hours under GDPR)",
    "right of erasure": "right of erasure / right to be forgotten (a person's GDPR right to request deletion of their personal data)",
    "data portability": "data portability (a person's GDPR right to receive their data in a reusable format)",
    "lawful basis": "lawful basis (one of the six GDPR grounds that justifies processing personal data, e.g. consent or legitimate interest)",
    "legitimate interest": "legitimate interest (a GDPR lawful basis — processing is justified by a genuine business need, balanced against individuals' rights)",
    "adequacy decision": "adequacy decision (EU Commission ruling that a country provides equivalent data protection, allowing free data transfers)",
    "third-country transfer": "third-country transfer (sending EU personal data to a country outside the EEA)",
    "supervisory authority": "supervisory authority (the national data protection regulator, e.g. Germany's BfDI or state DPAs)",
    "joint controller": "joint controller (two or more organisations that jointly decide how personal data is processed)",
    "pseudonymisation": "pseudonymisation (replacing identifying information with a key, so data cannot directly identify a person without that key)",
    "data minimisation": "data minimisation (GDPR principle — only collect the minimum personal data needed for the stated purpose)",
    "purpose limitation": "purpose limitation (GDPR principle — data can only be used for the specific purpose it was collected for)",
    "storage limitation": "storage limitation (GDPR principle — personal data must not be kept longer than necessary)",
}
