from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agents.base import ReviewContext
from app.services.contract_repository import ContractIdentity, ContractRepository
from app.services.escalation_repository import EscalationRepository
from app.services.review_storage import DocumentStore
from app.workflows.review_contract import ContractReviewWorkflow

router = APIRouter(prefix="/contracts", tags=["contracts"])


class ContractCreateRequest(BaseModel):
    contract_text: str
    contract_type: str | None = None


class ContractIdentityRequest(BaseModel):
    contract_type: str = Field(min_length=1)
    vendor: str = Field(min_length=1)
    effective_start_date: date
    effective_end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> "ContractIdentityRequest":
        self.contract_type = self.contract_type.strip()
        self.vendor = self.vendor.strip()
        if not self.contract_type:
            raise ValueError("contract_type is required")
        if not self.vendor:
            raise ValueError("vendor is required")
        if self.effective_end_date < self.effective_start_date:
            raise ValueError("effective_end_date must be on or after effective_start_date")
        return self


class ContractReviewRequest(ContractIdentityRequest):
    contract_text: str = Field(min_length=1)


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


@router.post("/review")
async def review_contract_by_identity(request: ContractReviewRequest) -> dict:
    repository = ContractRepository()
    identity = _identity_from_request(request)
    contract, is_new_contract = repository.get_or_create_contract(identity)
    version_number = contract.current_version_number + 1
    store = DocumentStore()
    contract_document = store.save_contract_document(
        contract.contract_id,
        "contract.txt",
        request.contract_text.encode("utf-8"),
        version_number=version_number,
    )
    context = ReviewContext(
        contract_id=contract.contract_id,
        contract_text=contract_document["text"],
        contract_type=request.contract_type,
        metadata={
            "contract_identity": _identity_payload(identity),
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "version_number": version_number,
            "is_new_contract": is_new_contract,
        },
    )
    result = await ContractReviewWorkflow().run(context)
    review_path = store.save_review_result(contract.contract_id, contract_document, result, version_number=version_number)
    version = repository.create_version(
        contract_id=contract.contract_id,
        contract_document=contract_document,
        review_result=result,
    )
    payload = _review_payload(result, contract.contract_id, version.version_id, version.version_number, is_new_contract)
    _attach_escalation_metadata(
        payload,
        contract.contract_id,
        result,
        contract_text=context.contract_text,
        version_id=version.version_id,
        version_number=version.version_number,
    )
    payload["metadata"]["contract_document"] = context.metadata["contract_document"]
    payload["metadata"]["review_storage_path"] = str(review_path)
    return payload


@router.post("/review/upload")
async def review_uploaded_contract_by_identity(
    file: UploadFile = File(...),
    contract_type: str = Form(...),
    vendor: str = Form(...),
    effective_start_date: date = Form(...),
    effective_end_date: date = Form(...),
    playbook_id: str | None = Form(default=None),
) -> dict:
    try:
        identity_request = ContractIdentityRequest(
            contract_type=contract_type,
            vendor=vendor,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    repository = ContractRepository()
    identity = _identity_from_request(identity_request)
    contract, is_new_contract = repository.get_or_create_contract(identity)
    version_number = contract.current_version_number + 1

    store = DocumentStore()
    try:
        contract_document = store.save_contract_document(
            contract.contract_id,
            file.filename or "contract",
            await file.read(),
            version_number=version_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    playbook_documents = store.load_playbook_documents(playbook_id) if playbook_id else []
    context = ReviewContext(
        contract_id=contract.contract_id,
        contract_text=contract_document["text"],
        contract_type=contract_type,
        playbook_documents=playbook_documents,
        metadata={
            "contract_identity": _identity_payload(identity),
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "playbook_id": playbook_id,
            "version_number": version_number,
            "is_new_contract": is_new_contract,
        },
    )
    result = await ContractReviewWorkflow().run(context)
    review_path = store.save_review_result(contract.contract_id, contract_document, result, version_number=version_number)
    version = repository.create_version(
        contract_id=contract.contract_id,
        contract_document=contract_document,
        review_result=result,
    )
    payload = _review_payload(result, contract.contract_id, version.version_id, version.version_number, is_new_contract)
    _attach_escalation_metadata(
        payload,
        contract.contract_id,
        result,
        contract_text=context.contract_text,
        version_id=version.version_id,
        version_number=version.version_number,
    )
    payload["metadata"]["contract_document"] = context.metadata["contract_document"]
    payload["metadata"]["review_storage_path"] = str(review_path)
    payload["metadata"]["playbook_document_count"] = len(playbook_documents)
    return payload


@router.get("/{contract_id}/versions")
async def list_contract_versions(contract_id: str) -> dict:
    versions = ContractRepository().list_versions(contract_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Contract not found or has no versions.")
    return {"contract_id": contract_id, "versions": versions}


@router.get("/{contract_id}/versions/{version_number}")
async def get_contract_version(contract_id: str, version_number: int) -> dict:
    version = ContractRepository().get_version(contract_id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail="Contract version not found.")
    return version


@router.post("/{contract_id}/review")
async def review_contract(contract_id: str, request: ContractCreateRequest) -> dict:
    context = ReviewContext(
        contract_id=contract_id,
        contract_text=request.contract_text,
        contract_type=request.contract_type,
    )
    result = await ContractReviewWorkflow().run(context)
    payload = result.model_dump()
    _attach_escalation_metadata(payload, contract_id, result, contract_text=context.contract_text)
    return payload


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
    _attach_escalation_metadata(payload, contract_id, result, contract_text=context.contract_text)
    return payload


def _identity_from_request(request: ContractIdentityRequest) -> ContractIdentity:
    return ContractIdentity(
        contract_type=request.contract_type,
        vendor=request.vendor,
        effective_start_date=request.effective_start_date,
        effective_end_date=request.effective_end_date,
    )


def _identity_payload(identity: ContractIdentity) -> dict:
    return {
        "contract_type": identity.contract_type,
        "vendor": identity.vendor,
        "effective_start_date": identity.effective_start_date.isoformat(),
        "effective_end_date": identity.effective_end_date.isoformat(),
    }


def _review_payload(
    result,
    contract_id: str,
    version_id: str,
    version_number: int,
    is_new_contract: bool,
) -> dict:
    payload = result.model_dump()
    payload["contract_id"] = contract_id
    payload["version_id"] = version_id
    payload["version_number"] = version_number
    payload["is_new_contract"] = is_new_contract
    payload["metadata"]["contract_id"] = contract_id
    payload["metadata"]["version_id"] = version_id
    payload["metadata"]["version_number"] = version_number
    payload["metadata"]["is_new_contract"] = is_new_contract
    return payload


def _attach_escalation_metadata(
    payload: dict,
    contract_id: str,
    result,
    contract_text: str | None = None,
    version_id: str | None = None,
    version_number: int | None = None,
) -> None:
    escalation = EscalationRepository().create_from_review(
        contract_id=contract_id,
        review_result=result,
        contract_text=contract_text,
        version_id=version_id,
        version_number=version_number,
    )
    if not escalation:
        return

    payload["metadata"]["escalation_id"] = escalation["id"]
    payload["metadata"]["escalation_status"] = escalation["status"]
