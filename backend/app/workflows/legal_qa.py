from __future__ import annotations

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
        domain = request.contract_type or "data_protection"
        legal_basis = await self.legal_data_hub.search_evidence(request.question, domain=domain)
        company_basis = [
            {
                "source": "BMW mock playbook",
                "citation": "General Rule GEN-001",
                "quote": "High-risk deviations from BMW defaults must be escalated to legal.",
            }
        ]
        return LegalQAResponse(
            summary="This is a demo answer combining BMW playbook guidance with legal evidence.",
            recommendation="Use the cited playbook rule as the internal default and escalate if the contract deviates materially.",
            company_basis=company_basis,
            legal_basis=legal_basis[:3],
            escalate="unlimited" in request.question.lower() or "waive" in request.question.lower(),
        )
