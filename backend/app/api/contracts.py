from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.agents.base import AgentResult, ReviewContext
from app.services.contract_repository import ContractIdentity, ContractRepository
from app.services.escalation_repository import EscalationRepository
from app.services.document_ingestion import extract_document_text
from app.services.review_storage import DocumentStore
from app.workflows.review_contract import ContractReviewWorkflow

router = APIRouter(prefix="/contracts", tags=["contracts"])


class ContractCreateRequest(BaseModel):
    contract_text: str
    contract_type: str | None = None


class ContractIdentityRequest(BaseModel):
    contract_type: str | None = None
    vendor: str = Field(min_length=1)
    effective_date: date | None = None
    effective_start_date: date | None = None
    effective_end_date: date | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> "ContractIdentityRequest":
        self.contract_type = self.contract_type.strip() if self.contract_type else None
        self.vendor = self.vendor.strip()
        if not self.vendor:
            raise ValueError("vendor is required")
        if self.effective_date is None:
            self.effective_date = self.effective_start_date
        if self.effective_date is None:
            raise ValueError("effective_date is required")
        if (
            self.effective_start_date is not None
            and self.effective_end_date is not None
            and self.effective_end_date < self.effective_start_date
        ):
            raise ValueError("effective_end_date must be on or after effective_start_date")
        return self


class ContractReviewRequest(ContractIdentityRequest):
    contract_text: str = Field(min_length=1)


class BusinessEscalationRequest(BaseModel):
    reason: str | None = None
    requested_by: str | None = None


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
    resolved_contract_type, contract_type_source = _resolve_contract_type(request.contract_type, request.contract_text)
    identity = _identity_from_request(request, resolved_contract_type)
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
        contract_type=resolved_contract_type,
        metadata={
            "contract_identity": _identity_payload(identity),
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "version_number": version_number,
            "is_new_contract": is_new_contract,
            "contract_type_source": contract_type_source,
            "uploaded_documents": [{"filename": "contract.txt", "text": contract_document["text"]}],
        },
    )
    result = await ContractReviewWorkflow().run(context)
    _finalize_review_result(result, resolved_contract_type, contract_type_source)
    review_path = store.save_review_result(contract.contract_id, contract_document, result, version_number=version_number)
    version = repository.create_version(
        contract_id=contract.contract_id,
        contract_document=contract_document,
        review_result=result,
    )
    payload = _review_payload(result, contract.contract_id, version.version_id, version.version_number, is_new_contract)
    payload["metadata"]["contract_document"] = context.metadata["contract_document"]
    payload["metadata"]["review_storage_path"] = str(review_path)
    return payload


