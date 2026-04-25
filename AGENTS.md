# Project Context

## Product Goal
Harvey is a 24-hour hackathon demo for a BMW-focused AI contract assistant. It helps business and technical teams review contracts, ask legal/playbook questions, and escalate risky contracts to legal counsel with full context.

The system must not pretend to replace lawyers. It should make routine review faster, explain risk clearly, suggest fixes, and escalate issues that require legal judgment.

## Priority Features
1. Contract review against BMW mock playbook rules and German legal evidence.
2. Escalated contract investigation for the legal team.
3. Legal and playbook Q&A for business and technical users.
4. Basic AI performance dashboard.

## Architecture
The project uses a FastAPI backend and a Vite React frontend.

Backend:
- `backend/app/main.py`: FastAPI entrypoint.
- `backend/app/api`: route modules for contracts, Legal Q&A, escalations, and dashboard.
- `backend/app/agents`: modular agents. Each agent implements `run(context) -> AgentResult`.
- `backend/app/workflows`: orchestration for contract review, Legal Q&A, and escalation investigation.
- `backend/app/services/legal_data_hub.py`: isolated Legal Data Hub adapter with fallback fixture support.

Frontend:
- `frontend/src/App.tsx`: page shell and route switching.
- `frontend/src/pages`: Contract Review, Legal Q&A, Escalations, and Dashboard screens.
- `frontend/src/api/client.ts`: browser API client.

Data:
- `data/playbook`: mock BMW playbook rules.
- `data/samples`: sample contracts, email thread, and meeting transcript.
- `data/legal_fallback`: fallback legal evidence used when live Legal Data Hub calls fail.

Docs:
- `docs/expert-instructions.md`: work assignment for the two technical experts and two legal experts.
- `docs/api-contract.md`: initial backend API response shapes.
- `docs/legal-answer-standards.md`: answer quality requirements for Legal Q&A.
- `docs/skeleton-template.md`: contributor guide for the scaffold.

## Agent Model
Agents are intentionally replaceable. A new agent should implement the shared interface in `backend/app/agents/base.py` and return an `AgentResult` with:

- `summary`
- `findings`
- `suggestions`
- `confidence`
- `requires_escalation`
- `metadata`

The current contract review workflow runs:
1. Contract Understanding Agent
2. BMW Playbook Checker Agent
3. German Legal Checker Agent
4. Risk Aggregator

## Legal Data Strategy
Use Legal Data Hub live calls when credentials and API availability allow it. Use fallback fixtures for demo reliability. Fallback evidence must remain clearly identifiable as fallback evidence and should not be presented as live legal research.

Environment variables expected in `.env`:

```text
LDA_CLIENT=
LDA_SECRET=
OPENAI_API_KEY=
```

`.env` is ignored by Git.

## Local Development
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
npm run dev
```

Default URLs:
- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- Backend health: `http://localhost:8000/health`

## Current Constraints
- This is a skeleton, not a production system.
- No production authentication or authorization yet.
- No persistent database implementation yet.
- No OCR or advanced document parsing yet.
- Legal outputs are starter examples and must be validated by legal experts before demo claims are made.
