from __future__ import annotations

import json
from hashlib import sha256
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.agents.base import AgentResult
from app.core.config import get_settings
from app.services.document_ingestion import extract_document_text, safe_upload_path


class DocumentStore:
    def __init__(self, storage_dir: str | None = None) -> None:
        configured_dir = storage_dir or get_settings().upload_storage_dir
        configured_path = Path(configured_dir)
        if configured_path.is_absolute():
            self.root = configured_path
        else:
            self.root = Path(__file__).resolve().parents[3] / configured_path

    def save_playbook_document(self, filename: str, content: bytes, upload_id: str | None = None) -> dict[str, Any]:
        playbook_id = upload_id or f"playbook-{uuid4().hex[:12]}"
        relative_path = safe_upload_path(filename)
        target = self.root / "playbooks" / playbook_id / "source" / Path(*relative_path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        extracted_text = extract_document_text(filename, content)
        text_path = self.root / "playbooks" / playbook_id / "extracted" / f"{target.name}.txt"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(extracted_text, encoding="utf-8")

        document = {
            "playbook_id": playbook_id,
            "filename": filename,
            "stored_path": str(target),
            "extracted_text_path": str(text_path),
            "text_preview": extracted_text[:500],
            "character_count": len(extracted_text),
            "uploaded_at": _utc_now(),
        }
        self._append_manifest(self.root / "playbooks" / playbook_id / "manifest.json", document)
        return document

    def load_playbook_documents(self, playbook_id: str) -> list[dict[str, Any]]:
        manifest_path = self.root / "playbooks" / playbook_id / "manifest.json"
        if not manifest_path.exists():
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        documents = manifest.get("documents", [])
        for document in documents:
            text_path = Path(document["extracted_text_path"])
            document["text"] = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        return documents

    def save_contract_document(
        self,
        contract_id: str,
        filename: str,
        content: bytes,
        version_number: int | None = None,
    ) -> dict[str, Any]:
        relative_path = safe_upload_path(filename)
        contract_root = self.root / "contracts" / contract_id
        if version_number is not None:
            contract_root = contract_root / "versions" / f"v{version_number}"
        target = contract_root / "source" / Path(*relative_path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        extracted_text = extract_document_text(filename, content)
        text_path = contract_root / "extracted" / f"{target.name}.txt"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(extracted_text, encoding="utf-8")

        return {
            "contract_id": contract_id,
            "filename": filename,
            "stored_path": str(target),
            "extracted_text_path": str(text_path),
            "content_hash": sha256(content).hexdigest(),
            "character_count": len(extracted_text),
            "text": extracted_text,
            "uploaded_at": _utc_now(),
        }

    def save_review_result(
        self,
        contract_id: str,
        contract_document: dict[str, Any],
        result: AgentResult,
        version_number: int | None = None,
    ) -> Path:
        contract_root = self.root / "contracts" / contract_id
        if version_number is not None:
            contract_root = contract_root / "versions" / f"v{version_number}"
        review_path = contract_root / "review.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "contract_id": contract_id,
            "contract_document": {key: value for key, value in contract_document.items() if key != "text"},
            "review_result": result.model_dump(mode="json"),
            "saved_at": _utc_now(),
        }
        review_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return review_path

    def _append_manifest(self, manifest_path: Path, document: dict[str, Any]) -> None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {"playbook_id": document["playbook_id"], "documents": []}
        manifest["documents"].append(document)
        manifest["updated_at"] = _utc_now()
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
