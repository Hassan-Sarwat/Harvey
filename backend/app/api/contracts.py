from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.base import ReviewContext
from app.services.review_storage import DocumentStore
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


@router.post("/playbooks")
async def upload_playbook_documents(files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="At least one playbook document is required.")

    store = DocumentStore()
    playbook_id = f"playbook-{uuid4().hex[:12]}"
    documents = []
    for file in files:
        try:
            documents.append(store.save_playbook_document(file.filename or "uploaded-document", await file.read(), playbook_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"playbook_id": playbook_id, "document_count": len(documents), "documents": documents}


@router.post("/{contract_id}/review")
async def review_contract(contract_id: str, request: ContractCreateRequest) -> dict:
    context = ReviewContext(
        contract_id=contract_id,
        contract_text=request.contract_text,
        contract_type=request.contract_type,
    )
    result = await ContractReviewWorkflow().run(context)
    return result.model_dump()


@router.post("/{contract_id}/review/upload")
async def review_uploaded_contract(
    contract_id: str,
    file: UploadFile = File(...),
    contract_type: str | None = Form(default=None),
    playbook_id: str | None = Form(default=None),
) -> dict:
    store = DocumentStore()
    try:
        contract_document = store.save_contract_document(contract_id, file.filename or "contract", await file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    playbook_documents = store.load_playbook_documents(playbook_id) if playbook_id else []
    context = ReviewContext(
        contract_id=contract_id,
        contract_text=contract_document["text"],
        contract_type=contract_type,
        playbook_documents=playbook_documents,
        metadata={
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "playbook_id": playbook_id,
        },
    )
    result = await ContractReviewWorkflow().run(context)
    review_path = store.save_review_result(contract_id, contract_document, result)
    payload = result.model_dump()
    payload["metadata"]["contract_document"] = context.metadata["contract_document"]
    payload["metadata"]["review_storage_path"] = str(review_path)
    payload["metadata"]["playbook_document_count"] = len(playbook_documents)
    return payload
