# Harvey Task Tracker

## Implemented

- Ask Donna chat UI under the General sidebar section.
- Combined question, business context, and pasted contract text into one chat composer.
- Ask Donna modes:
  - `general_question`
  - `contract_review`
- Automatic source and agent routing; manual source/agent selectors were removed from the UI.
- Contract review workflow routes through:
  - Contract Understanding Agent
  - BMW Playbook Checker Agent
  - German Legal Checker Agent
  - Risk Aggregator
- Source-based BMW DPA playbook loading from `data/playbook/bmw_group_dpa_negotiation_playbook.csv`.
- Litigation playbook loading from `data/playbook/bmw_litigation.csv`.
- Legal Q&A now resolves broad/general questions into a concrete domain such as `data_protection` or `litigation`.
- Ask Donna responses identify the selected BMW playbook rule and include German/EU legal evidence.
- Legal Data Hub fallback evidence is clearly marked with `retrieval_mode: "fallback"` and `fallback_reason`.
- Legal Data Hub status endpoint:
  - `GET /legal-qa/legal-data-hub/status`
- Persistent History page under General:
  - previous chats
  - replies
  - visible AI reasoning
  - source usage
  - findings
  - contract timeline events
- Final-version handling for contract review:
  - `approved`
  - `pending_legal`
  - `dropped`
- Ask Donna right-side panel was removed; the chat/result layout is now single-column.
- Backend tests currently pass.
- Frontend production build currently passes.

## To Be Implemented

1. Fix Otto Schmidt / Legal Data Hub API
   - Confirm the correct live API base URL, search path, auth mode, and data asset names.
   - Update `.env` with the working API configuration.
   - Verify `GET /legal-qa/legal-data-hub/status` reports `live_ready: true`.
   - Ensure Ask Donna uses live Otto Schmidt evidence instead of fallback evidence when the API is reachable.

2. Implement dashboard with agent performance
   - Replace placeholder dashboard metrics with real data from History, contract review runs, and escalations.
   - Track per-agent run count, findings, escalation recommendations, accepted/denied escalation outcomes, false escalation rate, and positive escalation rate.
   - Show recent runs and agent-level performance trends in the frontend Dashboard view.
   - Add backend tests for dashboard metrics.

3. Include Escalations and tickets
   - Build the frontend Escalations page under the Legal section.
   - Display pending and decided tickets from `/escalations`.
   - Show ticket detail, source agents, source findings, AI suggestions, legal notes, and timeline.
   - Support Legal decisions:
     - accepted
     - denied with required fix suggestions
   - Link `pending_legal` History records to escalation tickets.
