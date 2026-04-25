# Harvey Skeleton Template

## Purpose
This repository is a 24-hour demo scaffold for a BMW-focused contract assistant. It has three primary workflows:

- Contract review against BMW playbook rules and German legal evidence.
- Legal Q&A for business and technical users.
- Escalation investigation for legal counsel.

## Architecture
- `backend/app/agents`: replaceable review agents. Each agent implements `run(context) -> AgentResult`.
- `backend/app/workflows`: orchestration for review, legal Q&A, and escalation investigation.
- `backend/app/services`: external integrations, especially Legal Data Hub.
- `frontend/src/pages`: route-level screens for the demo.
- `data/playbook`: BMW mock rules owned by legal contributors.
- `data/legal_fallback`: deterministic legal evidence used when live API calls fail.

## Parallel Work Rules
- Keep agent outputs compatible with `AgentResult`.
- Add tests before wiring new logic into a workflow.
- Legal contributors should edit fixture and standards files first, then ask technical contributors to wire new fields.
- Technical contributors should avoid hardcoding legal conclusions outside fixtures, playbooks, or Legal Data Hub evidence.

## Local Commands
Backend:

```bash
cd backend
python -m pytest
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```
