from __future__ import annotations

from app.agents.base import AgentResult, ReviewContext
from app.agents.contract_understanding import ContractUnderstandingAgent
from app.agents.legal_checker import LegalCheckerAgent
from app.agents.playbook_checker import PlaybookCheckerAgent
from app.agents.risk_aggregator import RiskAggregator


class ContractReviewWorkflow:
    def __init__(self) -> None:
        self.agents = [
            ContractUnderstandingAgent(),
            PlaybookCheckerAgent(),
            LegalCheckerAgent(),
        ]
        self.aggregator = RiskAggregator()

    async def run(self, context: ReviewContext) -> AgentResult:
        results = [await agent.run(context) for agent in self.agents]
        aggregate = self.aggregator.combine(results)
        aggregate.metadata["agent_results"] = [result.model_dump() for result in results]
        return aggregate
