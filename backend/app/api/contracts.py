from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.base import ReviewContext
from app.workflows.review_contract import ContractReviewWorkflow

router = APIRouter(prefix="/contracts", tags=["contracts"])


class ContractCreateRequest(BaseModel):
    contract_text: str
    contract_type: str | None = None


@router.post("")
async def create_contract(request: ContractCreateRequest) -> dict:
    return {
        "contract_id": "demo-contract-1",
        "contract_type": request.contract_type,
        "status": "created",
    }


@router.post("/{contract_id}/review")
async def review_contract(contract_id: str, request: ContractCreateRequest) -> dict:
    context = ReviewContext(
        contract_id=contract_id,
        contract_text=request.contract_text,
        contract_type=request.contract_type,
    )
    result = await ContractReviewWorkflow().run(context)
    return result.model_dump()
