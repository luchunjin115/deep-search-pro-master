"""Inventory calculation, error mapping, and Evidence orchestration for M1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.errors import (
    DatabaseQueryError,
    DatabaseTimeoutError,
    InventoryDataContractError,
    InventoryNotFoundError,
    WarehouseRequiredError,
)
from app.repositories.inventory import InventoryRecord
from app.schemas.common import MarketCode, WarehouseCode
from app.schemas.evidence import EvidenceDetail
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.services.evidence import EvidenceWriteContext


class InventoryReader(Protocol):
    """The single controlled inventory read operation allowed to this Service."""

    def find_latest(
        self,
        tenant_id: UUID,
        sku: str,
        market_code: str,
        warehouse_code: str | None = None,
    ) -> list[InventoryRecord]: ...


class InventoryEvidenceWriter(Protocol):
    """The Evidence operation that must complete before inventory success."""

    def persist_inventory_evidence(
        self,
        context: EvidenceWriteContext,
        request: SearchInventoryInput,
        inventory: InventoryResult,
        snapshot_id: UUID,
    ) -> EvidenceDetail: ...


@dataclass(frozen=True, slots=True)
class InventoryServiceResult:
    """A checked inventory result plus its already-flushed Evidence."""

    inventory: InventoryResult
    evidence: EvidenceDetail


class InventoryService:
    """Turn latest raw stock into one sellable result and database Evidence."""

    def __init__(
        self,
        repository: InventoryReader,
        evidence_writer: InventoryEvidenceWriter,
    ) -> None:
        self._repository = repository
        self._evidence_writer = evidence_writer

    def search_inventory(
        self,
        context: EvidenceWriteContext,
        request: SearchInventoryInput,
    ) -> InventoryServiceResult:
        """Query one location, calculate available, then persist its Evidence."""

        try:
            records = self._repository.find_latest(
                context.tenant_id,
                request.sku,
                request.market_code,
                request.warehouse_code,
            )
        except OperationalError as error:
            if _is_statement_timeout(error):
                raise DatabaseTimeoutError from None
            raise DatabaseQueryError from None
        except SQLAlchemyError:
            raise DatabaseQueryError from None

        if not records:
            raise InventoryNotFoundError
        if len(records) > 1:
            raise WarehouseRequiredError

        record = records[0]
        if not record.synthetic_data:
            raise InventoryDataContractError

        available = record.on_hand - record.reserved - record.unsellable
        try:
            inventory = InventoryResult(
                sku=record.sku,
                product_name=record.product_name,
                market_code=cast(MarketCode, record.market_code),
                warehouse_code=cast(WarehouseCode, record.warehouse_code),
                warehouse_name=record.warehouse_name,
                on_hand=record.on_hand,
                reserved=record.reserved,
                unsellable=record.unsellable,
                available=available,
                inbound=record.inbound,
                safety_stock=record.safety_stock,
                snapshot_at=record.snapshot_at,
                synthetic_data=True,
            )
        except ValidationError:
            raise InventoryDataContractError from None

        evidence = self._evidence_writer.persist_inventory_evidence(
            context,
            request,
            inventory,
            record.snapshot_id,
        )
        return InventoryServiceResult(inventory=inventory, evidence=evidence)


def _is_statement_timeout(error: OperationalError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None)
    if sqlstate is None:
        sqlstate = getattr(error.orig, "pgcode", None)
    return sqlstate == "57014"
