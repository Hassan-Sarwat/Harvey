from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class LegalDataHubClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, Any]]:
        """Return live Legal Data Hub evidence or deterministic demo fallback evidence."""
        if not self.settings.lda_client or not self.settings.lda_secret:
            return self._fallback(domain)

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    f"{self.settings.legal_data_hub_base_url}/semantic-search",
                    auth=(self.settings.lda_client, self.settings.lda_secret),
                    json={"query": query, "data_assets": ["Gesetze", "Rechtsprechung"]},
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results", payload if isinstance(payload, list) else [])
                if isinstance(results, list) and results:
                    return results
        except (httpx.HTTPError, ValueError):
            if not self.settings.use_legal_fallback:
                raise

        return self._fallback(domain)

    def _fallback(self, domain: str) -> list[dict[str, Any]]:
        file_name = "datenschutz_evidence.json" if domain == "data_protection" else "litigation_evidence.json"
        fallback_path = Path(__file__).resolve().parents[3] / "data" / "legal_fallback" / file_name
        if not fallback_path.exists():
            return []
        return json.loads(fallback_path.read_text(encoding="utf-8"))
