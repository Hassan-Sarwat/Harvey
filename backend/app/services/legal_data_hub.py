from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class LegalDataHubClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, Any]]:
        """Return live Otto Schmidt / Legal Data Hub evidence or explicit fallback evidence."""
        if not self.settings.lda_client or not self.settings.lda_secret:
            return self._fallback(domain)

        try:
            async with httpx.AsyncClient(timeout=self.settings.legal_data_hub_timeout) as client:
                request_kwargs: dict[str, Any] = {
                    "json": {"query": query, "data_assets": self._data_assets()},
                }
                auth = self._auth()
                headers = self._headers()
                if auth is not None:
                    request_kwargs["auth"] = auth
                if headers:
                    request_kwargs["headers"] = headers
                response = await client.post(
                    self._search_url(),
                    **request_kwargs,
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results", payload if isinstance(payload, list) else [])
                if isinstance(results, list) and results:
                    return [_normalize_live_result(item) for item in results if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError) as exc:
            if not self.settings.use_legal_fallback:
                raise
            return self._fallback(domain, reason=f"{type(exc).__name__}: live Legal Data Hub request failed")

        return self._fallback(domain, reason="live Legal Data Hub returned no results")

    def _search_url(self) -> str:
        base = self.settings.legal_data_hub_base_url.rstrip("/")
        path = self.settings.legal_data_hub_search_path.strip() or "/semantic-search"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _auth(self) -> tuple[str, str] | None:
        if self.settings.legal_data_hub_auth_mode.lower() != "basic":
            return None
        return (self.settings.lda_client or "", self.settings.lda_secret or "")

    def _headers(self) -> dict[str, str]:
        if self.settings.legal_data_hub_auth_mode.lower() != "bearer":
            return {}
        return {"Authorization": f"Bearer {self.settings.lda_secret}"}

    def _data_assets(self) -> list[str]:
        return [
            asset.strip()
            for asset in self.settings.legal_data_hub_data_assets.split(",")
            if asset.strip()
        ] or ["Gesetze", "Rechtsprechung"]

    def _fallback(self, domain: str, reason: str = "Legal Data Hub credentials are not configured") -> list[dict[str, Any]]:
        file_name = "datenschutz_evidence.csv" if domain == "data_protection" else "litigation_evidence.csv"
        fallback_path = Path(__file__).resolve().parents[3] / "data" / "legal_fallback" / file_name
        if not fallback_path.exists():
            return []
        with fallback_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            row["retrieval_mode"] = "fallback"
            row["fallback_reason"] = reason
        return rows


def _normalize_live_result(item: dict[str, Any]) -> dict[str, Any]:
    title = item.get("citation") or item.get("title") or item.get("name") or item.get("document_title")
    quote = item.get("quote") or item.get("excerpt") or item.get("text") or item.get("snippet") or item.get("content")
    source = item.get("source") or item.get("publisher") or item.get("database") or "Otto Schmidt / Legal Data Hub"
    url = item.get("url") or item.get("link")
    confidence = item.get("confidence") or item.get("score")
    normalized = dict(item)
    normalized.update(
        {
            "source": str(source),
            "citation": str(title or "Otto Schmidt / Legal Data Hub result"),
            "quote": str(quote or "Live Legal Data Hub result returned without excerpt text."),
            "retrieval_mode": "live",
        }
    )
    if url is not None:
        normalized["url"] = url
    if confidence is not None:
        normalized["confidence"] = confidence
    return normalized
