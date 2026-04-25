from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from app.agents.base import AgentResult
from app.services.contract_repository import Base, _build_engine, _default_database_url


PENDING_LEGAL = "pending_legal"
ACCEPTED = "accepted"
DENIED = "denied"
FINAL_STATUSES = {ACCEPTED, DENIED}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    escalation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(24), unique=True, index=True, nullable=True)
    contract_id: Mapped[str] = mapped_column(String(64), index=True)
    version_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True, default=PENDING_LEGAL)
    reason: Mapped[str] = mapped_column(String(500))
    review_result: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_agents: Mapped[list[str]] = mapped_column(JSON)
    source_finding_ids: Mapped[list[str]] = mapped_column(JSON)
    ai_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    legal_notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    fix_suggestions: Mapped[list[str]] = mapped_column(JSON, default=list)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EscalationAlreadyDecidedError(ValueError):
    pass


class EscalationRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.engine = _build_engine(database_url or _default_database_url())
        Base.metadata.create_all(self.engine)
        _ensure_escalation_schema(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_from_review(
        self,
        *,
        contract_id: str,
        review_result: AgentResult,
        contract_text: str | None = None,
        version_id: str | None = None,
        version_number: int | None = None,
        business_reason: str | None = None,
        requested_by: str | None = None,
        force: bool = False,
    ) -> dict[str, Any] | None:
        if not review_result.requires_escalation and not force:
            return None

        source_agents, source_finding_ids = _source_attribution(review_result, include_all_findings=force)
        stored_review_result = review_result.model_dump(mode="json")
        if contract_text is not None:
            stored_review_result.setdefault("metadata", {})["contract_text"] = contract_text
        if business_reason:
            stored_review_result.setdefault("metadata", {})["business_escalation_reason"] = business_reason
        if requested_by:
            stored_review_result.setdefault("metadata", {})["business_escalation_requested_by"] = requested_by
        escalation = Escalation(
            escalation_id=f"esc-{uuid4().hex[:12]}",
            ticket_id=_new_ticket_id(),
            contract_id=contract_id,
            version_id=version_id,
            version_number=version_number,
            status=PENDING_LEGAL,
            reason=business_reason or _escalation_reason(review_result),
            review_result=stored_review_result,
            source_agents=source_agents,
            source_finding_ids=source_finding_ids,
            ai_suggestions=[suggestion.model_dump(mode="json") for suggestion in review_result.suggestions],
            fix_suggestions=[],
        )
        with self.session_factory() as session:
            if version_id:
                existing = session.scalar(
                    select(Escalation)
                    .where(Escalation.version_id == version_id)
                    .order_by(Escalation.created_at.desc())
                )
                if existing:
                    return _escalation_payload(existing, include_review=False)
            session.add(escalation)
            session.commit()
            session.refresh(escalation)
            return _escalation_payload(escalation, include_review=False)

    def list_escalations(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            statement = select(Escalation).order_by(Escalation.created_at.desc())
            if status:
                statement = statement.where(Escalation.status == status)
            escalations = session.scalars(statement).all()
            return [_escalation_payload(escalation, include_review=False) for escalation in escalations]

    def get_escalation(self, escalation_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            escalation = session.scalar(select(Escalation).where(Escalation.escalation_id == escalation_id))
            if escalation is None:
                return None
            return _escalation_payload(escalation, include_review=True)

    def decide_escalation(
        self,
        *,
        escalation_id: str,
        decision: str,
        notes: str | None,
        fix_suggestions: list[str],
        decided_by: str | None,
    ) -> dict[str, Any] | None:
        with self.session_factory() as session:
            escalation = session.scalar(select(Escalation).where(Escalation.escalation_id == escalation_id))
            if escalation is None:
                return None
            if escalation.status in FINAL_STATUSES:
                raise EscalationAlreadyDecidedError(escalation_id)

            escalation.status = decision
            escalation.legal_notes = notes
            escalation.fix_suggestions = fix_suggestions
            escalation.decided_by = decided_by
            escalation.decided_at = _utc_now()
            escalation.updated_at = escalation.decided_at
            session.commit()
            session.refresh(escalation)
            return _escalation_payload(escalation, include_review=True)

    def escalation_metrics(self) -> dict[str, Any]:
        with self.session_factory() as session:
            escalations = session.scalars(select(Escalation)).all()

        totals = {
            "total": len(escalations),
            "pending": sum(1 for escalation in escalations if escalation.status == PENDING_LEGAL),
            "accepted": sum(1 for escalation in escalations if escalation.status == ACCEPTED),
            "denied": sum(1 for escalation in escalations if escalation.status == DENIED),
        }
        agent_metrics: dict[str, dict[str, Any]] = {}
        for escalation in escalations:
            agents = list(dict.fromkeys(escalation.source_agents or []))
            for agent_name in agents:
                metrics = agent_metrics.setdefault(
                    agent_name,
                    {
                        "agent_name": agent_name,
                        "total": 0,
                        "pending": 0,
                        "accepted": 0,
                        "denied": 0,
                        "false_escalations": 0,
                        "positive_escalations": 0,
                        "false_escalation_rate": 0.0,
                    },
                )
                metrics["total"] += 1
                if escalation.status == PENDING_LEGAL:
                    metrics["pending"] += 1
                elif escalation.status == ACCEPTED:
                    metrics["accepted"] += 1
                    metrics["false_escalations"] += 1
                elif escalation.status == DENIED:
                    metrics["denied"] += 1
                    metrics["positive_escalations"] += 1

        for metrics in agent_metrics.values():
            decided = metrics["accepted"] + metrics["denied"]
            metrics["false_escalation_rate"] = metrics["false_escalations"] / decided if decided else 0.0

        by_agent = sorted(agent_metrics.values(), key=lambda item: item["agent_name"])
        return {
            "total_escalations": totals["total"],
            "pending_escalations": totals["pending"],
            "accepted_escalations": totals["accepted"],
            "denied_escalations": totals["denied"],
            "false_escalations": totals["accepted"],
            "positive_escalations": totals["denied"],
            "top_false_escalation_agent": _top_agent(by_agent, "false_escalations"),
            "top_positive_escalation_agent": _top_agent(by_agent, "positive_escalations"),
            "per_agent": by_agent,
        }


def _source_attribution(review_result: AgentResult, *, include_all_findings: bool = False) -> tuple[list[str], list[str]]:
    agents: list[str] = []
    finding_ids: list[str] = []
    for agent_result in review_result.metadata.get("agent_results", []):
        agent_name = agent_result.get("agent_name")
        if not agent_name or agent_name == "risk_aggregator":
            continue
        if not include_all_findings and not agent_result.get("requires_escalation"):
            continue
        agent_findings = agent_result.get("findings", [])
        if include_all_findings and not agent_findings:
            continue
        agents.append(agent_name)
        for finding in agent_result.get("findings", []):
            if (include_all_findings or finding.get("requires_escalation")) and finding.get("id"):
                finding_ids.append(finding["id"])

    if not agents and review_result.requires_escalation:
        agents.append(review_result.agent_name)
        finding_ids.extend(finding.id for finding in review_result.findings if finding.requires_escalation)
    if not agents and include_all_findings and review_result.findings:
        agents.append(review_result.agent_name)
        finding_ids.extend(finding.id for finding in review_result.findings)

    return list(dict.fromkeys(agents)), list(dict.fromkeys(finding_ids))


def _escalation_reason(review_result: AgentResult) -> str:
    blocker_or_high = [
        finding.title
        for finding in review_result.findings
        if finding.requires_escalation or finding.severity.value in {"high", "blocker"}
    ]
    if blocker_or_high:
        return "; ".join(blocker_or_high[:3])
    return "AI review required legal decision."


def _escalation_payload(escalation: Escalation, *, include_review: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": escalation.escalation_id,
        "ticket_id": escalation.ticket_id or _ticket_id_from_pk(escalation.id),
        "contract_id": escalation.contract_id,
        "version_id": escalation.version_id,
        "version_number": escalation.version_number,
        "status": escalation.status,
        "reason": escalation.reason,
        "highest_severity": _highest_severity(escalation.review_result),
        "source_agents": escalation.source_agents,
        "source_finding_ids": escalation.source_finding_ids,
        "ai_suggestions": escalation.ai_suggestions,
        "legal_decision": None if escalation.status == PENDING_LEGAL else escalation.status,
        "legal_notes": escalation.legal_notes,
        "fix_suggestions": escalation.fix_suggestions or [],
        "decided_by": escalation.decided_by,
        "created_at": escalation.created_at.isoformat(),
        "updated_at": escalation.updated_at.isoformat(),
        "decided_at": escalation.decided_at.isoformat() if escalation.decided_at else None,
        "next_owner": "business" if escalation.status == DENIED else ("legal" if escalation.status == PENDING_LEGAL else None),
        "timeline": _timeline(escalation),
    }
    if include_review:
        payload["review_result"] = escalation.review_result
        payload["contract_text"] = _contract_text(escalation.review_result)
        payload["trigger_annotations"] = _trigger_annotations(escalation.review_result)
        payload["agent_outputs"] = escalation.review_result.get("metadata", {}).get("agent_results", [])
    return payload


def _ensure_escalation_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "escalations" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("escalations")}
    with engine.begin() as connection:
        if "ticket_id" not in columns:
            connection.execute(text("ALTER TABLE escalations ADD COLUMN ticket_id VARCHAR(24)"))

        rows = connection.execute(
            text("SELECT id FROM escalations WHERE ticket_id IS NULL OR ticket_id = '' ORDER BY id")
        ).mappings()
        for row in rows:
            connection.execute(
                text("UPDATE escalations SET ticket_id = :ticket_id WHERE id = :id"),
                {"ticket_id": _ticket_id_from_pk(int(row["id"])), "id": row["id"]},
            )


def _new_ticket_id() -> str:
    return f"TCK-{uuid4().hex[:8].upper()}"


def _ticket_id_from_pk(pk: int) -> str:
    return f"TCK-{pk:06d}"


def _highest_severity(review_result: dict[str, Any]) -> str:
    severities: list[str] = []
    for finding in review_result.get("findings") or []:
        severity = finding.get("severity")
        if isinstance(severity, str):
            severities.append(severity)

    for agent_result in review_result.get("metadata", {}).get("agent_results") or []:
        for finding in agent_result.get("findings") or []:
            severity = finding.get("severity")
            if isinstance(severity, str):
                severities.append(severity)

    if not severities:
        return "info"
    return max(severities, key=_severity_weight)


def _severity_weight(severity: str) -> int:
    weights = {
        "info": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "blocker": 4,
    }
    return weights.get(severity, 0)


def _timeline(escalation: Escalation) -> list[dict[str, str | None]]:
    events: list[dict[str, str | None]] = [
        {"event": "reviewed_by_ai", "at": escalation.created_at.isoformat()},
        {"event": "escalated", "at": escalation.created_at.isoformat()},
    ]
    if escalation.decided_at:
        events.append({"event": escalation.status, "at": escalation.decided_at.isoformat()})
    return events


def _top_agent(metrics: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    candidates = [item for item in metrics if item[key] > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[key], item["agent_name"]))


def _contract_text(review_result: dict[str, Any]) -> str:
    metadata = review_result.get("metadata", {})
    contract_text = metadata.get("contract_text")
    return contract_text if isinstance(contract_text, str) else ""


def _trigger_annotations(review_result: dict[str, Any]) -> list[dict[str, Any]]:
    agent_results = review_result.get("metadata", {}).get("agent_results") or []
    if not agent_results:
        agent_results = [review_result]

    aggregate_suggestions = review_result.get("suggestions") or []
    annotations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for agent_result in agent_results:
        agent_name = str(agent_result.get("agent_name") or "unknown_agent")
        if agent_name == "risk_aggregator":
            continue

        agent_suggestions = list(agent_result.get("suggestions") or [])
        suggestions = agent_suggestions + aggregate_suggestions
        for finding in agent_result.get("findings") or []:
            finding_id = str(finding.get("id") or "")
            if not finding_id:
                continue
            key = (agent_name, finding_id)
            if key in seen:
                continue
            seen.add(key)

            trigger = finding.get("trigger") or {}
            ruling = finding.get("ruling") or _ruling_from_evidence(finding.get("evidence") or [])
            annotations.append(
                {
                    "id": f"{agent_name}:{finding_id}",
                    "agent_name": agent_name,
                    "finding_id": finding_id,
                    "title": finding.get("title"),
                    "description": finding.get("description"),
                    "severity": finding.get("severity"),
                    "requires_escalation": finding.get("requires_escalation", False),
                    "start": trigger.get("start"),
                    "end": trigger.get("end"),
                    "text": trigger.get("text") or finding.get("clause_reference"),
                    "ruling": ruling,
                    "suggestions": _suggestions_for_finding(suggestions, finding_id),
                }
            )

    return annotations


def _ruling_from_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in evidence:
        if item.get("citation") or item.get("quote"):
            return {
                "source": item.get("source"),
                "citation": item.get("citation"),
                "quote": item.get("quote"),
                "url": item.get("url"),
            }
    return None


def _suggestions_for_finding(suggestions: list[dict[str, Any]], finding_id: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for suggestion in suggestions:
        if suggestion.get("finding_id") != finding_id:
            continue
        key = (str(suggestion.get("proposed_text")), str(suggestion.get("rationale")))
        if key in seen:
            continue
        seen.add(key)
        matched.append(suggestion)
    return matched
