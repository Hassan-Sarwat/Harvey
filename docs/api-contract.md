# API Contract

## Contract Review
`POST /contracts/{contract_id}/review`

Request:

```json
{
  "contract_text": "string",
  "contract_type": "data_protection"
}
```

Response:

```json
{
  "agent_name": "risk_aggregator",
  "summary": "string",
  "findings": [],
  "suggestions": [],
  "confidence": 0.0,
  "requires_escalation": false,
  "metadata": {}
}
```

## Playbook Upload
`POST /contracts/playbooks`

Request: `multipart/form-data`

- `files`: one or more company playbook documents. Folder uploads are represented by repeated files whose filenames include relative paths.
- Supported extensions: `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.csv`, `.txt`, `.md`, `.json`.

Response:

```json
{
  "playbook_id": "playbook-abc123",
  "document_count": 2,
  "documents": [
    {
      "filename": "policies/data-protection.pdf",
      "stored_path": "storage/playbooks/playbook-abc123/source/policies/data-protection.pdf",
      "extracted_text_path": "storage/playbooks/playbook-abc123/extracted/data-protection.pdf.txt",
      "character_count": 1200
    }
  ]
}
```

## Uploaded Contract Review
`POST /contracts/{contract_id}/review/upload`

Request: `multipart/form-data`

- `file`: contract document, including PDF, Word, Excel, or text formats.
- `contract_type`: optional contract type such as `data_protection`.
- `playbook_id`: optional uploaded playbook identifier returned by `POST /contracts/playbooks`.

Response: same review shape as `POST /contracts/{contract_id}/review`, with extra metadata:

```json
{
  "metadata": {
    "contract_document": {
      "filename": "supplier-dpa.pdf",
      "stored_path": "storage/contracts/demo-contract-1/source/supplier-dpa.pdf",
      "extracted_text_path": "storage/contracts/demo-contract-1/extracted/supplier-dpa.pdf.txt"
    },
    "review_storage_path": "storage/contracts/demo-contract-1/review.json",
    "playbook_document_count": 1,
    "agent_results": [
      {
        "agent_name": "playbook_checker",
        "metadata": {
          "passed": false
        }
      }
    ]
  }
}
```

## Legal Q&A
`POST /legal-qa`

Request:

```json
{
  "question": "string",
  "use_case": "string",
  "contract_type": "data_protection"
}
```

Response:

```json
{
  "summary": "string",
  "recommendation": "string",
  "company_basis": [],
  "legal_basis": [],
  "escalate": false
}
```
