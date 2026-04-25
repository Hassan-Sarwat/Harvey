from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/escalations", tags=["escalations"])


class LegalDecisionRequest(BaseModel):
    decision: str
    notes: str | None = None


@router.get("")
async def list_escalations() -> dict:
    return {
        "items": [
            {
                "id": "esc-demo-1",
                "contract_id": "demo-contract-1",
                "status": "pending_legal",
                "reason": "High-severity BMW playbook deviation",
            }
        ]
    }


@router.get("/{escalation_id}")
async def get_escalation(escalation_id: str) -> dict:
    return {
        "id": escalation_id,
        "contract_id": "demo-contract-1",
        "history": ["uploaded", "reviewed_by_ai", "escalated"],
        "communications": [],
        "ai_suggestions": [],
        "status": "pending_legal",
    }


@router.post("/{escalation_id}/decision")
async def decide_escalation(escalation_id: str, request: LegalDecisionRequest) -> dict:
    return {"id": escalation_id, "decision": request.decision, "notes": request.notes}