@router.post("/review/upload")
async def review_uploaded_contract_by_identity(
    file: UploadFile = File(...),
    contract_type: str | None = Form(default=None),
    vendor: str = Form(...),
    effective_date: date | None = Form(default=None),
    effective_start_date: date | None = Form(default=None),
    effective_end_date: date | None = Form(default=None),
    playbook_id: str | None = Form(default=None),
) -> dict:
    contract_type = _optional_form_value(contract_type)
    effective_date = _optional_form_value(effective_date)
    effective_start_date = _optional_form_value(effective_start_date)
    effective_end_date = _optional_form_value(effective_end_date)
    playbook_id = _optional_form_value(playbook_id)
    try:
        identity_request = ContractIdentityRequest(
            contract_type=contract_type,
            vendor=vendor,
            effective_date=effective_date,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    content = await file.read()
    try:
        extracted_text = extract_document_text(file.filename or "contract", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    resolved_contract_type, contract_type_source = _resolve_contract_type(contract_type, extracted_text)
    repository = ContractRepository()
    identity = _identity_from_request(identity_request, resolved_contract_type)
    contract, is_new_contract = repository.get_or_create_contract(identity)
    version_number = contract.current_version_number + 1

    store = DocumentStore()
    try:
        contract_document = store.save_contract_document(
            contract.contract_id,
            file.filename or "contract",
            content,
            version_number=version_number,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    playbook_documents = store.load_playbook_documents(playbook_id) if playbook_id else []
    context = ReviewContext(
        contract_id=contract.contract_id,
        contract_text=contract_document["text"],
        contract_type=resolved_contract_type,
        playbook_documents=playbook_documents,
        metadata={
            "contract_identity": _identity_payload(identity),
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "playbook_id": playbook_id,
            "version_number": version_number,
            "is_new_contract": is_new_contract,
            "contract_type_source": contract_type_source,
            "uploaded_documents": [{"filename": file.filename or "contract", "text": contract_document["text"]}],
        },
    )
    result = await ContractReviewWorkflow().run(context)
    _finalize_review_result(result, resolved_contract_type, contract_type_source)
    review_path = store.save_review_result(contract.contract_id, contract_document, result, version_number=version_number)
    version = repository.create_version(
        contract_id=contract.contract_id,
        contract_document=contract_document,
        review_result=result,
    )
    payload = _review_payload(result, contract.contract_id, version.version_id, version.version_number, is_new_contract)
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


@router.post("/{contract_id}/versions/{version_number}/escalate")
async def escalate_contract_version(
    contract_id: str,
    version_number: int,
    request: BusinessEscalationRequest | None = None,
) -> dict:
    version = ContractRepository().get_version(contract_id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail="Contract version not found.")

    review_result = AgentResult.model_validate(version["review_result"])
    if not review_result.requires_escalation:
        raise HTTPException(status_code=409, detail="This contract version has no legal escalation trigger.")

    request = request or BusinessEscalationRequest()
    business_reason = (request.reason or "").strip() or "Business user declined the suggested contract edits."
    requested_by = (request.requested_by or "").strip() or None
    contract_text = DocumentStore().load_contract_text(version["contract_document"])
    escalation = EscalationRepository().create_from_review(
        contract_id=contract_id,
        review_result=review_result,
        contract_text=contract_text,
        version_id=version["version_id"],
        version_number=version_number,
        business_reason=business_reason,
        requested_by=requested_by,
    )
    if escalation is None:
        raise HTTPException(status_code=409, detail="This contract version does not require legal escalation.")

    detail = EscalationRepository().get_escalation(escalation["id"])
    return detail or escalation


@router.post("/{contract_id}/review")
async def review_contract(contract_id: str, request: ContractCreateRequest) -> dict:
    resolved_contract_type, contract_type_source = _resolve_contract_type(request.contract_type, request.contract_text)
    context = ReviewContext(
        contract_id=contract_id,
        contract_text=request.contract_text,
        contract_type=resolved_contract_type,
        metadata={"uploaded_documents": [{"filename": "contract.txt", "text": request.contract_text}]},
    )
    result = await ContractReviewWorkflow().run(context)
    _finalize_review_result(result, resolved_contract_type, contract_type_source)
    payload = result.model_dump()
    return payload


@router.post("/{contract_id}/review/upload")
async def review_uploaded_contract(
    contract_id: str,
    file: UploadFile = File(...),
    contract_type: str | None = Form(default=None),
    playbook_id: str | None = Form(default=None),
) -> dict:
    contract_type = _optional_form_value(contract_type)
    playbook_id = _optional_form_value(playbook_id)
    store = DocumentStore()
    content = await file.read()
    try:
        contract_document = store.save_contract_document(contract_id, file.filename or "contract", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    playbook_documents = store.load_playbook_documents(playbook_id) if playbook_id else []
    resolved_contract_type, contract_type_source = _resolve_contract_type(contract_type, contract_document["text"])
    context = ReviewContext(
        contract_id=contract_id,
        contract_text=contract_document["text"],
        contract_type=resolved_contract_type,
        playbook_documents=playbook_documents,
        metadata={
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "playbook_id": playbook_id,
            "contract_type_source": contract_type_source,
            "uploaded_documents": [{"filename": file.filename or "contract", "text": contract_document["text"]}],
        },
    )
    result = await ContractReviewWorkflow().run(context)
    _finalize_review_result(result, resolved_contract_type, contract_type_source)
    review_path = store.save_review_result(contract_id, contract_document, result)
    payload = result.model_dump()
    payload["metadata"]["contract_document"] = context.metadata["contract_document"]
    payload["metadata"]["review_storage_path"] = str(review_path)
    payload["metadata"]["playbook_document_count"] = len(playbook_documents)
    return payload


def _identity_from_request(request: ContractIdentityRequest, contract_type: str) -> ContractIdentity:
    if request.effective_date is None:
        raise HTTPException(status_code=422, detail="effective_date is required")
    return ContractIdentity(
        contract_type=contract_type,
        vendor=request.vendor,
        effective_date=request.effective_date,
    )


def _identity_payload(identity: ContractIdentity) -> dict:
    return {
        "contract_type": identity.contract_type,
        "vendor": identity.vendor,
        "effective_date": identity.effective_date.isoformat(),
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


def _finalize_review_result(result: AgentResult, contract_type: str, contract_type_source: str) -> None:
    result.metadata["recognized_contract_type"] = contract_type
    result.metadata["contract_type_source"] = contract_type_source
    result.metadata["business_status"] = "needs_business_input" if _review_needs_business_input(result) else "needs_revision" if result.findings else "accepted"
    result.metadata["escalation_available"] = result.requires_escalation
    result.metadata["needs_business_input"] = _review_needs_business_input(result)


def _review_needs_business_input(result: AgentResult) -> bool:
    if not result.requires_escalation:
        return False
    if any(
        finding.id.startswith(("missing-required-document", "missing-business-input"))
        and finding.severity.value in {"high", "blocker"}
        for finding in result.findings
    ):
        return True
    for agent_result in result.metadata.get("agent_results", []) or []:
        if agent_result.get("agent_name") != "completeness_checker":
            continue
        metadata = agent_result.get("metadata", {}) or {}
        if metadata.get("status") == "needs_business_input" or int(metadata.get("blocking_count") or 0) > 0:
            return True
    return False


def _resolve_contract_type(contract_type: str | None, contract_text: str) -> tuple[str, str]:
    normalized = (contract_type or "").strip()
    if normalized:
        return normalized, "user_provided"
    return _infer_contract_type(contract_text), "ai_inferred"


def _infer_contract_type(contract_text: str) -> str:
    text = contract_text.lower()
    data_protection_terms = (
        "gdpr",
        "personal data",
        "data subject",
        "processor",
        "controller",
        "subprocessor",
        "data processing",
        "breach notification",
        "technical and organisational",
        "third-country",
    )
    litigation_terms = (
        "litigation",
        "settlement",
        "liability",
        "indemnity",
        "court",
        "arbitration",
        "legal hold",
        "governing law",
        "claims",
        "privilege",
    )
    data_score = sum(1 for term in data_protection_terms if term in text)
    litigation_score = sum(1 for term in litigation_terms if term in text)
    if data_score > litigation_score and data_score > 0:
        return "data_protection"
    if litigation_score > 0:
        return "litigation"
    return "general"


def _optional_form_value(value):
    if type(value).__module__ == "fastapi.params" and type(value).__name__ == "Form":
        return None
    return value
