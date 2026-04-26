from __future__ import annotations

from app.agents.base import AgentResult, ReviewContext
from app.agents.contract_understanding import ContractUnderstandingAgent
from app.agents.contract_triage import ContractTriageAgent
from app.agents.legal_checker import LegalCheckerAgent
from app.agents.playbook_checker import PlaybookCheckerAgent
from app.agents.risk_aggregator import RiskAggregator


class ContractReviewWorkflow:
    def __init__(self) -> None:
        self.agents = [
            ContractUnderstandingAgent(),
            ContractTriageAgent(),
            PlaybookCheckerAgent(),
            LegalCheckerAgent(),
        ]
        self.aggregator = RiskAggregator()

    async def run(self, context: ReviewContext) -> AgentResult:
        results = []
        working_context = context
        for agent in self.agents:
            result = await agent.run(working_context)
            if agent.name == "contract_understanding" and not working_context.contract_type:
                inferred_type = result.metadata.get("inferred_contract_type")
                if isinstance(inferred_type, str) and inferred_type:
                    working_context = working_context.model_copy(update={"contract_type": inferred_type})
            results.append(result)
        for result in results:
            result.metadata["passed"] = _agent_passed(result)
        aggregate = self.aggregator.combine(results)
        aggregate.metadata["passed"] = _agent_passed(aggregate)
        aggregate.metadata["agent_results"] = [result.model_dump() for result in results]
        return aggregate


def _agent_passed(result: AgentResult) -> bool:
    return not result.requires_escalation and all(
        finding.severity.value not in {"high", "blocker"} for finding in result.findings
    )
