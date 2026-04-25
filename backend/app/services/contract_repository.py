from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.types import JSON

from app.agents.base import AgentResult
from app.core.config import get_settings


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint(
            "normalized_contract_type",
            "normalized_vendor",
            "effective_start_date",
            "effective_end_date",
            name="uq_contract_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contract_type: Mapped[str] = mapped_column(String(120))
    vendor: Mapped[str] = mapped_column(String(255))
    normalized_contract_type: Mapped[str] = mapped_column(String(120), index=True)
    normalized_vendor: Mapped[str] = mapped_column(String(255), index=True)
    effective_start_date: Mapped[date] = mapped_column(Date)
    effective_end_date: Mapped[date] = mapped_column(Date)
    current_version_number: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    versions: Mapped[list["ContractVersion"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ContractVersion.version_number",
    )


class ContractVersion(Base):
    __tablename__ = "contract_versions"
    __table_args__ = (UniqueConstraint("contract_pk", "version_number", name="uq_contract_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contract_pk: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stored_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    extracted_text_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    review_result: Mapped[dict[str, Any]] = mapped_column(JSON)
    ai_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    uploaded_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    contract: Mapped[Contract] = relationship(back_populates="versions")


class ContractIdentity:
    def __init__(
        self,
        *,
        contract_type: str,
        vendor: str,
        effective_date: date,
    ) -> None:
        self.contract_type = contract_type.strip()
        self.vendor = vendor.strip()
        self.normalized_contract_type = _normalize(contract_type)
        self.normalized_vendor = _normalize(vendor)
        self.effective_date = effective_date
        self.effective_start_date = effective_date
        self.effective_end_date = effective_date


class ContractRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.engine = _build_engine(database_url or _default_database_url())
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def get_or_create_contract(self, identity: ContractIdentity) -> tuple[Contract, bool]:
        with self.session_factory() as session:
            contract = _find_contract(session, identity)
            if contract:
                return contract, False

            contract = Contract(
                contract_id=f"contract-{uuid4().hex[:12]}",
                contract_type=identity.contract_type,
                vendor=identity.vendor,
                normalized_contract_type=identity.normalized_contract_type,
                normalized_vendor=identity.normalized_vendor,
                effective_start_date=identity.effective_start_date,
                effective_end_date=identity.effective_end_date,
            )
            session.add(contract)
            session.commit()
            session.refresh(contract)
            return contract, True

    def create_version(
        self,
        *,
        contract_id: str,
        contract_document: dict[str, Any],
        review_result: AgentResult,
    ) -> ContractVersion:
        with self.session_factory() as session:
            contract = session.scalar(select(Contract).where(Contract.contract_id == contract_id))
            if contract is None:
                raise ValueError(f"Unknown contract_id: {contract_id}")

            contract.current_version_number += 1
            version = ContractVersion(
                version_id=f"version-{uuid4().hex[:12]}",
                contract_pk=contract.id,
                version_number=contract.current_version_number,
                filename=contract_document.get("filename"),
                stored_path=contract_document.get("stored_path"),
                extracted_text_path=contract_document.get("extracted_text_path"),
                content_hash=contract_document.get("content_hash"),
                character_count=contract_document.get("character_count", 0),
                review_result=review_result.model_dump(mode="json"),
                ai_suggestions=[suggestion.model_dump(mode="json") for suggestion in review_result.suggestions],
                uploaded_at=contract_document.get("uploaded_at"),
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            return version

    def list_versions(self, contract_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            contract = session.scalar(select(Contract).where(Contract.contract_id == contract_id))
            if contract is None:
                return []
            versions = session.scalars(
                select(ContractVersion)
                .where(ContractVersion.contract_pk == contract.id)
                .order_by(ContractVersion.version_number)
            ).all()
            return [_version_payload(contract, version, include_review=False) for version in versions]

    def get_version(self, contract_id: str, version_number: int) -> dict[str, Any] | None:
        with self.session_factory() as session:
            contract = session.scalar(select(Contract).where(Contract.contract_id == contract_id))
            if contract is None:
                return None
            version = session.scalar(
                select(ContractVersion).where(
                    ContractVersion.contract_pk == contract.id,
                    ContractVersion.version_number == version_number,
                )
            )
            if version is None:
                return None
            return _version_payload(contract, version, include_review=True)


def _find_contract(session: Session, identity: ContractIdentity) -> Contract | None:
    return session.scalar(
        select(Contract).where(
            Contract.normalized_contract_type == identity.normalized_contract_type,
            Contract.normalized_vendor == identity.normalized_vendor,
            Contract.effective_start_date == identity.effective_start_date,
            Contract.effective_end_date == identity.effective_end_date,
        )
    )


def _version_payload(contract: Contract, version: ContractVersion, *, include_review: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_id": contract.contract_id,
        "version_id": version.version_id,
        "version_number": version.version_number,
        "contract_type": contract.contract_type,
        "vendor": contract.vendor,
        "effective_date": contract.effective_start_date.isoformat(),
        "contract_document": {
            "filename": version.filename,
            "stored_path": version.stored_path,
            "extracted_text_path": version.extracted_text_path,
            "content_hash": version.content_hash,
            "character_count": version.character_count,
            "uploaded_at": version.uploaded_at,
        },
        "ai_suggestions": version.ai_suggestions,
        "created_at": version.created_at.isoformat(),
    }
    if include_review:
        payload["review_result"] = version.review_result
    return payload


def _build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def _default_database_url() -> str:
    settings = get_settings()
    if settings.database_url:
        return settings.database_url

    configured_path = Path(settings.upload_storage_dir)
    root = configured_path if configured_path.is_absolute() else Path(__file__).resolve().parents[3] / configured_path
    root.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{root / 'harvey.db'}"


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())
