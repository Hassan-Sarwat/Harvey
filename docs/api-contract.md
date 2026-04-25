# API Contract

## Contract Review
`POST /contracts/review`

Request:

```json
{
  "contract_text": "string",
  "contract_type": "data_protection",
  "vendor": "ACME GmbH",
  "effective_date": "2026-01-01"
}
```

`contract_type` is optional. If omitted or blank, the backend infers `data_protection`, `litigation`, or `general` from the contract text.

Response:

```json
{
  "contract_id": "contract-abc123",
  "version_id": "version-def456",
  "version_number": 1,
  "is_new_contract": true,
  "agent_name": "risk_aggregator",
  "summary": "string",
  "findings": [],
  "suggestions": [],
  "confidence": 0.0,
  "requires_escalation": false,
  "metadata": {
    "business_status": "accepted",
    "escalation_available": false,
    "recognized_contract_type": "data_protection",
    "contract_type_source": "ai_inferred"
  }
}
```

Contracts are unique by recognized `contract_type`, `vendor`, and `effective_date`.
Re-reviewing the same identity creates a new version under the existing `contract_id`.
Review does not create a legal ticket automatically. If `metadata.business_status` is `needs_revision`, the business user should review the suggested edits and upload a revised version. If the business user declines or cannot obtain the changes, call `POST /contracts/{contract_id}/versions/{version_number}/escalate`.

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
`POST /contracts/review/upload`

Request: `multipart/form-data`

- `file`: contract document, including PDF, Word, Excel, or text formats.
- `contract_type`: optional contract type such as `data_protection`; omitted values are inferred from the extracted text.
- `vendor`: required vendor name.
- `effective_date`: required ISO date.
- `playbook_id`: optional uploaded playbook identifier returned by `POST /contracts/playbooks`.

Response: same review shape as `POST /contracts/review`, with extra metadata:

```json
{
  "contract_id": "contract-abc123",
  "version_id": "version-def456",
  "version_number": 2,
  "is_new_contract": false,
  "metadata": {
    "contract_document": {
      "filename": "supplier-dpa.pdf",
      "stored_path": "storage/contracts/contract-abc123/versions/v2/source/supplier-dpa.pdf",
      "extracted_text_path": "storage/contracts/contract-abc123/versions/v2/extracted/supplier-dpa.pdf.txt",
      "content_hash": "sha256"
    },
    "review_storage_path": "storage/contracts/contract-abc123/versions/v2/review.json",
    "playbook_document_count": 1,
    "business_status": "needs_revision",
    "escalation_available": true,
    "recognized_contract_type": "data_protection",
    "contract_type_source": "user_provided",
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

## Contract Version History
`GET /contracts/{contract_id}/versions`

Response:

```json
{
  "contract_id": "contract-abc123",
  "versions": [
    {
      "version_id": "version-def456",
      "version_number": 1,
      "contract_type": "data_protection",
      "vendor": "ACME GmbH",
      "effective_date": "2026-01-01",
      "contract_document": {},
      "ai_suggestions": []
    }
  ]
}
```

`GET /contracts/{contract_id}/versions/{version_number}` returns the same version metadata plus the full stored `review_result`.

`POST /contracts/{contract_id}/versions/{version_number}/escalate`

Creates a legal ticket only after the business user declines or cannot obtain the suggested edits.

Request:

```json
{
  "reason": "Business cannot accept the suggested liability cap.",
  "requested_by": "business-user"
}
```

Response: same shape as `GET /escalations/{escalation_id}` with `status: "pending_legal"`.

## Escalations
`GET /escalations`

Optional query:

- `status`: `pending_legal`, `accepted`, or `denied`

Response:

```json
{
  "items": [
    {
      "id": "esc-abc123",
      "ticket_id": "TCK-000123",
      "contract_id": "contract-abc123",
      "version_id": "version-def456",
      "version_number": 2,
      "status": "pending_legal",
      "reason": "Unlimited liability exceeds BMW default",
      "highest_severity": "blocker",
      "source_agents": ["playbook_checker"],
      "source_finding_ids": ["unlimited-liability"],
      "next_owner": "legal"
    }
  ]
}
```

`ticket_id` is the human-facing legal ticket identifier shown in the escalation queue. `GET /escalations/{escalation_id}` returns the same fields plus the full stored `review_result`, `ai_suggestions`, legal decision fields, fix suggestions, timeline, the stored `contract_text`, source `agent_outputs`, and normalized trigger annotations:

```json
{
  "contract_text": "Supplier accepts unlimited liability.",
  "trigger_annotations": [
    {
      "id": "playbook_checker:unlimited-liability",
      "agent_name": "playbook_checker",
      "finding_id": "unlimited-liability",
      "title": "Unlimited liability exceeds BMW default",
      "severity": "blocker",
      "requires_escalation": true,
      "start": 0,
      "end": 37,
      "text": "Supplier accepts unlimited liability.",
      "ruling": {
        "source": "BMW mock playbook: litigation",
        "citation": "LT-003 - Unlimited liability escalation",
        "quote": "Unlimited liability must be escalated to legal."
      },
      "suggestions": [
        {
          "finding_id": "unlimited-liability",
          "proposed_text": "Replace unlimited liability with the BMW-approved liability position.",
          "rationale": "Required by BMW Litigation Rule LT-003."
        }
      ]
    }
  ],
  "agent_outputs": []
}
```

`start` and `end` are character offsets into `contract_text`. The frontend uses `severity` to render highlights: low is yellow, medium is orange, and high/blocker is red. Rulings reference either the BMW company playbook or the Otto Schmidt / Legal Data Hub evidence. Fallback legal evidence remains labelled as fallback evidence.

`POST /escalations/{escalation_id}/chat`

Request:

```json
{
  "question": "Which playbook ruling triggered the liability issue?"
}
```

Response:

```json
{
  "escalation_id": "esc-abc123",
  "question": "Which playbook ruling triggered the liability issue?",
  "answer": "Relevant rulings: Unlimited liability exceeds BMW default cites BMW mock playbook: litigation LT-003 - Unlimited liability escalation: Unlimited liability must be escalated to legal.",
  "cited_context": []
}
```

`POST /escalations/{escalation_id}/decision`

Request:

```json
{
  "decision": "denied",
  "notes": "Legal cannot accept unlimited liability.",
  "fix_suggestions": ["Replace unlimited liability with the BMW default liability cap."],
  "decided_by": "legal-team"
}
```

- `decision` must be `accepted` or `denied`.
- `denied` requires at least one `fix_suggestion` and returns the contract to business with `next_owner: "business"`.
- `accepted` means legal approved the escalated contract to proceed.
- Re-deciding an escalation returns `409`.

## Dashboard Metrics
`GET /dashboard/metrics`

The response includes existing demo metrics plus live escalation metrics:

```json
{
  "escalation_metrics": {
    "total_escalations": 3,
    "pending_escalations": 1,
    "accepted_escalations": 1,
    "denied_escalations": 1,
    "false_escalations": 1,
    "positive_escalations": 1,
    "top_false_escalation_agent": {"agent_name": "playbook_checker"},
    "top_positive_escalation_agent": {"agent_name": "legal_checker"},
    "per_agent": []
  }
}
```

Accepted escalations count as false escalations. Denied escalations count as positive escalations. Counts are attributed to every non-aggregator agent that required escalation.

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
