from __future__ import annotations

from app.agents.base import AgentResult, Finding, Severity


SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.BLOCKER: 4,
}


class RiskAggregator:
    def combine(self, results: list[AgentResult]) -> AgentResult:
        findings_by_id: dict[str, Finding] = {}
        for result in results:
            for finding in result.findings:
                existing = findings_by_id.get(finding.id)
                if existing is None or SEVERITY_ORDER[finding.severity] > SEVERITY_ORDER[existing.severity]:
                    findings_by_id[finding.id] = finding

        findings = list(findings_by_id.values())
        suggestions = [suggestion for result in results for suggestion in result.suggestions]
        requires_escalation = any(f.requires_escalation for f in findings)
        highest = max((SEVERITY_ORDER[f.severity] for f in findings), default=0)
        conditions = _escalation_conditions(results, findings)

        return AgentResult(
            agent_name="risk_aggregator",
            summary="Aggregated agent findings and determined escalation status.",
            findings=findings,
            suggestions=suggestions,
            confidence=min([r.confidence for r in results], default=0.0),
            requires_escalation=requires_escalation,
            metadata={
                "highest_severity_score": highest,
                "agent_count": len(results),
                "escalation_conditions": conditions,
            },
        )


def _escalation_conditions(results: list[AgentResult], findings: list[Finding]) -> list[dict[str, object]]:
    finding_ids = {finding.id for finding in findings}
    triage = next((result for result in results if result.agent_name == "contract_triage"), None)
    value = triage.metadata.get("contract_value_eur") if triage else None
    threshold = triage.metadata.get("contract_value_threshold_eur") if triage else None
    playbook_covered = bool(triage.metadata.get("playbook_covered")) if triage else True
    playbook_triggered = any(
        result.agent_name == "playbook_checker" and result.requires_escalation for result in results
    )
    legal_triggered = any(
        result.agent_name == "legal_checker" and result.requires_escalation for result in results
    )

    return [
        {
            "id": "playbook_deviation",
            "label": "Playbook deviation requires Legal",
            "triggered": playbook_triggered or legal_triggered,
        },
        {
            "id": "contract_value_threshold",
            "label": "Contract value exceeds threshold",
            "triggered": "contract-value-threshold" in finding_ids,
            "value_eur": value,
            "threshold_eur": threshold,
        },
        {
            "id": "matter_not_covered_by_playbook",
            "label": "Matter is not covered by active playbooks",
            "triggered": not playbook_covered or "matter-not-covered-by-playbook" in finding_ids,
        },
        {
            "id": "high_risk_matter",
            "label": "High-risk contract matter",
            "triggered": "high-risk-contract-matter" in finding_ids,
        },
    ]
