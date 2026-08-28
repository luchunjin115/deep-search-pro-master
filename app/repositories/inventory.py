"""Fixed, tenant-scoped latest inventory reads for M1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.catalog import Product, ProductVariant
from app.models.inventory import InventorySnapshot, Warehouse
from app.repositories.common import apply_statement_timeout


@dataclass(frozen=True, slots=True)
class InventoryRecord:
    """Raw latest-snapshot facts; available is deliberately computed by Service."""

    snapshot_id: UUID
    product_id: UUID
    variant_id: UUID
    warehouse_id: UUID
    sku: str
    product_name: str
    market_code: str
    warehouse_code: str
    warehouse_name: str
    on_hand: int
    reserved: int
    unsellable: int
    inbound: int
    safety_stock: int
    snapshot_at: datetime
    synthetic_data: bool


class InventoryRepository:
    """Read latest stock through a fixed SQLAlchemy query with tenant filters."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def find_latest(
        self,
        tenant_id: UUID,
        sku: str,
        market_code: str,
        warehouse_code: str | None = None,
    ) -> list[InventoryRecord]:
        """Return the newest snapshot for every matching active warehouse."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        latest_times = (
            select(
                InventorySnapshot.tenant_id.label("tenant_id"),
                InventorySnapshot.variant_id.label("variant_id"),
                InventorySnapshot.warehouse_id.label("warehouse_id"),
                func.max(InventorySnapshot.snapshot_at).label("snapshot_at"),
            )
            .where(InventorySnapshot.tenant_id == tenant_id)
            .group_by(
                InventorySnapshot.tenant_id,
                InventorySnapshot.variant_id,
                InventorySnapshot.warehouse_id,
            )
            .subquery()
        )

        statement = (
            select(InventorySnapshot, ProductVariant, Product, Warehouse)
            .join(
                ProductVariant,
                and_(
                    ProductVariant.tenant_id == InventorySnapshot.tenant_id,
                    ProductVariant.id == InventorySnapshot.variant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.tenant_id == ProductVariant.tenant_id,
                    Product.id == ProductVariant.product_id,
                ),
            )
            .join(
                Warehouse,
                and_(
                    Warehouse.tenant_id == InventorySnapshot.tenant_id,
                    Warehouse.id == InventorySnapshot.warehouse_id,
                ),
            )
            .join(
                latest_times,
                and_(
                    latest_times.c.tenant_id == InventorySnapshot.tenant_id,
                    latest_times.c.variant_id == InventorySnapshot.variant_id,
                    latest_times.c.warehouse_id == InventorySnapshot.warehouse_id,
                    latest_times.c.snapshot_at == InventorySnapshot.snapshot_at,
                ),
            )
            .where(
                InventorySnapshot.tenant_id == tenant_id,
                ProductVariant.tenant_id == tenant_id,
                Product.tenant_id == tenant_id,
                Warehouse.tenant_id == tenant_id,
                ProductVariant.sku == sku,
                Warehouse.market_code == market_code,
                Warehouse.status == "active",
            )
            .order_by(Warehouse.code)
        )
        if warehouse_code is not None:
            statement = statement.where(Warehouse.code == warehouse_code)

        rows = self._session.execute(statement).all()
        return [
            InventoryRecord(
                snapshot_id=snapshot.id,
                product_id=product.id,
                variant_id=variant.id,
                warehouse_id=warehouse.id,
                sku=variant.sku,
                product_name=product.name_zh,
                market_code=warehouse.market_code,
                warehouse_code=warehouse.code,
                warehouse_name=warehouse.name,
                on_hand=snapshot.on_hand,
                reserved=snapshot.reserved,
                unsellable=snapshot.unsellable,
                inbound=snapshot.inbound,
                safety_stock=snapshot.safety_stock,
                snapshot_at=snapshot.snapshot_at,
                synthetic_data=product.is_demo
                and warehouse.is_demo
                and snapshot.is_demo,
            )
            for snapshot, variant, product, warehouse in rows
        ]
