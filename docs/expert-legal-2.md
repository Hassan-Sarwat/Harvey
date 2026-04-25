# Legal Expert 2: Legal Evidence, Q&A Standards, and Escalation Validation

## Ownership
- Legal Data Hub source strategy.
- Legal Q&A answer standards for business and technical users.
- Fallback legal evidence fixtures.
- Legal review standards for escalated contract packages.

## First Tasks
1. Review `data/legal_fallback/datenschutz_evidence.csv`, `data/legal_fallback/litigation_evidence.csv`, and the evidence digest workbook.
2. Define which Legal Data Hub data assets should be queried for data protection and litigation questions.
3. Expand `docs/legal-answer-standards.md` with answer quality rules and escalation language.
4. Define legal validation checks for escalation packages, including required history, communications, AI suggestions, and user decisions.

## Acceptance Criteria
- Q&A answers include plain-language summary, practical recommendation, company basis, legal basis, and escalation warning when needed.
- Fallback evidence is realistic enough for demos but clearly marked as fallback.
- Escalated cases include enough context for legal counsel to approve, deny, or request changes.
- Legal uncertainty is surfaced instead of overclaimed.
