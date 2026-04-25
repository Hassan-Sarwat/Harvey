from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel

from app.services.legal_data_hub import LegalDataHubClient


class LegalQARequest(BaseModel):
    question: str
    use_case: str | None = None
    contract_type: str | None = None


class LegalQAResponse(BaseModel):
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
        company_basis = _company_basis(request.question, domain)
        return LegalQAResponse(
            summary="This demo answer combines BMW playbook guidance with fallback legal evidence.",
            recommendation="Use the cited playbook rule as the internal default and escalate blocker or high-risk deviations to legal.",
            company_basis=company_basis,
            legal_basis=legal_basis[:3],
            escalate="unlimited" in request.question.lower() or "waive" in request.question.lower(),
        )


def _infer_domain(request: LegalQARequest) -> str:
    if request.contract_type:
        return request.contract_type.strip() or "data_protection"
    question = request.question.lower()
    litigation_terms = ("litigation", "settlement", "liability", "indemnity", "court", "arbitration", "legal hold")
    if any(term in question for term in litigation_terms):
        return "litigation"
    return "data_protection"


def _company_basis(question: str, domain: str) -> list[dict]:
    rows = _load_playbook_rows(domain)
    if not rows:
        return [
            {
                "source": "BMW mock playbook",
                "citation": "Fallback company rule unavailable",
                "quote": "High-risk deviations from BMW defaults must be escalated to legal.",
            }
        ]

    terms = {term for term in question.lower().replace("/", " ").replace("-", " ").split() if len(term) > 3}
    scored: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        searchable = " ".join(str(row.get(key, "")) for key in ("id", "title", "default", "red_line", "escalation_trigger")).lower()
        score = sum(1 for term in terms if term in searchable)
        if score:
            scored.append((score, row))
    selected = [row for _, row in sorted(scored, key=lambda item: item[0], reverse=True)[:3]]
    if not selected:
        selected = rows[:3]

    return [
        {
            "source": f"BMW mock playbook CSV: {domain}",
            "citation": f"{row.get('id', 'unknown')} - {row.get('title', 'Untitled rule')}",
            "quote": row.get("default") or row.get("preferred_position") or "",
            "severity": row.get("severity"),
            "approved_fix": row.get("approved_fix"),
        }
        for row in selected
    ]


def _load_playbook_rows(domain: str) -> list[dict[str, str]]:
    file_name = "bmw_litigation.csv" if domain == "litigation" else "bmw_data_protection.csv"
    path = Path(__file__).resolve().parents[3] / "data" / "playbook" / file_name
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
