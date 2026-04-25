from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKER = "blocker"


class Evidence(BaseModel):
    source: str
    citation: str
    quote: str | None = None
    url: str | None = None


class Suggestion(BaseModel):
    finding_id: str
    proposed_text: str
    rationale: str


class Finding(BaseModel):
    id: str
    title: str
    description: str
    severity: Severity
    clause_reference: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    requires_escalation: bool = False


class ReviewContext(BaseModel):
    contract_id: str
    contract_text: str
    contract_type: str | None = None
    playbook_scope: list[str] = Field(default_factory=list)
    user_question: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    agent_name: str
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_escalation: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class Agent(ABC):
    name: str

    @abstractmethod
    async def run(self, context: ReviewContext) -> AgentResult:
        """Run one isolated review step."""
