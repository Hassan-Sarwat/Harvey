from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from app.services.contract_repository import Base, _build_engine, _default_database_url


APPROVED = "approved"
PENDING_LEGAL = "pending_legal"
NEEDS_BUSINESS_INPUT = "needs_business_input"
DROPPED = "dropped"
CONTRACT_HISTORY_STATUSES = {APPROVED, PENDING_LEGAL, NEEDS_BUSINESS_INPUT, DROPPED}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HistoryThread(Base):
    __tablename__ = "history_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(40), index=True)
    item_type: Mapped[str] = mapped_column(String(40), index=True)
    contract_status: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    contract_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    version_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)


class HistoryMessage(Base):
    __tablename__ = "history_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_pk: Mapped[int] = mapped_column(ForeignKey("history_threads.id"), index=True)
    role: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class HistoryRun(Base):
    __tablename__ = "history_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_pk: Mapped[int] = mapped_column(ForeignKey("history_threads.id"), index=True)
    mode: Mapped[str] = mapped_column(String(40))
    reply: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[dict[str, Any]] = mapped_column(JSON)
    sources_used: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    routed_agents: Mapped[list[str]] = mapped_column(JSON)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class HistoryEvent(Base):
    __tablename__ = "history_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_pk: Mapped[int] = mapped_column(ForeignKey("history_threads.id"), index=True)
    actor: Mapped[str] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class HistoryRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.engine = _build_engine(database_url or _default_database_url())
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def record_run(
        self,
        *,
        thread_id: str | None,
        mode: str,
        message: str,
        result_payload: dict[str, Any],
        reasoning: dict[str, Any],
        sources_used: list[dict[str, Any]],
        uploaded_filenames: list[str],
        is_final_version: bool,
        contract_status: str | None,
        escalation_id: str | None = None,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            thread = _find_thread(session, thread_id) if thread_id else None
            if thread is None:
                thread = HistoryThread(
                    thread_id=f"thread-{uuid4().hex[:12]}",
                    title=_title_from_message(message),
                    mode=mode,
                    item_type="contract" if mode == "contract_review" else "chat",
                    contract_status=None,
                )
                session.add(thread)
                session.flush()

            matter_summary = result_payload.get("matter_summary") or {}
            thread.mode = mode
            thread.item_type = "contract" if mode == "contract_review" else "chat"
            thread.title = thread.title or _title_from_message(message)
            thread.contract_status = contract_status or thread.contract_status
            thread.contract_id = result_payload.get("contract_id") or thread.contract_id
            thread.version_id = result_payload.get("version_id") or thread.version_id
            thread.version_number = result_payload.get("version_number") or thread.version_number
            thread.escalation_id = escalation_id or result_payload.get("escalation_id") or thread.escalation_id
            thread.contract_type = result_payload.get("metrics", {}).get("contract_type") or thread.contract_type
            thread.counterparty = matter_summary.get("counterparty") or thread.counterparty
            thread.updated_at = _utc_now()

            user_message = HistoryMessage(
                message_id=f"msg-{uuid4().hex[:12]}",
                thread_pk=thread.id,
                role="user",
                content=message,
                message_metadata={
                    "mode": mode,
                    "uploaded_filenames": uploaded_filenames,
                    "is_final_version": is_final_version,
                },
            )
            assistant_message = HistoryMessage(
                message_id=f"msg-{uuid4().hex[:12]}",
                thread_pk=thread.id,
                role="assistant",
                content=str(result_payload.get("plain_answer") or result_payload.get("legal_answer") or ""),
                message_metadata={
                    "run_id": result_payload.get("id"),
                    "escalation_state": result_payload.get("escalation_state"),
                    "contract_status": contract_status,
                },
            )
            session.add_all([user_message, assistant_message])

            session.add(
                HistoryRun(
                    run_id=str(result_payload["id"]),
                    thread_pk=thread.id,
                    mode=mode,
                    reply=assistant_message.content,
                    reasoning=reasoning,
                    sources_used=sources_used,
                    routed_agents=list(result_payload.get("routed_agents") or []),
                    findings=list(result_payload.get("findings") or []),
                    result_payload=result_payload,
                )
            )

            session.add(
                HistoryEvent(
                    event_id=f"event-{uuid4().hex[:12]}",
                    thread_pk=thread.id,
                    actor="business",
                    event_type="message_submitted",
                    summary=_message_event_summary(mode, uploaded_filenames, is_final_version),
                    status=contract_status,
                    event_metadata={
                        "uploaded_filenames": uploaded_filenames,
                        "is_final_version": is_final_version,
                    },
                )
            )
            session.add(
                HistoryEvent(
                    event_id=f"event-{uuid4().hex[:12]}",
                    thread_pk=thread.id,
                    actor="ai",
                    event_type=_ai_event_type(contract_status),
                    summary=_ai_event_summary(result_payload, contract_status),
                    status=contract_status,
                    event_metadata={
                        "run_id": result_payload.get("id"),
                        "routed_agents": result_payload.get("routed_agents") or [],
                        "finding_count": len(result_payload.get("findings") or []),
                    },
                )
            )

            session.commit()
            session.refresh(thread)
            return self._detail_from_session(session, thread)

    def list_items(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            threads = session.scalars(select(HistoryThread).order_by(HistoryThread.updated_at.desc())).all()
            return [_thread_summary(thread) for thread in threads]

    def get_item(self, thread_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            thread = _find_thread(session, thread_id)
            if thread is None:
                return None
            return self._detail_from_session(session, thread)

    def drop_item(self, thread_id: str, reason: str | None = None) -> dict[str, Any] | None:
        with self.session_factory() as session:
            thread = _find_thread(session, thread_id)
            if thread is None:
                return None
            thread.contract_status = DROPPED
            thread.item_type = "contract"
            thread.updated_at = _utc_now()
            session.add(
                HistoryEvent(
                    event_id=f"event-{uuid4().hex[:12]}",
                    thread_pk=thread.id,
                    actor="business",
                    event_type="dropped",
                    summary=(reason or "Business marked this contract as dropped.").strip(),
                    status=DROPPED,
                    event_metadata={},
                )
            )
            session.commit()
            session.refresh(thread)
            return self._detail_from_session(session, thread)

    def _detail_from_session(self, session, thread: HistoryThread) -> dict[str, Any]:
        messages = session.scalars(
            select(HistoryMessage).where(HistoryMessage.thread_pk == thread.id).order_by(HistoryMessage.created_at)
        ).all()
        runs = session.scalars(
            select(HistoryRun).where(HistoryRun.thread_pk == thread.id).order_by(HistoryRun.created_at)
        ).all()
        events = session.scalars(
            select(HistoryEvent).where(HistoryEvent.thread_pk == thread.id).order_by(HistoryEvent.created_at)
        ).all()
        payload = _thread_summary(thread)
        payload["messages"] = [_message_payload(message) for message in messages]
        payload["runs"] = [_run_payload(run) for run in runs]
        payload["events"] = [_event_payload(event) for event in events]
        return payload


def _find_thread(session, thread_id: str | None) -> HistoryThread | None:
    if not thread_id:
        return None
    return session.scalar(select(HistoryThread).where(HistoryThread.thread_id == thread_id))


def _thread_summary(thread: HistoryThread) -> dict[str, Any]:
    return {
        "id": thread.thread_id,
        "title": thread.title,
        "mode": thread.mode,
        "item_type": thread.item_type,
        "contract_status": thread.contract_status,
        "contract_id": thread.contract_id,
        "version_id": thread.version_id,
        "version_number": thread.version_number,
        "escalation_id": thread.escalation_id,
        "contract_type": thread.contract_type,
        "counterparty": thread.counterparty,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
    }


def _message_payload(message: HistoryMessage) -> dict[str, Any]:
    return {
        "id": message.message_id,
        "role": message.role,
        "content": message.content,
        "metadata": message.message_metadata,
        "created_at": message.created_at.isoformat(),
    }


def _run_payload(run: HistoryRun) -> dict[str, Any]:
    return {
        "id": run.run_id,
        "mode": run.mode,
        "reply": run.reply,
        "reasoning": run.reasoning,
        "sources_used": run.sources_used,
        "routed_agents": run.routed_agents,
        "findings": run.findings,
        "result": run.result_payload,
        "created_at": run.created_at.isoformat(),
    }


def _event_payload(event: HistoryEvent) -> dict[str, Any]:
    return {
        "id": event.event_id,
        "actor": event.actor,
        "event_type": event.event_type,
        "summary": event.summary,
        "status": event.status,
        "metadata": event.event_metadata,
        "created_at": event.created_at.isoformat(),
    }


def _title_from_message(message: str) -> str:
    compact = " ".join(message.split())
    if not compact:
        return "Ask Donna chat"
    return compact[:72] + ("..." if len(compact) > 72 else "")


def _message_event_summary(mode: str, uploaded_filenames: list[str], is_final_version: bool) -> str:
    label = "contract review" if mode == "contract_review" else "general question"
    parts = [f"Business submitted a {label}."]
    if uploaded_filenames:
        parts.append(f"Uploaded {len(uploaded_filenames)} document(s).")
    if is_final_version:
        parts.append("Marked as final version.")
    return " ".join(parts)


def _ai_event_type(contract_status: str | None) -> str:
    if contract_status == APPROVED:
        return "approved"
    if contract_status == PENDING_LEGAL:
        return "pending_legal"
    if contract_status == NEEDS_BUSINESS_INPUT:
        return "needs_business_input"
    return "ai_reply"


def _ai_event_summary(result_payload: dict[str, Any], contract_status: str | None) -> str:
    if contract_status == APPROVED:
        return "AI approved the final contract version because no findings or escalation triggers remained."
    if contract_status == PENDING_LEGAL:
        return "AI marked the final contract version as pending Legal because unresolved findings or escalation triggers remain."
    if contract_status == NEEDS_BUSINESS_INPUT:
        return "AI blocked Legal submission because the ticket package needs business input before escalation."
    return str(result_payload.get("routing_summary") or result_payload.get("plain_answer") or "AI replied to the thread.")
