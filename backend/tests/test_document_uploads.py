from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile

from app.agents.legal_checker import LegalDataHubClient
from app.api import contracts
from app.services.contract_repository import ContractRepository
from app.services.escalation_repository import EscalationRepository
from app.services.review_storage import DocumentStore


async def test_upload_playbook_documents_preserves_folder_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))

    payload = await contracts.upload_playbook_documents(
        files=[
            _upload_file("policies/data-protection.txt", b"BMW contracting entity must be named."),
            _upload_file("litigation.xlsx", b"Settlement authority remains with BMW legal."),
        ]
    )

    assert payload["document_count"] == 2
    assert payload["documents"][0]["filename"] == "policies/data-protection.txt"
    assert Path(payload["documents"][0]["stored_path"]).exists()
    assert "policies" in payload["documents"][0]["stored_path"]


async def test_review_uploaded_contract_stores_pdf_and_agent_reactions(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))
    monkeypatch.setattr(contracts, "EscalationRepository", lambda: EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}"))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    playbook_payload = await contracts.upload_playbook_documents(
        files=[_upload_file("bmw/playbook.txt", b"Processor must list subprocessors or state none are used.")]
    )
    playbook_id = playbook_payload["playbook_id"]

    payload = await contracts.review_uploaded_contract(
        contract_id="demo-contract-2",
        contract_type="data_protection",
        playbook_id=playbook_id,
        file=_upload_file("supplier-dpa.pdf", b"BMW supplier processes personal data. Supplier accepts unlimited liability."),
    )

    assert payload["metadata"]["contract_document"]["filename"] == "supplier-dpa.pdf"
    assert Path(payload["metadata"]["contract_document"]["stored_path"]).exists()
    assert payload["metadata"]["playbook_document_count"] == 1
    assert all("passed" in result["metadata"] for result in payload["metadata"]["agent_results"])

    review_path = Path(payload["metadata"]["review_storage_path"])
    assert review_path.exists()
    persisted = json.loads(review_path.read_text(encoding="utf-8"))
    assert persisted["contract_document"]["filename"] == "supplier-dpa.pdf"
    assert persisted["review_result"]["metadata"]["agent_results"]


async def test_reupload_same_identity_creates_contract_version_history(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))
    monkeypatch.setattr(contracts, "ContractRepository", lambda: ContractRepository(f"sqlite:///{tmp_path / 'harvey.db'}"))
    monkeypatch.setattr(contracts, "EscalationRepository", lambda: EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}"))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    first = await contracts.review_uploaded_contract_by_identity(
        contract_type="data_protection",
        vendor="ACME GmbH",
        effective_date=date(2026, 1, 1),
        playbook_id=None,
        file=_upload_file("supplier-dpa-v1.pdf", b"BMW supplier processes personal data."),
    )
    second = await contracts.review_uploaded_contract_by_identity(
        contract_type=" data_protection ",
        vendor=" acme gmbh ",
        effective_date=date(2026, 1, 1),
        playbook_id=None,
        file=_upload_file("supplier-dpa-v2.pdf", b"Supplier processes personal data. Supplier accepts unlimited liability."),
    )

    assert first["contract_id"] == second["contract_id"]
    assert first["version_number"] == 1
    assert second["version_number"] == 2
    assert first["is_new_contract"] is True
    assert second["is_new_contract"] is False
    assert "/versions/v1/" in first["metadata"]["contract_document"]["stored_path"]
    assert "/versions/v2/" in second["metadata"]["contract_document"]["stored_path"]

    history = await contracts.list_contract_versions(first["contract_id"])
    assert [version["version_number"] for version in history["versions"]] == [1, 2]
    assert history["versions"][1]["ai_suggestions"]

    version = await contracts.get_contract_version(first["contract_id"], 2)
    assert version["review_result"]["metadata"]["agent_results"]


async def test_changed_contract_identity_creates_new_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))
    monkeypatch.setattr(contracts, "ContractRepository", lambda: ContractRepository(f"sqlite:///{tmp_path / 'harvey.db'}"))
    monkeypatch.setattr(contracts, "EscalationRepository", lambda: EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}"))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    first = await contracts.review_contract_by_identity(
        contracts.ContractReviewRequest(
            contract_text="BMW supplier processes personal data.",
            contract_type="data_protection",
            vendor="ACME GmbH",
            effective_date=date(2026, 1, 1),
        )
    )
    second = await contracts.review_contract_by_identity(
        contracts.ContractReviewRequest(
            contract_text="BMW supplier processes personal data.",
            contract_type="data_protection",
            vendor="Different GmbH",
            effective_date=date(2026, 1, 1),
        )
    )

    assert first["contract_id"] != second["contract_id"]
    assert first["version_number"] == 1
    assert second["version_number"] == 1
    assert second["is_new_contract"] is True


async def test_contract_type_is_inferred_when_not_supplied(tmp_path, monkeypatch):
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))
    monkeypatch.setattr(contracts, "ContractRepository", lambda: ContractRepository(f"sqlite:///{tmp_path / 'harvey.db'}"))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    payload = await contracts.review_contract_by_identity(
        contracts.ContractReviewRequest(
            contract_text="Effective Date: 1 January 2026. BMW is controller and Supplier is processor of personal data under GDPR.",
            vendor="ACME GmbH",
            effective_date=date(2026, 1, 1),
        )
    )

    assert payload["metadata"]["recognized_contract_type"] == "data_protection"
    assert payload["metadata"]["contract_type_source"] == "ai_inferred"

    history = await contracts.list_contract_versions(payload["contract_id"])
    assert history["versions"][0]["contract_type"] == "data_protection"
    assert history["versions"][0]["effective_date"] == "2026-01-01"


async def test_revised_contract_version_can_be_accepted_without_legal_ticket(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))
    monkeypatch.setattr(contracts, "ContractRepository", lambda: ContractRepository(database_url))
    monkeypatch.setattr(contracts, "EscalationRepository", lambda: EscalationRepository(database_url))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    first = await contracts.review_contract_by_identity(
        contracts.ContractReviewRequest(
            contract_text="Effective Date: 1 January 2026. BMW supplier accepts unlimited liability.",
            contract_type="litigation",
            vendor="ACME GmbH",
            effective_date=date(2026, 1, 1),
        )
    )
    second = await contracts.review_contract_by_identity(
        contracts.ContractReviewRequest(
            contract_text="Effective Date: 1 January 2026. BMW supplier liability is capped at 100 percent of annual fees.",
            contract_type="litigation",
            vendor="ACME GmbH",
            effective_date=date(2026, 1, 1),
        )
    )

    assert first["contract_id"] == second["contract_id"]
    assert first["metadata"]["business_status"] == "needs_revision"
    assert second["version_number"] == 2
    assert second["metadata"]["business_status"] == "accepted"
    assert second["requires_escalation"] is False
    assert EscalationRepository(database_url).list_escalations() == []


def _upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file, filename=filename)


async def _fake_search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
    return [{"source": "test fallback", "citation": "test", "quote": "test evidence"}]
