from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import contracts, dashboard, escalations, legal_qa
from app.core.config import get_settings
from app.services.contract_repository import ContractRepository
from app.services.escalation_repository import EscalationRepository

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contracts.router)
app.include_router(legal_qa.router)
app.include_router(escalations.router)
app.include_router(dashboard.router)


@app.on_event("startup")
async def initialize_database() -> None:
    ContractRepository()
    EscalationRepository()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
