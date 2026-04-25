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

        return AgentResult(
            agent_name="risk_aggregator",
            summary="Aggregated agent findings and determined escalation status.",
            findings=findings,
            suggestions=suggestions,
            confidence=min([r.confidence for r in results], default=0.0),
            requires_escalation=requires_escalation,
            metadata={"highest_severity_score": highest, "agent_count": len(results)},
        )
