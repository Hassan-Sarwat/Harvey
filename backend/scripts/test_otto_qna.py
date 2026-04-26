from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx

from app.core.config import get_settings


QUESTION = (
    "Darf ein BMW-Team personenbezogene Fahrzeugdaten an einen externen SaaS-Anbieter senden, "
    "wenn der Anbieter außerhalb der EU hostet?"
)


def _timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(timeout=seconds, connect=min(seconds, 10.0))


def _url(base_url: str, path: str) -> str:
    path = path.strip() or "/api/qna"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base_url.rstrip('/')}{path}"


def _masked(value: str | None) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


async def _token(settings: Any, client: httpx.AsyncClient, grant_type: str) -> str:
    print(f"Requesting token from {settings.legal_data_hub_token_url} with grant_type={grant_type}", flush=True)
    response = await client.post(
        settings.legal_data_hub_token_url,
        data={
            "grant_type": grant_type,
            "client_id": settings.lda_client or "",
            "client_secret": settings.lda_secret or "",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    print(f"Token HTTP status: {response.status_code}", flush=True)
    if response.status_code >= 400:
        print(response.text[:1000], flush=True)
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError(f"Token response did not include access_token. Keys: {sorted(payload.keys())}")
    return str(access_token)


async def _qna(settings: Any, client: httpx.AsyncClient, bearer_token: str, question: str) -> dict[str, Any]:
    qna_url = _url(settings.legal_data_hub_base_url, settings.legal_data_hub_qna_path)
    payload = {
        "data_asset": "*",
        "filter": [{}],
        "mode": "attribution",
        "prompt": question,
    }
    print(f"Calling QnA endpoint: {qna_url}", flush=True)
    started = time.monotonic()
    response = await client.post(
        qna_url,
        json=payload,
        headers={"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"},
    )
    elapsed = time.monotonic() - started
    print(f"QnA HTTP status: {response.status_code} in {elapsed:.2f}s", flush=True)
    if response.status_code >= 400:
        print(response.text[:2000], flush=True)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object, got {type(data).__name__}")
    return data


def _print_qna_payload(payload: dict[str, Any]) -> None:
    source_documents = payload.get("sourcedocuments")
    if not isinstance(source_documents, list):
        source_documents = []

    text = str(payload.get("text") or "")
    print("Response keys:", sorted(payload.keys()), flush=True)
    print("response_id:", payload.get("response_id"), flush=True)
    print("text length:", len(text), flush=True)
    print("sourcedocuments count:", len(source_documents), flush=True)
    if text:
        print("text preview:", text[:800], flush=True)

    for index, document in enumerate(source_documents[:5], start=1):
        if not isinstance(document, dict):
            print(f"source {index}: non-object document {type(document).__name__}", flush=True)
            continue
        metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
        print(
            json.dumps(
                {
                    "index": index,
                    "content_preview": str(document.get("content") or "")[:300],
                    "source": metadata.get("source"),
                    "dokumententyp": metadata.get("dokumententyp"),
                    "datum": metadata.get("datum"),
                    "aktenzeichen": metadata.get("aktenzeichen"),
                    "oso_url": metadata.get("oso_url"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Otto Schmidt Legal Data Hub /api/qna.")
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--grant-type", default=os.getenv("LEGAL_DATA_HUB_GRANT_TYPE", "authorization_code"))
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--token", default=os.getenv("LEGAL_DATA_HUB_BEARER_TOKEN"))
    parser.add_argument("--no-trust-env", action="store_true", help="Ignore proxy env vars for httpx.")
    args = parser.parse_args()

    settings = get_settings()
    timeout = float(args.timeout or settings.legal_data_hub_timeout)
    print("Config:", flush=True)
    print(f"  base_url={settings.legal_data_hub_base_url}", flush=True)
    print(f"  qna_path={settings.legal_data_hub_qna_path}", flush=True)
    print(f"  token_url={settings.legal_data_hub_token_url}", flush=True)
    print(f"  auth_mode={settings.legal_data_hub_auth_mode}", flush=True)
    print(f"  timeout={timeout}", flush=True)
    print(f"  lda_client={_masked(settings.lda_client)}", flush=True)
    print(f"  lda_secret={_masked(settings.lda_secret)}", flush=True)
    print(f"  trust_env={not args.no_trust_env}", flush=True)

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=_timeout(timeout), trust_env=not args.no_trust_env) as client:
        bearer_token = args.token
        if not bearer_token:
            bearer_token = await _token(settings, client, args.grant_type)
        else:
            print("Using bearer token from LEGAL_DATA_HUB_BEARER_TOKEN/--token", flush=True)
        print(f"Bearer token: {_masked(bearer_token)}", flush=True)
        payload = await _qna(settings, client, bearer_token, args.question)

    print(f"Total elapsed: {time.monotonic() - started:.2f}s", flush=True)
    _print_qna_payload(payload)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
