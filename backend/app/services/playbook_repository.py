from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


DPA_MARKDOWN_FILE = "dpa_negotiation_playbook.md"
LITIGATION_FILE = "bmw_litigation.csv"


def playbook_source_label(domain: str) -> str:
    if domain == "litigation":
        return "BMW litigation playbook"
    return "BMW Group DPA negotiation playbook"


def playbook_file_label(domain: str) -> str:
    if domain == "litigation":
        return LITIGATION_FILE
    return DPA_MARKDOWN_FILE


def playbook_data_file_label(domain: str) -> str:
    if domain == "litigation":
        return LITIGATION_FILE
    return DPA_MARKDOWN_FILE


def load_playbook_rows(domain: str) -> list[dict[str, str]]:
    if domain == "litigation":
        return _load_csv(LITIGATION_FILE)
    return _load_dpa_markdown_rows()


def get_playbook_rule(domain: str, rule_id: str) -> dict[str, Any]:
    for rule in load_playbook_rows(domain):
        if rule.get("id") == rule_id:
            return rule
    return {"id": rule_id, "title": rule_id, "default": "Playbook rule unavailable."}


def load_playbook_markdown(domain: str) -> str:
    if domain != "data_protection":
        return ""
    path = _playbook_dir() / DPA_MARKDOWN_FILE
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def _load_csv(file_name: str) -> list[dict[str, str]]:
    path = _playbook_dir() / file_name
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def _load_dpa_markdown_rows() -> list[dict[str, str]]:
    markdown = load_playbook_markdown("data_protection")
    if not markdown:
        return []

    sections = re.split(r"\n##\s+", markdown)
    rows: list[dict[str, str]] = []
    for section in sections:
        heading_match = re.match(r"(?P<number>\d+)\.\s+(?P<title>[^\n]+)", section.strip())
        if not heading_match:
            continue
        number = int(heading_match.group("number"))
        title = heading_match.group("title").strip()
        standard = _extract_tier(section, "Standard")
        fallback = _extract_tier(section, "Fall-back")
        red_line = _extract_tier(section, "Red line")
        severity = _severity_for_dpa_title(title)
        rows.append(
            {
                "id": f"DPA-{number:03d}",
                "title": title,
                "severity": severity,
                "default": standard,
                "why_it_matters": _why_it_matters(title),
                "preferred_position": standard,
                "fallback_1": fallback,
                "fallback_2": "",
                "red_line": red_line,
                "escalation_trigger": red_line,
                "legal_basis": _legal_basis(title),
                "sample_clause": "",
                "approved_fix": standard,
                "owner": "BMW Group Privacy Legal",
                "last_reviewed": "2026-04-26",
                "source_playbook_clause": f"Clause {number}: {title}",
                "source_playbook_file": DPA_MARKDOWN_FILE,
            }
        )
    return rows


def _extract_tier(section: str, tier: str) -> str:
    bullet = re.search(rf"- \*\*{re.escape(tier)}\*\*\s*[—-]\s*(?P<value>.+?)(?=\n- \*\*|\n##|\Z)", section, re.DOTALL)
    if bullet:
        return _compact(bullet.group("value"))
    table = re.search(rf"\|\s*{re.escape(tier)}\s*\|\s*(?P<value>.*?)\s*\|", section, re.IGNORECASE)
    return _compact(table.group("value")) if table else ""


def _severity_for_dpa_title(title: str) -> str:
    normalized = title.lower()
    if "international transfers" in normalized or "liability" in normalized:
        return "blocker"
    if any(term in normalized for term in ("breach", "sub-processor", "audit", "deletion", "encryption")):
        return "high"
    return "medium"


def _why_it_matters(title: str) -> str:
    normalized = title.lower()
    if "breach" in normalized:
        return "BMW needs timely facts to assess GDPR notification duties and coordinate mitigation."
    if "sub-processor" in normalized:
        return "BMW must know and control who can access personal data in the processor supply chain."
    if "audit" in normalized:
        return "BMW needs documentary evidence and audit rights to verify Article 28 compliance."
    if "deletion" in normalized:
        return "Retention beyond the service term increases GDPR, confidentiality, and reuse risk."
    if "liability" in normalized:
        return "Security incident exposure can exceed ordinary commercial fee caps."
    if "international transfers" in normalized:
        return "Third-country processing needs locations, transfer mechanisms, and transfer impact assessment."
    if "encryption" in normalized:
        return "Security safeguards must be concrete enough to verify and enforce."
    return "The clause affects BMW's DPA risk position."


def _legal_basis(title: str) -> str:
    normalized = title.lower()
    if "breach" in normalized:
        return "GDPR Art. 28(3)(f), Art. 33, Art. 34."
    if "sub-processor" in normalized:
        return "GDPR Art. 28(2), Art. 28(4)."
    if "audit" in normalized:
        return "GDPR Art. 28(3)(h)."
    if "deletion" in normalized:
        return "GDPR Art. 28(3)(g)."
    if "international transfers" in normalized:
        return "GDPR Chapter V; SCCs; transfer impact assessment practice."
    if "encryption" in normalized:
        return "GDPR Art. 32."
    return "GDPR Art. 28."


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _playbook_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "playbook"
