# API Contract

## Contract Review
`POST /contracts/review`

Request:

```json
{
  "contract_text": "string",
  "contract_type": "data_protection",
  "vendor": "ACME GmbH",
  "effective_start_date": "2026-01-01",
  "effective_end_date": "2026-12-31"
}
```

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
    "escalation_id": "esc-abc123",
    "escalation_status": "pending_legal"
  }
}
```

Contracts are unique by `contract_type`, `vendor`, `effective_start_date`, and `effective_end_date`.
Re-reviewing the same identity creates a new version under the existing `contract_id`.
Escalation metadata is present only when `requires_escalation` is true.

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
- `contract_type`: required contract type such as `data_protection`.
- `vendor`: required vendor name.
- `effective_start_date`: required ISO date, using the contract effective start date.
- `effective_end_date`: required ISO date, using the contract effective end date.
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
      "effective_start_date": "2026-01-01",
      "effective_end_date": "2026-12-31",
      "contract_document": {},
      "ai_suggestions": []
    }
  ]
}
```

`GET /contracts/{contract_id}/versions/{version_number}` returns the same version metadata plus the full stored `review_result`.

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
      "contract_id": "contract-abc123",
      "version_id": "version-def456",
      "version_number": 2,
      "status": "pending_legal",
      "reason": "Unlimited liability exceeds BMW default",
      "source_agents": ["playbook_checker"],
      "source_finding_ids": ["unlimited-liability"],
      "next_owner": "legal"
    }
  ]
}
```

`GET /escalations/{escalation_id}` returns the same fields plus the full stored `review_result`, `ai_suggestions`, legal decision fields, fix suggestions, timeline, the stored `contract_text`, source `agent_outputs`, and normalized trigger annotations:

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
