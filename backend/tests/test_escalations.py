from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.agents.base import AgentResult, ContractTrigger, Finding, RulingReference, Severity, Suggestion
from app.api import contracts, dashboard, escalations
from app.services.contract_repository import ContractRepository
from app.services.escalation_repository import EscalationAlreadyDecidedError, EscalationRepository
from app.services.legal_data_hub import LegalDataHubClient
from app.services.review_storage import DocumentStore


def test_escalation_repository_tracks_denied_as_positive_escalation(tmp_path):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    escalation = repository.create_from_review(contract_id="contract-1", review_result=_escalating_result())

    assert escalation is not None
    assert escalation["ticket_id"].startswith("TCK-")
    assert escalation["status"] == "pending_legal"
    assert escalation["highest_severity"] == "blocker"
    assert escalation["source_agents"] == ["playbook_checker"]

    decided = repository.decide_escalation(
        escalation_id=escalation["id"],
        decision="denied",
        notes="Supplier must revise the draft.",
        fix_suggestions=["Name the BMW contracting entity."],
        decided_by="legal-team",
    )

    assert decided is not None
    assert decided["status"] == "denied"
    assert decided["next_owner"] == "business"

    metrics = repository.escalation_metrics()
    assert metrics["positive_escalations"] == 1
    assert metrics["false_escalations"] == 0
    assert metrics["top_positive_escalation_agent"]["agent_name"] == "playbook_checker"
    assert {item["agent_name"] for item in metrics["per_agent"]} == {"playbook_checker"}


def test_escalation_repository_tracks_accepted_as_false_escalation(tmp_path):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    escalation = repository.create_from_review(contract_id="contract-1", review_result=_escalating_result())

    repository.decide_escalation(
        escalation_id=escalation["id"],
        decision="accepted",
        notes="Legal accepts the risk.",
        fix_suggestions=[],
        decided_by="legal-team",
    )

    metrics = repository.escalation_metrics()
    assert metrics["accepted_escalations"] == 1
    assert metrics["false_escalations"] == 1
    assert metrics["positive_escalations"] == 0
    assert metrics["top_false_escalation_agent"]["agent_name"] == "playbook_checker"


def test_escalation_repository_rejects_duplicate_decision(tmp_path):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    escalation = repository.create_from_review(contract_id="contract-1", review_result=_escalating_result())

    repository.decide_escalation(
        escalation_id=escalation["id"],
        decision="accepted",
        notes=None,
        fix_suggestions=[],
        decided_by=None,
    )

    with pytest.raises(EscalationAlreadyDecidedError):
        repository.decide_escalation(
            escalation_id=escalation["id"],
            decision="denied",
            notes=None,
            fix_suggestions=["Revise the contract."],
            decided_by=None,
        )


async def test_escalation_api_requires_fix_suggestions_for_denial():
    with pytest.raises(ValidationError):
        escalations.LegalDecisionRequest(decision="denied", fix_suggestions=[])


async def test_escalation_api_returns_conflict_for_duplicate_decision(tmp_path, monkeypatch):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    monkeypatch.setattr(escalations, "EscalationRepository", lambda: repository)
    escalation = repository.create_from_review(contract_id="contract-1", review_result=_escalating_result())

    request = escalations.LegalDecisionRequest(decision="accepted")
    await escalations.decide_escalation(escalation["id"], request)

    with pytest.raises(HTTPException) as exc:
        await escalations.decide_escalation(escalation["id"], request)
    assert exc.value.status_code == 409


def test_escalation_detail_includes_contract_text_and_trigger_annotations(tmp_path):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    contract_text = "Supplier accepts unlimited liability."
    escalation = repository.create_from_review(
        contract_id="contract-1",
        review_result=_escalating_result(),
        contract_text=contract_text,
    )

    detail = repository.get_escalation(escalation["id"])

    assert detail["contract_text"] == contract_text
    liability = next(item for item in detail["trigger_annotations"] if item["finding_id"] == "unlimited-liability")
    assert liability["text"] == contract_text
    assert liability["severity"] == "blocker"
    assert liability["ruling"]["citation"] == "LT-003 - Unlimited liability escalation"
    assert liability["suggestions"][0]["finding_id"] == "unlimited-liability"


def test_escalation_list_and_detail_share_ticket_identity(tmp_path):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    escalation = repository.create_from_review(
        contract_id="contract-1",
        review_result=_escalating_result(),
        contract_text="Supplier accepts unlimited liability.",
    )

    listed = repository.list_escalations(status="pending_legal")[0]
    detail = repository.get_escalation(escalation["id"])

    assert listed["ticket_id"] == escalation["ticket_id"]
    assert detail["ticket_id"] == escalation["ticket_id"]
    assert listed["highest_severity"] == "blocker"


