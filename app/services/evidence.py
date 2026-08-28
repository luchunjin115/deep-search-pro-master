"""Deterministically persist M1 database Evidence from validated service facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    EvidenceNotFoundError,
    EvidencePersistenceError,
    EvidenceReadError,
)
from app.models.runtime import Evidence
from app.schemas.auth import CurrentUser
from app.schemas.evidence import (
    EvidenceAccessScope,
    EvidenceDetail,
    EvidenceSummary,
    InventoryEvidenceQuery,
)
from app.schemas.inventory import InventoryResult, SearchInventoryInput


@dataclass(frozen=True, slots=True)
class EvidenceWriteContext:
    """Trusted runtime IDs required by the Evidence foreign-key chain."""

    tenant_id: UUID
    agent_run_id: UUID
    tool_call_id: UUID


class EvidenceService:
    """Write structured database Evidence before inventory success is returned."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def persist_inventory_evidence(
        self,
        context: EvidenceWriteContext,
        request: SearchInventoryInput,
        inventory: InventoryResult,
        snapshot_id: UUID,
    ) -> EvidenceDetail:
        """Persist and return the exact database fact supporting an inventory result."""

        evidence_id = uuid4()
        created_at = datetime.now(UTC)
        query_summary = InventoryEvidenceQuery(
            sku=request.sku,
            market_code=request.market_code,
            warehouse_code=inventory.warehouse_code,
        )
        access_scope = EvidenceAccessScope(
            tenant_id=context.tenant_id,
            market_codes=[inventory.market_code],
        )
        source_locator = f"inventory_snapshots/{snapshot_id}"
        title = f"{inventory.warehouse_code} {inventory.product_name}库存"
        excerpt = (
            f"SKU {inventory.sku}可售库存{inventory.available}件，"
            f"数据时间{inventory.snapshot_at.isoformat()}"
        )
        confidence = Decimal("1.000")

        evidence_row = Evidence(
            id=evidence_id,
            tenant_id=context.tenant_id,
            agent_run_id=context.agent_run_id,
            tool_call_id=context.tool_call_id,
            source_type="database",
            source_name="synthetic_inventory",
            source_locator=source_locator,
            title=title,
            excerpt=excerpt,
            query_summary=query_summary.model_dump(mode="json"),
            structured_data=inventory.model_dump(mode="json"),
            observed_at=inventory.snapshot_at,
            confidence=confidence,
            trust_level="internal_demo",
            access_scope=access_scope.model_dump(mode="json"),
            synthetic_data=True,
            created_at=created_at,
        )

        try:
            self._session.add(evidence_row)
            self._session.flush()
            return EvidenceDetail(
                id=evidence_id,
                source_type="database",
                source_name="synthetic_inventory",
                source_locator=source_locator,
                title=title,
                excerpt=excerpt,
                query_summary=query_summary,
                structured_data=inventory,
                observed_at=inventory.snapshot_at,
                confidence=confidence,
                trust_level="internal_demo",
                access_scope=access_scope,
                synthetic_data=True,
                created_at=created_at,
            )
        except (SQLAlchemyError, ValidationError):
            raise EvidencePersistenceError from None


class EvidenceReader(Protocol):
    """The only tenant-scoped Evidence read needed by M1 HTTP routes."""

    def find_by_id(self, *, tenant_id: UUID, evidence_id: UUID) -> Evidence | None: ...


class EvidenceQueryService:
    """Hide absent, cross-tenant, and out-of-market Evidence identically."""

    def __init__(self, repository: EvidenceReader) -> None:
        self._repository = repository

    def get_detail(self, user: CurrentUser, evidence_id: UUID) -> EvidenceDetail:
        try:
            row = self._repository.find_by_id(
                tenant_id=user.tenant_id,
                evidence_id=evidence_id,
            )
        except SQLAlchemyError:
            raise EvidenceReadError from None
        if row is None:
            raise EvidenceNotFoundError

        try:
            detail = EvidenceDetail.model_validate(
                {
                    "id": row.id,
                    "source_type": row.source_type,
                    "source_name": row.source_name,
                    "source_locator": row.source_locator,
                    "title": row.title,
                    "excerpt": row.excerpt,
                    "query_summary": row.query_summary,
                    "structured_data": row.structured_data,
                    "observed_at": row.observed_at,
                    "confidence": row.confidence,
                    "trust_level": row.trust_level,
                    "access_scope": row.access_scope,
                    "synthetic_data": row.synthetic_data,
                    "created_at": row.created_at,
                }
            )
        except ValidationError:
            raise EvidenceReadError from None

        if detail.access_scope.tenant_id != user.tenant_id or not set(
            detail.access_scope.market_codes
        ).issubset(user.market_scopes):
            raise EvidenceNotFoundError
        return detail

    def get_summaries(
        self,
        user: CurrentUser,
        evidence_ids: list[UUID],
    ) -> list[EvidenceSummary]:
        return [
            EvidenceSummary(
                id=detail.id,
                source_type=detail.source_type,
                source_name=detail.source_name,
                title=detail.title,
                excerpt=detail.excerpt,
                observed_at=detail.observed_at,
                synthetic_data=True,
            )
            for detail in (
                self.get_detail(user, evidence_id) for evidence_id in evidence_ids
            )
        ]
