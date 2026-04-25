# Technical Expert 1: Backend and Agent Platform

## Ownership
- FastAPI routes and backend app structure.
- Agent interface, registry, workflow runner, and aggregation behavior.
- Legal Data Hub adapter and fallback behavior.
- Backend test suite.

## First Tasks
1. Confirm `python -m pytest` passes from `backend/`.
2. Replace endpoint stubs with persistence-backed handlers.
3. Add an agent registry so new agents can be enabled by configuration.
4. Expand `LegalDataHubClient` once live endpoint shape is verified with the provided credentials.
5. Add mocked tests for live success, auth failure, throttling, malformed responses, and fixture fallback.

## Acceptance Criteria
- Each agent can be tested independently.
- Review workflow can run without Legal Data Hub availability.
- API responses are stable enough for the frontend to consume.
- No legal conclusion is hardcoded unless it is backed by a playbook fixture or evidence fixture.
