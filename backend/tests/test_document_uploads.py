from __future__ import annotations

import json
from pathlib import Path
from tempfile import SpooledTemporaryFile

from starlette.datastructures import UploadFile

from app.agents.legal_checker import LegalDataHubClient
from app.api import contracts
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


def _upload_file(filename: str, content: bytes) -> UploadFile:
    file = SpooledTemporaryFile()
    file.write(content)
    file.seek(0)
    return UploadFile(file, filename=filename)


async def _fake_search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
    return [{"source": "test fallback", "citation": "test", "quote": "test evidence"}]
