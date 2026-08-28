"""Create the M1 product catalog, warehouses, and inventory snapshots.

Revision ID: 20260828_0002
Revises: 20260828_0001
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_0002"
down_revision: str | None = "20260828_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the M1 catalog and inventory boundary."""

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("spu", sa.String(length=64), nullable=False),
        sa.Column("name_zh", sa.String(length=200), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column(
            "aliases",
            sa.ARRAY(sa.String(length=100)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'candidate'"),
            nullable=False,
        ),
        sa.Column(
            "is_demo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "array_position(aliases, NULL) IS NULL",
            name=op.f("ck_products_aliases_no_null"),
        ),
        sa.CheckConstraint(
            "cardinality(aliases) BETWEEN 0 AND 20",
            name=op.f("ck_products_aliases_size"),
        ),
        sa.CheckConstraint(
            "spu ~ '^[A-Z0-9][A-Z0-9-]{2,63}$'",
            name=op.f("ck_products_spu_format"),
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'active', 'inactive', 'discontinued')",
            name=op.f("ck_products_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_products_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_products_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "spu",
            name=op.f("uq_products_tenant_spu"),
        ),
    )
    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=80), nullable=True),
        sa.Column("size", sa.String(length=80), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'candidate'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sku ~ '^[A-Z0-9][A-Z0-9-]{2,63}$'",
            name=op.f("ck_product_variants_sku_format"),
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'active', 'inactive', 'discontinued')",
            name=op.f("ck_product_variants_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_product_variants_tenant_product"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_variants")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_product_variants_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "sku",
            name=op.f("uq_product_variants_tenant_sku"),
        ),
    )
    op.create_table(
        "product_specs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN "
            "('synthetic_seed', 'supplier_document', 'image_observation', "
            "'manual_entry')",
            name=op.f("ck_product_specs_source_type_allowed"),
        ),
        sa.CheckConstraint(
            "verification_status IN ('demo_declared', 'unverified', 'verified')",
            name=op.f("ck_product_specs_verification_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name=op.f("fk_product_specs_tenant_variant"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_specs")),
        sa.UniqueConstraint(
            "tenant_id",
            "variant_id",
            "name",
            name=op.f("uq_product_specs_tenant_variant_name"),
        ),
    )
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("market_code", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "is_demo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code ~ '^[A-Z]{2}-[A-Z0-9]{3,8}$'",
            name=op.f("ck_warehouses_code_format"),
        ),
        sa.CheckConstraint(
            "market_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_warehouses_market_code_format"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name=op.f("ck_warehouses_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_warehouses_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_warehouses")),
        sa.UniqueConstraint(
            "tenant_id",
            "code",
            name=op.f("uq_warehouses_tenant_code"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_warehouses_tenant_id_id"),
        ),
    )
    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("unsellable", sa.Integer(), nullable=False),
        sa.Column("inbound", sa.Integer(), nullable=False),
        sa.Column("safety_stock", sa.Integer(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_demo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reserved + unsellable <= on_hand",
            name=op.f("ck_inventory_snapshots_allocations_within_on_hand"),
        ),
        sa.CheckConstraint(
            "inbound >= 0",
            name=op.f("ck_inventory_snapshots_inbound_nonnegative"),
        ),
        sa.CheckConstraint(
            "on_hand >= 0",
            name=op.f("ck_inventory_snapshots_on_hand_nonnegative"),
        ),
        sa.CheckConstraint(
            "reserved >= 0",
            name=op.f("ck_inventory_snapshots_reserved_nonnegative"),
        ),
        sa.CheckConstraint(
            "safety_stock >= 0",
            name=op.f("ck_inventory_snapshots_safety_stock_nonnegative"),
        ),
        sa.CheckConstraint(
            "unsellable >= 0",
            name=op.f("ck_inventory_snapshots_unsellable_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name=op.f("fk_inventory_snapshots_tenant_variant"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_inventory_snapshots_tenant_warehouse"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_snapshots")),
        sa.UniqueConstraint(
            "tenant_id",
            "variant_id",
            "warehouse_id",
            "snapshot_at",
            name=op.f("uq_inventory_snapshots_tenant_variant_warehouse_time"),
        ),
    )
    op.create_index(
        "ix_warehouses_tenant_market",
        "warehouses",
        ["tenant_id", "market_code"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the M1 catalog and inventory boundary only."""

    op.drop_index("ix_warehouses_tenant_market", table_name="warehouses")
    op.drop_table("inventory_snapshots")
    op.drop_table("warehouses")
    op.drop_table("product_specs")
    op.drop_table("product_variants")
    op.drop_table("products")
