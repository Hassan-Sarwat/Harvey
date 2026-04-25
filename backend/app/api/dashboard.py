from __future__ import annotations

from fastapi import APIRouter

from app.services.escalation_repository import EscalationRepository

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def metrics() -> dict:
    payload = {
        "ai_approved": 3,
        "escalated": 2,
        "average_contract_value_vs_default": [
            {"metric": "liability_cap_months", "playbook_default": 12, "average_observed": 18}
        ],
        "frequent_playbook_deviations": ["unlimited liability", "missing DPA subprocessors list"],
    }
    payload["escalation_metrics"] = EscalationRepository().escalation_metrics()
    return payload
