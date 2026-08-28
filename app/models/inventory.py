"""Warehouse and point-in-time inventory snapshot models for M1."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.catalog import ProductVariant
from app.models.identity import Tenant


class Warehouse(Base):
    """A tenant-owned warehouse assigned to one market."""

    __tablename__ = "warehouses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_warehouses_tenant_id_id"),
        UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
        Index("ix_warehouses_tenant_market", "tenant_id", "market_code"),
        CheckConstraint(
            "code ~ '^[A-Z]{2}-[A-Z0-9]{3,8}$'",
            name="code_format",
        ),
        CheckConstraint(
            "market_code ~ '^[A-Z]{2}$'",
            name="market_code_format",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    market_code: Mapped[str] = mapped_column(String(2), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped[Tenant] = relationship()
    snapshots: Mapped[list[InventorySnapshot]] = relationship(
        back_populates="warehouse",
        cascade="all, delete-orphan",
        passive_deletes=True,
        overlaps="variant",
    )


class InventorySnapshot(Base):
    """Raw stock quantities observed for one SKU and warehouse at one time."""

    __tablename__ = "inventory_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "variant_id",
            "warehouse_id",
            "snapshot_at",
            name="uq_inventory_snapshots_tenant_variant_warehouse_time",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_inventory_snapshots_tenant_variant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name="fk_inventory_snapshots_tenant_warehouse",
            ondelete="CASCADE",
        ),
        CheckConstraint("on_hand >= 0", name="on_hand_nonnegative"),
        CheckConstraint("reserved >= 0", name="reserved_nonnegative"),
        CheckConstraint("unsellable >= 0", name="unsellable_nonnegative"),
        CheckConstraint("inbound >= 0", name="inbound_nonnegative"),
        CheckConstraint("safety_stock >= 0", name="safety_stock_nonnegative"),
        CheckConstraint(
            "reserved + unsellable <= on_hand",
            name="allocations_within_on_hand",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    unsellable: Mapped[int] = mapped_column(Integer, nullable=False)
    inbound: Mapped[int] = mapped_column(Integer, nullable=False)
    safety_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    variant: Mapped[ProductVariant] = relationship(overlaps="snapshots,warehouse")
    warehouse: Mapped[Warehouse] = relationship(
        back_populates="snapshots",
        overlaps="variant",
    )
