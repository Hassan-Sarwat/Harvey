from __future__ import annotations

from app.agents.base import AgentResult, ReviewContext
from app.agents.escalation_packager import EscalationPackager


class EscalationInvestigationWorkflow:
    def __init__(self) -> None:
        self.packager = EscalationPackager()

    async def run(self, context: ReviewContext, review_result: AgentResult) -> dict:
        return self.packager.build_package(context, review_result)
