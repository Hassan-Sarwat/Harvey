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
