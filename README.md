# Harvey

Legal Tech Hackathon BMW Challenge.

Harvey is a 24-hour demo scaffold for a BMW-focused AI assistant that helps business and technical teams review contracts, ask legal/playbook questions, and escalate risky drafts to legal counsel.

## Structure

- `backend/`: FastAPI app, modular agents, workflows, Legal Data Hub adapter, and backend tests.
- `frontend/`: Vite React app with contract review, Legal Q&A, escalations, and dashboard pages.
- `data/`: mock BMW playbooks, sample contracts, communications, and fallback legal evidence.
- `docs/`: API contract, skeleton guide, legal answer standards, and per-expert instructions.

## Backend

```bash
cd backend
python -m pip install -e ".[dev]"
python -m pytest
uvicorn app.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Team Handoff

Start with `docs/skeleton-template.md`, then use the expert-specific files:

- `docs/expert-technical-1.md`
- `docs/expert-technical-2.md`
- `docs/expert-legal-1.md`
- `docs/expert-legal-2.md`
