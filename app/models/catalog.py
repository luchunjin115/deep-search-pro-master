"""Product, SKU variant, and specification models for the M1 catalog."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import Tenant


class Product(Base):
    """An SPU-level product shared by one or more SKU variants."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        UniqueConstraint("tenant_id", "spu", name="uq_products_tenant_spu"),
        CheckConstraint(
            "spu ~ '^[A-Z0-9][A-Z0-9-]{2,63}$'",
            name="spu_format",
        ),
        CheckConstraint(
            "status IN ('candidate', 'active', 'inactive', 'discontinued')",
            name="status_allowed",
        ),
        CheckConstraint(
            "cardinality(aliases) BETWEEN 0 AND 20",
            name="aliases_size",
        ),
        CheckConstraint(
            "array_position(aliases, NULL) IS NULL",
            name="aliases_no_null",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    spu: Mapped[str] = mapped_column(String(64), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="candidate",
        server_default="candidate",
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
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProductVariant(Base):
    """A sellable SKU belonging to an SPU within the same tenant."""

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_product_variants_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "sku",
            name="uq_product_variants_tenant_sku",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_variants_tenant_product",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "sku ~ '^[A-Z0-9][A-Z0-9-]{2,63}$'",
            name="sku_format",
        ),
        CheckConstraint(
            "status IN ('candidate', 'active', 'inactive', 'discontinued')",
            name="status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    product_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(80))
    size: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="candidate",
        server_default="candidate",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    product: Mapped[Product] = relationship(back_populates="variants")
    specs: Mapped[list[ProductSpec]] = relationship(
        back_populates="variant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProductSpec(Base):
    """A traceable key/value specification attached to one SKU variant."""

    __tablename__ = "product_specs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "variant_id",
            "name",
            name="uq_product_specs_tenant_variant_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_product_specs_tenant_variant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "source_type IN "
            "('synthetic_seed', 'supplier_document', 'image_observation', "
            "'manual_entry')",
            name="source_type_allowed",
        ),
        CheckConstraint(
            "verification_status IN ('demo_declared', 'unverified', 'verified')",
            name="verification_status_allowed",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    variant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255))
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    variant: Mapped[ProductVariant] = relationship(back_populates="specs")
