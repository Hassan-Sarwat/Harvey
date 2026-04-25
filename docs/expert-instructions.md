# Expert Instructions

This file assigns work across the four-person team. Each contributor should keep changes within their ownership area when possible and add tests or expected outputs before integrating new behavior into the demo.

## Technical Expert 1: Backend and Agent Platform

### Ownership
- FastAPI routes and backend app structure.
- Agent interface, registry, workflow runner, and aggregation behavior.
- Legal Data Hub adapter and fallback behavior.
- Backend test suite.

### First Tasks
1. Confirm `python -m pytest` passes from `backend/`.
2. Replace endpoint stubs with persistence-backed handlers.
3. Add an agent registry so new agents can be enabled by configuration.
4. Expand `LegalDataHubClient` once live endpoint shape is verified with the provided credentials.
5. Add mocked tests for live success, auth failure, throttling, malformed responses, and fixture fallback.

### Acceptance Criteria
- Each agent can be tested independently.
- Review workflow can run without Legal Data Hub availability.
- API responses are stable enough for the frontend to consume.
- No legal conclusion is hardcoded unless it is backed by a playbook fixture or evidence fixture.

## Technical Expert 2: Frontend and Demo Experience

### Ownership
- React app structure, navigation, and page-level state.
- API client and frontend error handling.
- Contract review, Legal Q&A, escalation investigation, and dashboard screens.
- Frontend smoke tests once testing dependencies are added.

### First Tasks
1. Confirm `npm install` and `npm run dev` work from `frontend/`.
2. Replace raw JSON outputs with structured findings, evidence, suggestions, and decision controls.
3. Add accept/reject suggestion actions on the review page.
4. Add escalation detail timeline with contract versions, emails, transcripts, AI suggestions, and legal decision panel.
5. Add dashboard cards for AI approvals, escalations, common deviations, and default-value drift.

### Acceptance Criteria
- Demo can be navigated without backend changes by using the current stub endpoints.
- Legal citations and playbook arguments are visible on review and Q&A screens.
- Rejected high-risk suggestions visibly trigger escalation.
- Layout remains usable on laptop screens during the live demo.

## Legal Expert 1: BMW Mock Playbook and Contract Review Rules

### Ownership
- BMW mock playbook rules for data protection and litigation.
- Default values, risk thresholds, escalation triggers, and replacement language.
- Golden expected findings for sample contracts.

### First Tasks
1. Review `data/playbook/bmw_data_protection.json` and `data/playbook/bmw_litigation.json`.
2. Add missing rules for mandatory clauses, risky ambiguity, illegal terms, default-value deviations, and escalation requirements.
3. Create expected findings for `data/samples/sample_dpa.txt` and `data/samples/sample_litigation_contract.txt`.
4. Provide approved replacement language for common fixes.

### Acceptance Criteria
- Each rule has an id, title, severity, default position, and escalation trigger.
- Review expectations distinguish between fixable issues and legal escalations.
- Data protection and litigation examples are both covered.
- Technical contributors can implement checks without inventing legal policy.

## Legal Expert 2: Legal Evidence, Q&A Standards, and Escalation Validation

### Ownership
- Legal Data Hub source strategy.
- Legal Q&A answer standards for business and technical users.
- Fallback legal evidence fixtures.
- Legal review standards for escalated contract packages.

### First Tasks
1. Review `data/legal_fallback/datenschutz_evidence.json` and `data/legal_fallback/litigation_evidence.json`.
2. Define which Legal Data Hub data assets should be queried for data protection and litigation questions.
3. Expand `docs/legal-answer-standards.md` with answer quality rules and escalation language.
4. Define legal validation checks for escalation packages, including required history, communications, AI suggestions, and user decisions.

### Acceptance Criteria
- Q&A answers include plain-language summary, practical recommendation, company basis, legal basis, and escalation warning when needed.
- Fallback evidence is realistic enough for demos but clearly marked as fallback.
- Escalated cases include enough context for legal counsel to approve, deny, or request changes.
- Legal uncertainty is surfaced instead of overclaimed.
