from __future__ import annotations

import re

from app.agents.base import Agent, AgentResult, ContractTrigger, Evidence, Finding, ReviewContext, Severity
from app.core.config import get_settings
from app.services.contract_classifier import classify_contract_type


class ContractTriageAgent(Agent):
    name = "contract_triage"

    async def run(self, context: ReviewContext) -> AgentResult:
        findings: list[Finding] = []
        classification = await classify_contract_type(context.contract_text, provided_type=context.contract_type)
        contract_type = classification.contract_type
        value = _extract_contract_value(context.contract_text)
        threshold = get_settings().contract_value_escalation_threshold_eur

        if contract_type not in {"data_protection", "litigation"}:
            findings.append(
                Finding(
                    id="matter-not-covered-by-playbook",
                    title="Matter is not covered by active playbooks",
                    description="The contract does not fit the active DPA or litigation playbook domains with enough confidence.",
                    severity=Severity.HIGH,
                    ruling=None,
                    evidence=[
                        Evidence(
                            source="Contract triage",
                            citation="Playbook coverage check",
                            quote=classification.rationale,
                        )
                    ],
                    requires_escalation=True,
                )
            )

        if value is not None and value.amount_eur > threshold:
            trigger = _value_trigger(context.contract_text, value.raw_text)
            findings.append(
                Finding(
                    id="contract-value-threshold",
                    title="Contract value exceeds escalation threshold",
                    description=(
                        f"The detected contract value is approximately EUR {value.amount_eur:,.0f}, "
                        f"above the EUR {threshold:,.0f} legal escalation threshold."
                    ),
                    severity=Severity.HIGH,
                    clause_reference=trigger.text,
                    trigger=trigger,
                    evidence=[
                        Evidence(
                            source="Contract triage",
                            citation="Contract value escalation rule",
                            quote=f"Detected value: {value.raw_text}",
                        )
                    ],
                    requires_escalation=True,
                )
            )

        high_risk = _high_risk_trigger(context.contract_text)
        if high_risk is not None:
            findings.append(
                Finding(
                    id="high-risk-contract-matter",
                    title="High-risk contract matter needs Legal review",
                    description="The contract appears to involve a sensitive risk category that should not be self-approved.",
                    severity=Severity.HIGH,
                    clause_reference=high_risk.text,
                    trigger=high_risk,
                    evidence=[
                        Evidence(
                            source="Contract triage",
                            citation="High-risk matter escalation rule",
                            quote=high_risk.text,
                        )
                    ],
                    requires_escalation=True,
                )
            )

        return AgentResult(
            agent_name=self.name,
            summary="Checked playbook coverage, contract value, and high-risk matter triggers.",
            findings=findings,
            confidence=max(0.55, classification.confidence),
            requires_escalation=any(finding.requires_escalation for finding in findings),
            metadata={
                "contract_type": contract_type,
                "classification_source": classification.source,
                "classification_confidence": classification.confidence,
                "classification_rationale": classification.rationale,
                "contract_value_eur": value.amount_eur if value else None,
                "contract_value_raw": value.raw_text if value else None,
                "contract_value_threshold_eur": threshold,
                "playbook_covered": contract_type in {"data_protection", "litigation"},
            },
        )


class _ContractValue:
    def __init__(self, amount_eur: float, raw_text: str) -> None:
        self.amount_eur = amount_eur
        self.raw_text = raw_text

    def __gt__(self, threshold: float) -> bool:
        return self.amount_eur > threshold


def _extract_contract_value(text: str) -> _ContractValue | None:
    patterns = [
        r"(?:eur|€)\s*([0-9][0-9.,]*(?:\s*(?:k|m|million|thousand))?)",
        r"([0-9][0-9.,]*(?:\s*(?:k|m|million|thousand))?)\s*(?:eur|€)",
    ]
    candidates: list[_ContractValue] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw_number = match.group(1)
            amount = _parse_amount(raw_number)
            if amount is not None:
                candidates.append(_ContractValue(amount, match.group(0)))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.amount_eur)


def _parse_amount(raw: str) -> float | None:
    normalized = raw.strip().lower()
    multiplier = 1.0
    if normalized.endswith("million"):
        multiplier = 1_000_000.0
        normalized = normalized[: -len("million")]
    elif normalized.endswith("thousand"):
        multiplier = 1_000.0
        normalized = normalized[: -len("thousand")]
    elif normalized.endswith("m"):
        multiplier = 1_000_000.0
        normalized = normalized[:-1]
    elif normalized.endswith("k"):
        multiplier = 1_000.0
        normalized = normalized[:-1]

    cleaned = normalized.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 3:
            cleaned = "".join(parts)
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3:
            cleaned = "".join(parts)
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _value_trigger(text: str, raw_value: str) -> ContractTrigger:
    start = text.lower().find(raw_value.lower())
    if start < 0:
        return ContractTrigger(text=raw_value)
    return ContractTrigger(text=raw_value, start=start, end=start + len(raw_value))


def _high_risk_trigger(text: str) -> ContractTrigger | None:
    high_risk_phrases = (
        "special category data",
        "biometric data",
        "health data",
        "criminal convictions",
        "precise location",
        "driver behavior",
        "works council",
        "automated decision-making",
        "regulatory investigation",
        "dawn raid",
        "class action",
        "sanctions",
    )
    lower_text = text.lower()
    for phrase in high_risk_phrases:
        start = lower_text.find(phrase)
        if start >= 0:
            return ContractTrigger(text=text[start : start + len(phrase)], start=start, end=start + len(phrase))
    return None
