from __future__ import annotations

from pydantic import BaseModel

from app.services.legal_data_hub import LegalDataHubClient
from app.services.playbook_repository import load_playbook_rows, playbook_file_label, playbook_source_label


class LegalQARequest(BaseModel):
    question: str
    use_case: str | None = None
    contract_type: str | None = None


class LegalQAResponse(BaseModel):
    domain: str
    summary: str
    recommendation: str
    company_basis: list[dict]
    legal_basis: list[dict]
    escalate: bool


class LegalQAWorkflow:
    def __init__(self, legal_data_hub: LegalDataHubClient | None = None) -> None:
        self.legal_data_hub = legal_data_hub or LegalDataHubClient()

    async def run(self, request: LegalQARequest) -> LegalQAResponse:
        domain = _infer_domain(request)
        legal_basis = await self.legal_data_hub.search_evidence(request.question, domain=domain)
        selected_rows, matched_playbook_terms = _select_playbook_rows(request.question, domain)
        company_basis = _company_basis_from_rows(selected_rows, domain)
        legal_basis = [_normalize_legal_basis(item) for item in legal_basis[:3]]
        escalate = _requires_escalation(request.question, selected_rows, matched_playbook_terms)
        return LegalQAResponse(
            domain=domain,
            summary=_summary(domain, selected_rows, legal_basis, matched_playbook_terms),
            recommendation=_recommendation(selected_rows, escalate),
            company_basis=company_basis,
            legal_basis=legal_basis,
            escalate=escalate,
        )


def _infer_domain(request: LegalQARequest) -> str:
    supplied = (request.contract_type or "").strip()
    if supplied and supplied != "general":
        return supplied
    question = request.question.lower()
    litigation_terms = ("litigation", "settlement", "liability", "indemnity", "court", "arbitration", "legal hold")
    if any(term in question for term in litigation_terms):
        return "litigation"
    return "data_protection"


def _company_basis(question: str, domain: str) -> list[dict]:
    selected, _ = _select_playbook_rows(question, domain)
    return _company_basis_from_rows(selected, domain)


def _select_playbook_rows(question: str, domain: str) -> tuple[list[dict[str, str]], bool]:
    rows = _load_playbook_rows(domain)
    if not rows:
        return [], False

    normalized_question = question.lower()
    terms = {term.strip(".,;:?!()[]") for term in normalized_question.replace("/", " ").replace("-", " ").split() if len(term) > 3}
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


def _summary(
    domain: str,
    rows: list[dict[str, str]],
    legal_basis: list[dict],
    matched_playbook_terms: bool,
) -> str:
    domain_label = "data protection" if domain == "data_protection" else domain.replace("_", " ")
    if rows and matched_playbook_terms:
        rule = rows[0]
        severity = (rule.get("severity") or "medium").lower()
        return (
            f"I checked the {playbook_source_label(domain)}. It treats this as a {severity} issue under "
            f"{rule.get('id', 'the cited rule')} ({rule.get('title', 'playbook rule')}). "
            f"German/EU legal evidence is cited below as support, not as a substitute for legal sign-off."
        )
    if rows:
        rule = rows[0]
        return (
            f"I checked the {playbook_source_label(domain)} and did not find an exact trigger match. "
            f"The closest playbook position is {rule.get('id', 'the cited rule')} "
            f"({rule.get('title', 'playbook rule')}). German/EU legal evidence is cited below as support."
        )
    if legal_basis:
        first = legal_basis[0]
        return (
            f"The strongest available {domain_label} answer is based on BMW playbook defaults "
            f"and legal evidence from {first.get('source', 'Legal Data Hub evidence')}."
        )
    return (
        f"The answer uses BMW {domain_label} playbook defaults. Legal evidence was unavailable, "
        "so treat this as a demo answer that needs legal validation."
    )


def _recommendation(rows: list[dict[str, str]], escalate: bool) -> str:
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
