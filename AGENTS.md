# Project Context

## Product Goal
Harvey is a hackathon demo for a BMW-focused AI contract assistant. It helps business and technical teams:

- Ask legal and BMW playbook questions.
- Review uploaded contracts against BMW playbook positions and German/EU legal evidence.
- Store prior chats, contract review reasoning, source usage, and final contract status in History.
- Escalate risky final contract versions to Legal with context.

The system must not pretend to replace lawyers. It should speed up routine review, explain risk clearly, suggest fixes, cite sources, and escalate issues that need legal judgment.

## Current Implemented State

### Frontend
The active frontend is the Vite React app in `frontend/src`.

- `frontend/src/App.tsx`: single-file app shell, route switching, Ask Donna chat, History, Dashboard, and Playbook views.
- `frontend/src/api.ts`: browser API client for config, dashboard, Ask Donna analyze, and History endpoints.
- `frontend/src/types.ts`: frontend DTO types for run results, history, sources, findings, dashboard data.
- `frontend/src/styles.css`: active app styling.

Navigation currently uses:

- General
  - Ask Donna
  - History
- Legal
  - Dashboard
  - Playbook
  - Escalations (currently sidebar-only / not a full frontend view)
- Admin
  - Settings (placeholder)

Ask Donna is implemented as a chat-style page:

- One combined message box for legal question, business context, or pasted contract text.
- Mode selector: `general_question` or `contract_review`.
- File upload support for contract review.
- No manual source/agent selectors in the UI; sources and agents are selected automatically by backend routing.
- Final-version toggle for contract review.
- If a final contract passes checks, status becomes `approved`.
- If a final contract has unresolved findings/escalation triggers, status becomes `pending_legal`.
- History stores chat messages, replies, visible reasoning, sources used, findings, and contract timeline events.

The old `frontend/src/pages`, `frontend/src/components/workspace`, and `frontend/src/api/client.ts` paths are no longer the active app surface. There are also `backup_frontend*` and `louis_frontend` folders; do not use them for current work unless explicitly asked.

### Backend
The backend is FastAPI.

- `backend/app/main.py`: FastAPI entrypoint; registers contracts, legal Q&A, escalations, dashboard, intake, and history routers; initializes repositories.
- `backend/app/api/intake.py`: Ask Donna analyze/demo/config/dashboard routes under `/api`.
- `backend/app/api/history.py`: History list/detail/drop routes under `/api/history`.
- `backend/app/api/legal_qa.py`: Legal Q&A route plus Legal Data Hub status route.
- `backend/app/api/contracts.py`: contract identity/version review APIs and business escalation creation.
- `backend/app/api/escalations.py`: escalation list/detail/chat/decision APIs.
- `backend/app/api/dashboard.py`: backend metrics endpoint.

Important services:

- `backend/app/services/playbook_repository.py`: loads BMW playbook CSVs from `data/playbook`.
- `backend/app/services/legal_data_hub.py`: live Otto Schmidt / Legal Data Hub adapter with explicit fallback evidence.
- `backend/app/services/history_repository.py`: SQLite persistence for Ask Donna chat/history.
- `backend/app/services/contract_repository.py`: SQLite contract identity and version history.
- `backend/app/services/escalation_repository.py`: SQLite escalation tickets and decisions.
- `backend/app/services/review_storage.py`: uploaded document and review JSON storage.
- `backend/app/services/document_ingestion.py`: text extraction for PDF, DOCX, XLSX, PPTX, TXT, CSV, EML, ZIP, etc.

### Workflows And Agents
Agents implement `run(context) -> AgentResult` from `backend/app/agents/base.py`.

The contract review workflow in `backend/app/workflows/review_contract.py` runs:

1. Contract Understanding Agent
2. BMW Playbook Checker Agent
3. German Legal Checker Agent
4. Risk Aggregator

Current agents:

- `contract_understanding.py`: identifies basic contract characteristics and missing effective date.
- `playbook_checker.py`: checks contract text against loaded BMW playbook rules.
- `legal_checker.py`: calls Legal Data Hub evidence and flags legal red flags currently implemented for data subject rights waiver.
- `risk_aggregator.py`: consolidates findings and escalation state.
- `escalation_packager.py`: supports legal escalation context packaging.

Legal/playbook Q&A uses `backend/app/workflows/legal_qa.py`.

- It infers a concrete domain (`data_protection` or `litigation`) even for general questions.
- It selects playbook rows by keyword matching.
- It calls Legal Data Hub for German/EU evidence.
- It returns `domain`, `summary`, `recommendation`, `company_basis`, `legal_basis`, and `escalate`.

## Data Strategy And Structure

### Playbook Data
Main playbook folder: `data/playbook`.

Current preferred data protection / DPA source:

