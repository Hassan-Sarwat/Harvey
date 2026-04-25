from __future__ import annotations

from app.agents.base import AgentResult, ReviewContext


class EscalationPackager:
    def build_package(self, context: ReviewContext, review_result: AgentResult) -> dict:
        return {
            "contract_id": context.contract_id,
            "summary": review_result.summary,
            "findings": [finding.model_dump() for finding in review_result.findings],
            "suggestions": [suggestion.model_dump() for suggestion in review_result.suggestions],
            "communications": context.metadata.get("communications", []),
            "versions": context.metadata.get("versions", []),
            "requires_legal_decision": review_result.requires_escalation,
        }
