from __future__ import annotations

from fastapi import APIRouter

from app.workflows.legal_qa import LegalQARequest, LegalQAWorkflow

router = APIRouter(prefix="/legal-qa", tags=["legal-qa"])


@router.post("")
async def answer_question(request: LegalQARequest) -> dict:
    response = await LegalQAWorkflow().run(request)
    return response.model_dump()


@router.get("/legal-data-hub/status")
async def legal_data_hub_status() -> dict:
    return await LegalQAWorkflow().legal_data_hub.status()
