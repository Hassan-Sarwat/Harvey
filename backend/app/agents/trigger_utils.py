from __future__ import annotations

import re

from app.agents.base import ContractTrigger


def sentence_trigger_for_phrase(contract_text: str, phrase: str) -> ContractTrigger | None:
    phrase_start = contract_text.lower().find(phrase.lower())
    if phrase_start == -1:
        return None

    return _sentence_trigger_at(contract_text, phrase_start)


def first_sentence_trigger(contract_text: str) -> ContractTrigger | None:
    first_non_space = next((index for index, char in enumerate(contract_text) if not char.isspace()), None)
    if first_non_space is None:
        return None

    return _sentence_trigger_at(contract_text, first_non_space)


def missing_term_trigger(contract_text: str, label: str) -> ContractTrigger:
    fallback = first_sentence_trigger(contract_text)
    if fallback is None:
        return ContractTrigger(text=label, start=None, end=None)
    return fallback


def _sentence_trigger_at(contract_text: str, index: int) -> ContractTrigger:
    sentence_start = max(contract_text.rfind(".", 0, index), contract_text.rfind("\n", 0, index))
    start = sentence_start + 1 if sentence_start >= 0 else 0

    sentence_end_candidates = [
        position
        for position in (
            contract_text.find(".", index),
            contract_text.find("\n", index),
        )
        if position != -1
    ]
    end = min(sentence_end_candidates) + 1 if sentence_end_candidates else len(contract_text)

    while start < end and contract_text[start].isspace():
        start += 1
    while end > start and contract_text[end - 1].isspace():
        end -= 1

    text = re.sub(r"\s+", " ", contract_text[start:end]).strip()
    return ContractTrigger(text=text, start=start, end=end)
