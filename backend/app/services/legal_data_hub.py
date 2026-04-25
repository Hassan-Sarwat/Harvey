from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


class LegalDataHubClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._bearer_token: str | None = None
        self._token_expires_at: float = 0.0

    async def search_evidence(self, query: str, domain: str = "general") -> list[dict[str, Any]]:
        """Return live Otto Schmidt / Legal Data Hub evidence or explicit fallback evidence."""
        if not self.settings.lda_client or not self.settings.lda_secret:
            return self._fallback(domain)

        try:
            headers = await self._auth_headers()
            results: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            async with httpx.AsyncClient(timeout=self.settings.legal_data_hub_timeout) as client:
                for data_asset in self._data_assets():
                    url = self._search_url(data_asset)
                    body = _build_es_query(query)
                    response = await client.post(url, json=body, headers=headers)
                    response.raise_for_status()
                    payload = response.json()
                    hits = _extract_hits(payload)
                    for hit in hits:
                        normalized = _normalize_es_result(hit, data_asset)
                        hit_id = normalized.get("_id") or normalized.get("citation", "")
                        if hit_id and hit_id in seen_ids:
                            continue
                        if hit_id:
                            seen_ids.add(hit_id)
                        results.append(normalized)
            if results:
                return results
        except (httpx.HTTPError, ValueError) as exc:
            if not self.settings.use_legal_fallback:
                raise
            return self._fallback(domain, reason=f"{type(exc).__name__}: live Legal Data Hub request failed")

        return self._fallback(domain, reason="live Legal Data Hub returned no results")

    async def status(self) -> dict[str, Any]:
        configured = bool(self.settings.lda_client and self.settings.lda_secret)
        payload: dict[str, Any] = {
            "configured": configured,
            "base_url": self.settings.legal_data_hub_base_url,
            "search_path": self.settings.legal_data_hub_search_path,
            "auth_mode": self.settings.legal_data_hub_auth_mode,
            "data_assets": self._data_assets(),
            "reachable": False,
            "live_ready": False,
            "fallback_enabled": self.settings.use_legal_fallback,
            "error": None,
        }
        if not configured:
            payload["error"] = "LDA_CLIENT and LDA_SECRET are not both configured."
            return payload

        probe_url = _origin_url(self.settings.legal_data_hub_base_url)
        try:
            async with httpx.AsyncClient(timeout=min(self.settings.legal_data_hub_timeout, 5.0)) as client:
                response = await client.head(probe_url)
                payload["reachable"] = response.status_code < 500
                payload["live_ready"] = payload["reachable"]
                payload["status_code"] = response.status_code
        except httpx.HTTPError as exc:
            payload["error"] = f"{type(exc).__name__}: {exc}"
        return payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search_url(self, data_asset: str) -> str:
        base = self.settings.legal_data_hub_base_url.rstrip("/")
        search_base = self.settings.legal_data_hub_search_path.strip() or "/api/search"
        if not search_base.startswith("/"):
            search_base = f"/{search_base}"
        from urllib.parse import quote
        encoded_asset = quote(data_asset, safe="")
        return f"{base}{search_base}/{encoded_asset}/_search"

    def _data_assets(self) -> list[str]:
        return [
            asset.strip()
            for asset in self.settings.legal_data_hub_data_assets.split(",")
            if asset.strip()
        ] or ["Gesetze", "Rechtsprechung"]

    async def _auth_headers(self) -> dict[str, str]:
        mode = self.settings.legal_data_hub_auth_mode.lower()
        if mode == "oauth2":
            token = await self._get_bearer_token()
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if mode == "bearer":
            return {
                "Authorization": f"Bearer {self.settings.lda_secret}",
                "Content-Type": "application/json",
            }
        # basic — encode credentials in the header directly
        import base64
        creds = base64.b64encode(
            f"{self.settings.lda_client}:{self.settings.lda_secret}".encode()
        ).decode()
        return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    async def _get_bearer_token(self) -> str:
        """Fetch and cache an OAuth2 client_credentials bearer token."""
        if self._bearer_token and time.monotonic() < self._token_expires_at:
            return self._bearer_token

        async with httpx.AsyncClient(timeout=self.settings.legal_data_hub_timeout) as client:
            response = await client.post(
                self.settings.legal_data_hub_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.lda_client or "",
                    "client_secret": self.settings.lda_secret or "",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        token = data.get("access_token")
        if not token:
            raise ValueError(f"OAuth2 token response missing access_token: {data}")

        expires_in = float(data.get("expires_in", 3600))
        # Refresh 60 s before expiry
        self._token_expires_at = time.monotonic() + expires_in - 60
        self._bearer_token = token
        return token

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


# ------------------------------------------------------------------
# Elasticsearch response helpers
# ------------------------------------------------------------------

def _build_es_query(query: str) -> dict[str, Any]:
    return {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["content^2", "title^3", "text^2", "excerpt"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        },
        "highlight": {
            "fields": {
                "content": {"number_of_fragments": 2, "fragment_size": 250},
                "text": {"number_of_fragments": 2, "fragment_size": 250},
            },
            "pre_tags": [""],
            "post_tags": [""],
        },
        "size": 5,
        "_source": True,
    }


def _extract_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract hits from an Elasticsearch response or a plain list."""
    if isinstance(payload, list):
        return payload
    hits_wrapper = payload.get("hits", {})
    if isinstance(hits_wrapper, dict):
        return hits_wrapper.get("hits", [])
    # Some APIs return results at top level
    return payload.get("results", [])


def _normalize_es_result(hit: dict[str, Any], data_asset: str) -> dict[str, Any]:
    """Normalise an Elasticsearch hit to the internal evidence format."""
    source = hit.get("_source", hit)
    highlight = hit.get("highlight", {})

    # Extract a readable excerpt from highlights or source content
    highlight_texts = []
    for field_fragments in highlight.values():
        if isinstance(field_fragments, list):
            highlight_texts.extend(field_fragments)
    excerpt = " … ".join(highlight_texts[:2]) if highlight_texts else (
        str(source.get("content") or source.get("text") or source.get("excerpt") or "")[:400]
    )

    title = (
        source.get("title")
        or source.get("citation")
        or source.get("reference_number")
        or source.get("name")
        or hit.get("_id")
        or f"{data_asset} result"
    )
    url = source.get("url") or source.get("link")
    confidence = hit.get("_score") or source.get("confidence") or source.get("score")

    normalized: dict[str, Any] = {
        "_id": hit.get("_id"),
        "source": f"Otto Schmidt / Legal Data Hub — {data_asset}",
        "citation": str(title),
        "quote": excerpt or "Live Legal Data Hub result returned without excerpt text.",
        "retrieval_mode": "live",
        "data_asset": data_asset,
    }
    if url:
        normalized["url"] = url
    if confidence is not None:
        normalized["confidence"] = float(confidence)

    # Keep all source fields for downstream use
    normalized.update({k: v for k, v in source.items() if k not in normalized})
    return normalized


def _origin_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"
