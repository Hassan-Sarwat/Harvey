from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any


SOURCE_BASED_DPA_FILE = "bmw_group_dpa_negotiation_playbook.csv"
SOURCE_BASED_DPA_MARKDOWN_FILE = "dpa_negotiation_playbook.md"
DATA_PROTECTION_FALLBACK_FILE = "bmw_data_protection.csv"
LITIGATION_FILE = "bmw_litigation.csv"


def playbook_source_label(domain: str) -> str:
    if domain == "litigation":
        return "BMW litigation playbook"
    return "BMW Group DPA negotiation playbook"


def playbook_file_label(domain: str) -> str:
    if domain == "litigation":
        return LITIGATION_FILE
    return SOURCE_BASED_DPA_MARKDOWN_FILE


def playbook_data_file_label(domain: str) -> str:
    if domain == "litigation":
        return LITIGATION_FILE
    return SOURCE_BASED_DPA_FILE


def load_playbook_rows(domain: str) -> list[dict[str, str]]:
    if domain == "litigation":
        return _load_csv(LITIGATION_FILE)

    source_based_rows = _load_csv(SOURCE_BASED_DPA_FILE)
    if source_based_rows:
        return source_based_rows
    return _load_csv(DATA_PROTECTION_FALLBACK_FILE)


def get_playbook_rule(domain: str, rule_id: str) -> dict[str, Any]:
    for rule in load_playbook_rows(domain):
        if rule.get("id") == rule_id:
            return rule
    if domain == "data_protection":
        for rule in _load_csv(DATA_PROTECTION_FALLBACK_FILE):
            if rule.get("id") == rule_id:
                return rule
    return {"id": rule_id, "title": rule_id, "default": "Playbook rule unavailable."}


def load_playbook_markdown(domain: str) -> str:
    if domain != "data_protection":
        return ""
    path = Path(__file__).resolve().parents[3] / "data" / "playbook" / SOURCE_BASED_DPA_MARKDOWN_FILE
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def _load_csv(file_name: str) -> list[dict[str, str]]:
    path = Path(__file__).resolve().parents[3] / "data" / "playbook" / file_name
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