- `data/playbook/bmw_group_dpa_negotiation_playbook.csv`
- This is the source-based DPA negotiation playbook normalized from `BMW Group DPA NEGOTIATION PLAYBOOK E.docx`.
- The backend loads this first for `data_protection` via `playbook_repository.py`.

Fallback/legacy data protection playbook:

- `data/playbook/bmw_data_protection.csv`
- Used only if the source-based DPA playbook is unavailable or a specific legacy rule ID is needed.

Litigation playbook:

- `data/playbook/bmw_litigation.csv`

Common playbook CSV columns:

- `id`: rule ID, e.g. `DPA-001`, `DPA-004`, `LT-003`.
- `title`: short rule name.
- `severity`: `low`, `medium`, `high`, or `blocker`.
- `default`: default BMW position.
- `why_it_matters`: risk/business/legal rationale.
- `preferred_position`: preferred clause position.
- `fallback_1`, `fallback_2`: acceptable fallbacks.
- `red_line`: unacceptable clause position.
- `escalation_trigger`: when to escalate to Legal.
- `legal_basis`: legal basis text, e.g. GDPR/BGB/ZPO references.
- `sample_clause`: problematic sample wording.
- `approved_fix`: preferred replacement/fix language.
- `owner`: internal owner/team.
- `last_reviewed`: date string.

`bmw_group_dpa_negotiation_playbook.csv` additionally includes:

- `source_playbook_clause`
- `source_playbook_file`

Supporting playbook documents in `data/playbook` include `.docx`, `.xlsx`, and `.pdf` versions for demos/uploads. The app currently uses the CSVs for automated rule matching.

### Legal Evidence Fallback Data
Fallback folder: `data/legal_fallback`.

Files:

- `datenschutz_evidence.csv`
- `litigation_evidence.csv`
- `German_Data_Privacy_and_Litigation_Evidence_Digest.xlsx`

Fallback CSV columns include:

- `source`
- `citation`
- `quote`
- `url`
- `domain`
- `use_case`
- `source_type`
- `notes`

Fallback evidence must remain clearly identified as fallback evidence and not be represented as live Otto Schmidt research.

### Sample Data
Sample folder: `data/samples`.

Important contract samples:

- `data/samples/sample_dpa.txt`
- `data/samples/sample_litigation_contract.txt`
- `data/samples/contracts/BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.docx`
- `data/samples/contracts/BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.pdf`
- `data/samples/contracts/BMW_RheinKlar_Litigation_Support_Problem_Draft.docx`
- `data/samples/contracts/BMW_RheinKlar_Litigation_Support_Problem_Draft.pdf`
- `data/samples/contracts/BMW_Group_DPA_Problem_01_Processor_Analytics_Subprocessors.docx`
- `data/samples/contracts/BMW_Group_DPA_Problem_02_Breach_Security_Audit.docx`
- `data/samples/contracts/BMW_Group_DPA_Problem_03_Transfers_Retention.docx`
- `data/samples/contracts/BMW_Group_DPA_Problem_04_All_Redlines.docx`
- Matching PDFs exist for the `BMW_Group_DPA_Problem_*` documents.
- `data/samples/contracts/bmw_group_dpa_problem_matrix.csv` describes expected problem scenarios.

Escalation samples:

- `data/samples/escalation/email_thread_datenschutz_atlasedge.csv`
- `data/samples/escalation/meeting_transcript_datenschutz_atlasedge.docx`

Case files:

- `data/samples/case_files/german_litigation_case_timeline.csv`
- `data/samples/case_files/german_data_privacy_case_digest.csv`

Golden data:

- `data/samples/golden_expected_findings.csv`

## SQLite Persistence

The default database is local SQLite at `storage/harvey.db` unless `DATABASE_URL` is set.

Contract persistence:

- Service: `backend/app/services/contract_repository.py`
- Tables: `contracts`, `contract_versions`
- Tracks contract identities, version numbers, document metadata, review result JSON, and AI suggestions.

Escalation persistence:

- Service: `backend/app/services/escalation_repository.py`
- Table: `escalations`
- Tracks ticket ID, contract/version links, status, source agents, source finding IDs, AI suggestions, legal decisions, legal notes, and timeline.

Ask Donna History persistence:

- Service: `backend/app/services/history_repository.py`
- Tables:
  - `history_threads`: one chat/contract history item.
  - `history_messages`: user/assistant transcript.
  - `history_runs`: run payload, visible reasoning, sources used, routed agents, findings.
  - `history_events`: business/AI/legal timeline events.
- Contract statuses for history:
  - `approved`
  - `pending_legal`
  - `dropped`

History stores visible reasoning only: routing summary, agent steps, findings, source usage, next action, and status. Do not store or expose hidden chain-of-thought.

## Legal Data Hub / Otto Schmidt

