from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.model_context import is_model_access_error, openai_model_candidates

logger = logging.getLogger(__name__)

CONTRACT_TYPES = {"data_protection", "litigation", "general"}


class ContractClassification(BaseModel):
    contract_type: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str
    source: str


async def classify_contract_type(contract_text: str, provided_type: str | None = None) -> ContractClassification:
    normalized = (provided_type or "").strip()
    if normalized:
        return ContractClassification(
            contract_type=normalized,
            confidence=1.0,
            rationale="Contract type was provided by the user or calling workflow.",
            source="user_provided",
        )

    llm_result = await _llm_contract_classification(contract_text)
    if llm_result is not None:
        return llm_result

    fallback_type = infer_contract_type_fallback(contract_text)
    return ContractClassification(
        contract_type=fallback_type,
        confidence=0.45 if fallback_type != "general" else 0.25,
        rationale="OpenAI classification was unavailable, so Harvey used the offline keyword fallback.",
        source="keyword_fallback",
    )


def infer_contract_type_fallback(contract_text: str) -> str:
    text = contract_text.lower()
    data_protection_terms = (
        "gdpr",
        "personal data",
        "data subject",
        "processor",
        "controller",
        "subprocessor",
        "data processing",
        "breach notification",
        "technical and organisational",
        "technical and organizational",
        "third-country",
        "third country",
        "tom",
    )
    litigation_terms = (
        "litigation",
        "settlement",
        "liability",
        "indemnity",
        "court",
        "arbitration",
        "legal hold",
        "governing law",
        "claims",
        "privilege",
    )
    data_score = sum(1 for term in data_protection_terms if term in text)
    litigation_score = sum(1 for term in litigation_terms if term in text)
    if data_score >= litigation_score and data_score > 0:
        return "data_protection"
    if litigation_score > 0:
        return "litigation"
    return "general"


async def _llm_contract_classification(contract_text: str) -> ContractClassification | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package is not installed; contract classification is using fallback")
        return None

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        content = ""
        last_error: Exception | None = None
        for model in openai_model_candidates(settings):
            try:
                content = await _create_classification_response(
                    client=client,
                    model=model,
                    reasoning_effort=settings.openai_reasoning_effort,
                    contract_text=contract_text,
                )
                break
            except Exception as exc:
                last_error = exc
                if not is_model_access_error(exc):
                    raise
                logger.warning("OpenAI model %s unavailable for contract classification; trying fallback model", model)
        if not content and last_error:
            raise last_error
        parsed = _parse_classification_json(content)
        if parsed is None:
            return None

        contract_type = str(parsed.get("contract_type") or "").strip().lower()
        if contract_type not in CONTRACT_TYPES:
            return None
        confidence = _coerce_confidence(parsed.get("confidence"))
        rationale = str(parsed.get("rationale") or "Classified by OpenAI from the submitted matter text.").strip()
        return ContractClassification(
            contract_type=contract_type,
            confidence=confidence,
            rationale=rationale[:500],
            source="openai_llm",
        )
    except Exception as exc:
        logger.warning("OpenAI contract classification failed: %s", exc)
        return None


async def _create_classification_response(
    *,
    client: Any,
    model: str,
    reasoning_effort: str | None,
    contract_text: str,
) -> str:
    response = await client.responses.create(
        model=model,
        reasoning={"effort": reasoning_effort or "low"},
        input=[
            {
                "role": "system",
                "content": (
                    "You classify contract matters for BMW legal intake. Return only the requested structured output. "
                    "Use data_protection for DPAs, privacy addenda, GDPR processor/controller clauses, personal data, "
                    "TOMs, subprocessors, data subject rights, breach notice, retention, audits, or international transfers. "
                    "Use litigation for disputes, claims, settlement, indemnity, liability, courts, arbitration, legal hold, "
                    "privilege, or evidence. Use general only when neither playbook domain is materially supported."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Classify this uploaded contract or matter text:\n\n"
                    f"{_classification_excerpt(contract_text)}"
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "contract_classification",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "contract_type": {
                            "type": "string",
                            "enum": ["data_protection", "litigation", "general"],
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "rationale": {
                            "type": "string",
                        },
                    },
                    "required": ["contract_type", "confidence", "rationale"],
                    "additionalProperties": False,
                },
            }
        },
        max_output_tokens=350,
    )
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text
    # Compatibility for older SDK response objects or test doubles.
    choices = getattr(response, "choices", None)
    if choices:
        return getattr(getattr(choices[0], "message", None), "content", "") or ""
    return ""


def _classification_excerpt(contract_text: str) -> str:
    compact = re.sub(r"\s+", " ", contract_text).strip()
    if len(compact) <= 6000:
        return compact
    return f"{compact[:3000]}\n\n[...middle omitted...]\n\n{compact[-3000:]}"


def _parse_classification_json(content: str) -> dict[str, Any] | None:
    stripped = content.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.6
    return max(0.0, min(1.0, value))
