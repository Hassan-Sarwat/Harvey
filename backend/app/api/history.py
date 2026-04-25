from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.history_repository import HistoryRepository

router = APIRouter(prefix="/api/history", tags=["history"])


class DropHistoryRequest(BaseModel):
    reason: str | None = None


@router.get("")
async def list_history() -> dict:
    return {"items": HistoryRepository().list_items()}


@router.get("/{thread_id}")
async def get_history_item(thread_id: str) -> dict:
    item = HistoryRepository().get_item(thread_id)
    if item is None:
        raise HTTPException(status_code=404, detail="History item not found.")
    return item


@router.post("/{thread_id}/drop")
async def drop_history_item(thread_id: str, request: DropHistoryRequest | None = None) -> dict:
    item = HistoryRepository().drop_item(thread_id, reason=(request.reason if request else None))
    if item is None:
        raise HTTPException(status_code=404, detail="History item not found.")
    return item
