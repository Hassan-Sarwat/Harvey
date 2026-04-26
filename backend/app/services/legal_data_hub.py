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
                qna_payload = await _qna(client, self._qna_url(), query, headers)
                for document in _extract_qna_documents(qna_payload):
                    normalized = _normalize_qna_document(document, qna_payload or {})
                    hit_id = normalized.get("_id") or normalized.get("citation", "")
                    if hit_id and hit_id in seen_ids:
                        continue
                    if hit_id:
                        seen_ids.add(hit_id)
                    results.append(normalized)

                if not results:
                    for data_asset in self._data_assets():
                        # Prefer semantic search; fall back to keyword search
                        hits = await _semantic_search(client, self._base_url(), query, data_asset, headers)
                        if not hits:
                            hits = await _keyword_search(client, self._keyword_search_url(data_asset), query, headers)
                        for hit in hits:
                            normalized = _normalize_result(hit, data_asset)
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
            "qna_path": self.settings.legal_data_hub_qna_path,
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

    def _base_url(self) -> str:
        return self.settings.legal_data_hub_base_url.rstrip("/")

    def _keyword_search_url(self, data_asset: str) -> str:
        from urllib.parse import quote
        encoded_asset = quote(data_asset, safe="")
        search_base = self.settings.legal_data_hub_search_path.strip() or "/api/search"
        if not search_base.startswith("/"):
            search_base = f"/{search_base}"
        return f"{self._base_url()}{search_base}/{encoded_asset}/_search"

    def _qna_url(self) -> str:
        qna_path = self.settings.legal_data_hub_qna_path.strip() or "/api/qna"
        if not qna_path.startswith("/"):
            qna_path = f"/{qna_path}"
        return f"{self._base_url()}{qna_path}"

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
        # basic
        import base64
        creds = base64.b64encode(
            f"{self.settings.lda_client}:{self.settings.lda_secret}".encode()
        ).decode()
        return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

    async def _get_bearer_token(self) -> str:
        """Fetch and cache an OAuth2 bearer token using the LDA authorization_code grant."""
        if self._bearer_token and time.monotonic() < self._token_expires_at:
            return self._bearer_token

        async with httpx.AsyncClient(timeout=self.settings.legal_data_hub_timeout) as client:
            response = await client.post(
                self.settings.legal_data_hub_token_url,
                data={
                    "grant_type": "authorization_code",
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
# Search helpers
# ------------------------------------------------------------------

async def _semantic_search(
    client: httpx.AsyncClient,
    base_url: str,
    query: str,
    data_asset: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    """POST /api/semantic-search — preferred; returns natural-language ranked results."""
    url = f"{base_url}/api/semantic-search"
    body = {
        "search_query": query,
        "data_asset": data_asset,
        "candidates": 5,
        "filter": [],
        "post_reranking": True,
    }
    try:
        response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        return _extract_hits(payload)
    except httpx.HTTPStatusError:
        return []


async def _qna(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    headers: dict[str, str],
) -> dict[str, Any] | None:
    """POST /api/qna — Otto Schmidt attribution answer with source documents."""
    body = {
        "prompt": query,
        "data_asset": "*",
        "mode": "attribution",
        "filter": [{}],
    }
    try:
        response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except httpx.HTTPStatusError:
        return None


async def _keyword_search(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    """POST /api/search/{data_asset}/_search — Elasticsearch DSL fallback."""
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["content^2", "title^3", "text^2"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        },
        "highlight": {
            "fields": {"content": {"number_of_fragments": 2, "fragment_size": 250}},
            "pre_tags": [""],
            "post_tags": [""],
        },
        "size": 5,
    }
    response = await client.post(url, json=body, headers=headers)
    response.raise_for_status()
    return _extract_hits(response.json())


def _extract_hits(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    hits_wrapper = payload.get("hits", {})
    if isinstance(hits_wrapper, dict):
        hits = hits_wrapper.get("hits", [])
        if hits:
            return hits
    results = payload.get("results", payload.get("documents", []))
    if isinstance(results, list):
        return results
    return []


def _extract_qna_documents(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    documents = payload.get("sourcedocuments") or payload.get("source_documents") or []
    return documents if isinstance(documents, list) else []


def _normalize_qna_document(document: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    content = str(document.get("content") or document.get("text") or "")[:800]
    source = str(metadata.get("source") or metadata.get("title") or metadata.get("name") or "Otto Schmidt QnA source")
    url = metadata.get("oso_url") or metadata.get("url") or metadata.get("link")
    document_type = metadata.get("dokumententyp") or metadata.get("document_type")
    date = metadata.get("datum") or metadata.get("date")
    aktenzeichen = metadata.get("aktenzeichen")
    citation_parts = [source]
    if document_type:
        citation_parts.append(str(document_type))
    if date:
        citation_parts.append(str(date)[:10])
    citation = " - ".join(part for part in citation_parts if part)

    normalized: dict[str, Any] = {
        "_id": metadata.get("id") or metadata.get("document_id") or url or source,
        "source": "Otto Schmidt / Legal Data Hub QnA",
        "citation": citation,
        "quote": content or "Live Legal Data Hub QnA source returned without excerpt text.",
        "retrieval_mode": "live",
        "retrieval_endpoint": "qna",
        "data_asset": "*",
        "qna_response_id": payload.get("response_id"),
        "qna_answer": payload.get("text") or "",
    }
    if url:
        normalized["url"] = url
    if document_type:
        normalized["source_type"] = document_type
    if date:
        normalized["date"] = date
    if aktenzeichen:
        normalized["aktenzeichen"] = aktenzeichen
    normalized.update({f"metadata_{key}": value for key, value in metadata.items() if f"metadata_{key}" not in normalized})
    return normalized


def _normalize_result(hit: dict[str, Any], data_asset: str) -> dict[str, Any]:
    """Normalise any Otto Schmidt hit format to the internal evidence format."""
    # ES hit wrapper: { _id, _score, _source: {...}, highlight: {...} }
    source = hit.get("_source", hit)
    highlight = hit.get("highlight", {})

    # Extract excerpt from highlights or source content
    highlight_texts: list[str] = []
    for fragments in highlight.values():
        if isinstance(fragments, list):
            highlight_texts.extend(str(f) for f in fragments)
    excerpt = " … ".join(highlight_texts[:2]) if highlight_texts else (
        str(source.get("content") or source.get("text") or source.get("excerpt") or "")[:400]
    )

    title = (
        source.get("title")
        or source.get("citation")
        or source.get("reference_number")
        or source.get("aktenzeichen")
        or source.get("name")
        or hit.get("_id")
        or f"{data_asset} result"
    )
    url = source.get("url") or source.get("link")
    confidence = hit.get("_score") or hit.get("score") or source.get("confidence")

    normalized: dict[str, Any] = {
        "_id": hit.get("_id") or hit.get("id"),
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

    # Preserve all source fields for downstream use
    normalized.update({k: v for k, v in source.items() if k not in normalized})
    return normalized


def _origin_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"
