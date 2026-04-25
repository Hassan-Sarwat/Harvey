# Legal Expert 1: BMW Mock Playbook and Contract Review Rules

## Ownership
- BMW mock playbook rules for data protection and litigation.
- Default values, risk thresholds, escalation triggers, and replacement language.
- Golden expected findings for sample contracts.

## First Tasks
1. Review `data/playbook/bmw_data_protection.csv`, `data/playbook/bmw_litigation.csv`, and the matching `.docx`/`.xlsx` playbook exports.
2. Add missing rules for mandatory clauses, risky ambiguity, illegal terms, default-value deviations, and escalation requirements.
3. Create expected findings for `data/samples/sample_dpa.txt` and `data/samples/sample_litigation_contract.txt`.
4. Provide approved replacement language for common fixes.

## Acceptance Criteria
- Each rule has an id, title, severity, default position, and escalation trigger.
- Review expectations distinguish between fixable issues and legal escalations.
- Data protection and litigation examples are both covered.
- Technical contributors can implement checks without inventing legal policy.