async def test_escalation_chat_answers_from_trigger_context(tmp_path, monkeypatch):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    monkeypatch.setattr(escalations, "EscalationRepository", lambda: repository)
    escalation = repository.create_from_review(
        contract_id="contract-1",
        review_result=_escalating_result(),
        contract_text="Supplier accepts unlimited liability.",
    )

    payload = await escalations.ask_escalation_context(
        escalation["id"],
        escalations.EscalationChatRequest(question="Which playbook ruling triggered liability?"),
    )

    assert "LT-003 - Unlimited liability escalation" in payload["answer"]
    assert payload["cited_context"][0]["type"] == "trigger"


async def test_dashboard_uses_live_escalation_metrics(tmp_path, monkeypatch):
    repository = EscalationRepository(f"sqlite:///{tmp_path / 'harvey.db'}")
    monkeypatch.setattr(dashboard, "EscalationRepository", lambda: repository)
    escalation = repository.create_from_review(contract_id="contract-1", review_result=_escalating_result())
    repository.decide_escalation(
        escalation_id=escalation["id"],
        decision="accepted",
        notes=None,
        fix_suggestions=[],
        decided_by=None,
    )

    payload = await dashboard.metrics()

    assert payload["escalation_metrics"]["false_escalations"] == 1
    assert payload["escalation_metrics"]["top_false_escalation_agent"]["agent_name"] == "playbook_checker"


async def test_review_endpoint_waits_for_business_escalation_decision(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'harvey.db'}"
    monkeypatch.setattr(contracts, "DocumentStore", lambda: DocumentStore(str(tmp_path)))
    monkeypatch.setattr(contracts, "ContractRepository", lambda: ContractRepository(database_url))
    monkeypatch.setattr(contracts, "EscalationRepository", lambda: EscalationRepository(database_url))
    monkeypatch.setattr(LegalDataHubClient, "search_evidence", _fake_search_evidence)

    payload = await contracts.review_contract_by_identity(
        contracts.ContractReviewRequest(
            contract_text="Supplier accepts unlimited liability.",
            contract_type="litigation",
            vendor="ACME GmbH",
            effective_date=date(2026, 1, 1),
        )
    )

    assert "escalation_id" not in payload["metadata"]
    assert payload["metadata"]["business_status"] == "needs_revision"
    assert payload["metadata"]["escalation_available"] is True
    assert EscalationRepository(database_url).list_escalations() == []

    escalation = await contracts.escalate_contract_version(
        payload["contract_id"],
        payload["version_number"],
        contracts.BusinessEscalationRequest(
            reason="Business cannot accept the AI suggested liability cap.",
            requested_by="business-user",
        ),
    )

    assert escalation["status"] == "pending_legal"
    assert escalation["version_id"] == payload["version_id"]
    assert escalation["version_number"] == payload["version_number"]
    assert escalation["source_agents"] == ["playbook_checker"]
    assert escalation["review_result"]["metadata"]["business_escalation_requested_by"] == "business-user"


def _escalating_result() -> AgentResult:
    liability_trigger = ContractTrigger(text="Supplier accepts unlimited liability.", start=0, end=37)
    liability_ruling = RulingReference(
        source="BMW mock playbook: litigation",
        citation="LT-003 - Unlimited liability escalation",
        quote="Unlimited liability must be escalated to legal.",
    )
    playbook_finding = Finding(
        id="unlimited-liability",
        title="Unlimited liability exceeds BMW default",
        description="Unlimited liability exceeds the BMW playbook default.",
        severity=Severity.BLOCKER,
        clause_reference=liability_trigger.text,
        trigger=liability_trigger,
        ruling=liability_ruling,
        requires_escalation=True,
    )
    return AgentResult(
        agent_name="risk_aggregator",
        summary="Aggregated agent findings and determined escalation status.",
        findings=[playbook_finding],
        suggestions=[
            Suggestion(
                finding_id="unlimited-liability",
                proposed_text="Replace unlimited liability with the BMW-approved liability position.",
                rationale="Required by BMW Litigation Rule LT-003.",
            )
        ],
        confidence=0.6,
        requires_escalation=True,
        metadata={
            "agent_results": [
                {
                    "agent_name": "playbook_checker",
                    "findings": [playbook_finding.model_dump(mode="json")],
                    "suggestions": [],
                    "confidence": 0.7,
                    "requires_escalation": True,
                    "metadata": {},
                },
            ]
        },
    )


async def _fake_search_evidence(self, query: str, domain: str = "general") -> list[dict[str, str]]:
    return [{"source": "test fallback", "citation": "test", "quote": "test evidence"}]
