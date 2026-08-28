from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, insert, inspect
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.identity import Tenant
from app.models.inventory import InventorySnapshot, Warehouse


@pytest.fixture
def postgres_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(_env_file=".env.example", app_env="test")
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    return settings


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


def alembic_config() -> Config:
    return Config("alembic.ini")


def test_catalog_inventory_migration_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()
    domain_tables = {
        "inventory_snapshots",
        "product_specs",
        "product_variants",
        "products",
        "warehouses",
    }
    identity_tables = {"roles", "tenants", "user_roles", "users"}

    try:
        command.downgrade(config, "20260828_0001")
        runtime = create_database_runtime(Settings())
        try:
            table_names = set(inspect(runtime.engine).get_table_names())
            assert domain_tables.isdisjoint(table_names)
            assert identity_tables <= table_names
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260828_0002")
        runtime = create_database_runtime(Settings())
        try:
            assert domain_tables <= set(inspect(runtime.engine).get_table_names())
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260828_0001")
        command.upgrade(config, "20260828_0002")
        runtime = create_database_runtime(Settings())
        try:
            assert domain_tables <= set(inspect(runtime.engine).get_table_names())
        finally:
            runtime.engine.dispose()
    finally:
        command.upgrade(config, "head")


def test_database_rejects_invalid_catalog_inventory_rows(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    product_id = uuid4()
    variant_id = uuid4()
    warehouse_id = uuid4()
    snapshot_at = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                insert(Tenant),
                [
                    {"id": tenant_id, "name": "M1 catalog tenant"},
                    {"id": other_tenant_id, "name": "M1 other tenant"},
                ],
            )
            connection.execute(
                insert(Product).values(
                    id=product_id,
                    tenant_id=tenant_id,
                    spu="LR-TL-MUSH",
                    name_zh="橙色复古蘑菇台灯",
                    name_en="LUMORIVA Orange Mushroom Table Lamp",
                    aliases=["蘑菇灯", "mushroom lamp"],
                )
            )
            connection.execute(
                insert(ProductVariant).values(
                    id=variant_id,
                    tenant_id=tenant_id,
                    product_id=product_id,
                    sku="LR-TL-MUSH-OR01",
                    color="orange",
                )
            )
            connection.execute(
                insert(Warehouse).values(
                    id=warehouse_id,
                    tenant_id=tenant_id,
                    code="DE-FRA",
                    market_code="DE",
                    name="德国法兰克福海外仓",
                )
            )
            connection.execute(
                insert(ProductSpec).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    variant_id=variant_id,
                    name="height",
                    value="30",
                    unit="cm",
                    source_type="synthetic_seed",
                    source_id="m1-v1",
                    verification_status="demo_declared",
                )
            )
            valid_snapshot = {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "variant_id": variant_id,
                "warehouse_id": warehouse_id,
                "on_hand": 150,
                "reserved": 20,
                "unsellable": 5,
                "inbound": 80,
                "safety_stock": 60,
                "snapshot_at": snapshot_at,
            }
            connection.execute(insert(InventorySnapshot).values(**valid_snapshot))

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(ProductVariant).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        product_id=product_id,
                        sku="LR-TL-MUSH-OR01",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(ProductVariant).values(
                        id=uuid4(),
                        tenant_id=other_tenant_id,
                        product_id=product_id,
                        sku="CROSS-TENANT-SKU",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Warehouse).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        code="DE-FRA",
                        market_code="DE",
                        name="Duplicate warehouse",
                    )
                )

            duplicate_snapshot = valid_snapshot | {"id": uuid4()}
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(InventorySnapshot).values(**duplicate_snapshot)
                )

            negative_snapshot = valid_snapshot | {
                "id": uuid4(),
                "snapshot_at": datetime(2026, 8, 28, 7, 0, tzinfo=UTC),
                "inbound": -1,
            }
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(InventorySnapshot).values(**negative_snapshot)
                )

            overallocated_snapshot = valid_snapshot | {
                "id": uuid4(),
                "snapshot_at": datetime(2026, 8, 28, 8, 0, tzinfo=UTC),
                "reserved": 146,
            }
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(InventorySnapshot).values(**overallocated_snapshot)
                )

            cross_tenant_snapshot = valid_snapshot | {
                "id": uuid4(),
                "tenant_id": other_tenant_id,
                "snapshot_at": datetime(2026, 8, 28, 9, 0, tzinfo=UTC),
            }
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(InventorySnapshot).values(**cross_tenant_snapshot)
                )
        finally:
            transaction.rollback()


def test_model_metadata_contains_applied_catalog_inventory_tables(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    domain_tables = {
        "inventory_snapshots",
        "product_specs",
        "product_variants",
        "products",
        "warehouses",
    }

    assert domain_tables <= set(Base.metadata.tables)
    assert domain_tables <= set(inspect(postgres_engine).get_table_names())
