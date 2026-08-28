from app.db.base import Base
from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.inventory import InventorySnapshot, Warehouse


def test_catalog_inventory_metadata_contains_m1_05_tables() -> None:
    assert {
        "inventory_snapshots",
        "product_specs",
        "product_variants",
        "products",
        "warehouses",
    } <= set(Base.metadata.tables)


def test_catalog_inventory_models_use_expected_table_names() -> None:
    assert Product.__tablename__ == "products"
    assert ProductVariant.__tablename__ == "product_variants"
    assert ProductSpec.__tablename__ == "product_specs"
    assert Warehouse.__tablename__ == "warehouses"
    assert InventorySnapshot.__tablename__ == "inventory_snapshots"


def test_available_inventory_is_derived_not_stored() -> None:
    snapshot_columns = set(InventorySnapshot.__table__.columns.keys())

    assert "available" not in snapshot_columns
    assert {"on_hand", "reserved", "unsellable"} <= snapshot_columns