The app tries live Otto Schmidt / Legal Data Hub first when credentials are configured.

Environment variables:

```text
LDA_CLIENT=
LDA_SECRET=
OPENAI_API_KEY=
DATABASE_URL=
LEGAL_DATA_HUB_BASE_URL=https://api.legal-data-analytics.com
LEGAL_DATA_HUB_SEARCH_PATH=/semantic-search
LEGAL_DATA_HUB_AUTH_MODE=basic
LEGAL_DATA_HUB_DATA_ASSETS=Gesetze,Rechtsprechung
LEGAL_DATA_HUB_TIMEOUT=8
USE_LEGAL_FALLBACK=true
```

Status endpoint:

```text
GET /legal-qa/legal-data-hub/status
```

Current observed issue:

- Credentials are configured in the local environment.
- The configured default host `api.legal-data-analytics.com` currently fails DNS resolution from this machine.
- Status reports `ConnectError: [Errno -2] Name or service not known`.
- Ask Donna therefore falls back to `data/legal_fallback` and includes `retrieval_mode: "fallback"` plus `fallback_reason`.

To fix live Otto Schmidt usage, obtain the actual Legal Data Hub base URL/search path/auth mode from the provider/API docs and update `.env`. Do not hardcode secrets.

## Important API Endpoints

Ask Donna / intake:

- `GET /api/config`
- `GET /api/dashboard`
- `POST /api/demo`
- `POST /api/analyze`

`POST /api/analyze` accepts multipart form fields:

- `message`: combined question/context/contract text.
- `mode`: `general_question` or `contract_review`.
- `thread_id`: optional existing history thread.
- `is_final_version`: boolean.
- `files`: uploaded files.
- Legacy fields `question`, `context`, `selected_sources`, and `selected_agents` still exist for backward compatibility.

History:

- `GET /api/history`
- `GET /api/history/{thread_id}`
- `POST /api/history/{thread_id}/drop`

Legal Q&A:

- `POST /legal-qa`
- `GET /legal-qa/legal-data-hub/status`

Contracts:

- `POST /contracts/review`
- `POST /contracts/review/upload`
- `POST /contracts/{contract_id}/review`
- `POST /contracts/{contract_id}/review/upload`
- `GET /contracts/{contract_id}/versions`
- `GET /contracts/{contract_id}/versions/{version_number}`
- `POST /contracts/{contract_id}/versions/{version_number}/escalate`

Escalations:

- `GET /escalations`
- `GET /escalations/{escalation_id}`
- `POST /escalations/{escalation_id}/chat`
- `POST /escalations/{escalation_id}/decision`

## What Still Needs Implementation

High priority:

- Fix live Otto Schmidt / Legal Data Hub connectivity by confirming the real base URL, path, and auth scheme.
- Expand `LegalCheckerAgent`; it currently only flags a narrow data-subject-rights waiver trigger.
- Make playbook matching more robust than keyword scoring:
  - Match by semantic similarity or clause extraction.
  - Return all materially relevant rules.
  - Avoid selecting weakly related fallback rows for broad questions.
- Connect final `pending_legal` History items to richer legal-team workflows in the frontend.

Medium priority:

- Split the large `frontend/src/App.tsx` into page/components once demo behavior stabilizes.
- Add frontend tests or Playwright smoke tests for Ask Donna and History.
- Improve contract identity creation from Ask Donna final-review runs. Current Ask Donna runs use generated `intake-*` IDs and History status; the richer contract version APIs exist separately.
- Add clear UI display of `retrieval_mode` and `fallback_reason` in source panels/history details.
- Add a full frontend Escalations page under Legal.
- Replace dashboard placeholder metrics with unified history/contract/escalation metrics.

Lower priority:

- Add authentication/authorization.
- Add OCR and advanced document parsing.
- Add migrations instead of SQLAlchemy `create_all` / light schema evolution.
- Improve counterparty/effective-date extraction.
- Clean up old backup frontend folders if no longer needed.

## Verification

Backend:

```bash
cd backend
python -m pip install -e ".[dev]"
python -m pytest
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run build
npm run dev
```

Default URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Backend health: `http://localhost:8000/health`
- Legal Data Hub status: `http://localhost:8000/legal-qa/legal-data-hub/status`

Most recent verification after Ask Donna/History/playbook/Legal Data Hub updates:

- `python -m pytest backend/tests` -> 28 passed
- `npm run build` from `frontend/` -> passed

## Current Constraints

- This is still a demo, not a production legal system.
- No production auth.
- Live Otto Schmidt is configured but currently unreachable from this environment until the correct reachable endpoint is supplied.
- Fallback evidence is useful for reliability but must be labelled as fallback.
- Legal outputs must be validated by legal experts before demo claims are made.
