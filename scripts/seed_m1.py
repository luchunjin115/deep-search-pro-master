"""Load the deterministic M1 synthetic demo dataset into PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from pwdlib import PasswordHash
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.identity import Role, Tenant, User, UserRole
from app.models.inventory import InventorySnapshot, Warehouse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seed" / "m1_seed.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "seed" / "m1_manifest.json"
SEED_NAMESPACE = UUID("c4f77885-d16f-4b35-9dac-89e32e9be8b4")
PASSWORD_HASHER = PasswordHash.recommended()


class SeedDataMismatchError(RuntimeError):
    """Raised when existing rows conflict with the versioned M1 seed contract."""


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Stable summary returned by one successful seed execution."""

    manifest: dict[str, Any]
    manifest_path: Path


def deterministic_id(version: str, entity: str, key: str) -> UUID:
    """Create a stable UUID for one versioned seed entity."""

    return uuid5(SEED_NAMESPACE, f"{version}:{entity}:{key}")


def load_seed_definition(path: Path = DEFAULT_SEED_PATH) -> dict[str, Any]:
    """Read and minimally validate the trusted, versioned seed definition."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != "m1-v1":
        raise SeedDataMismatchError("M1 seed version must be m1-v1")
    if data.get("data_classification") != "synthetic_demo_data":
        raise SeedDataMismatchError("M1 seed must be marked as synthetic demo data")
    if "password" in json.dumps(data, ensure_ascii=False).lower():
        raise SeedDataMismatchError("Seed definition must not contain passwords")
    return data


def seed_content_hash(data: dict[str, Any]) -> str:
    """Hash canonical business input, independent of JSON whitespace."""

    canonical = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _same_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, datetime) and isinstance(expected, datetime):
        return actual == expected
    return actual == expected


def _verify_fields(instance: Any, expected: dict[str, Any], label: str) -> None:
    mismatches = [
        field
        for field, value in expected.items()
        if not _same_value(getattr(instance, field), value)
    ]
    if mismatches:
        joined = ", ".join(sorted(mismatches))
        raise SeedDataMismatchError(f"Existing {label} differs in: {joined}")


def _existing_by_id_or_natural_key(
    session: Session,
    model: type[Any],
    entity_id: UUID,
    natural_query: Select[tuple[Any]],
    label: str,
) -> Any | None:
    by_id = session.get(model, entity_id)
    by_natural_key = session.scalar(natural_query)
    if by_id is not None and by_natural_key is not None and by_id is not by_natural_key:
        raise SeedDataMismatchError(
            f"Existing {label} has a conflicting deterministic ID"
        )
    existing = by_id or by_natural_key
    if existing is not None and existing.id != entity_id:
        raise SeedDataMismatchError(
            f"Existing {label} has a conflicting deterministic ID"
        )
    return existing


def _get_or_create(
    session: Session,
    model: type[Any],
    entity_id: UUID,
    natural_query: Select[tuple[Any]],
    expected: dict[str, Any],
    label: str,
) -> Any:
    existing = _existing_by_id_or_natural_key(
        session,
        model,
        entity_id,
        natural_query,
        label,
    )
    if existing is not None:
        _verify_fields(existing, expected, label)
        return existing

    instance = model(id=entity_id, **expected)
    session.add(instance)
    session.flush()
    return instance


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seed_identity(
    session: Session,
    data: dict[str, Any],
    password: str,
) -> tuple[Tenant, dict[str, Role]]:
    version = data["version"]
    tenant_data = data["tenant"]
    tenant_id = deterministic_id(version, "tenant", tenant_data["name"])
    tenant = _get_or_create(
        session,
        Tenant,
        tenant_id,
        select(Tenant).where(Tenant.id == tenant_id),
        {"name": tenant_data["name"], "is_demo": tenant_data["is_demo"]},
        "tenant",
    )

    roles: dict[str, Role] = {}
    for role_name in data["roles"]:
        role_id = deterministic_id(version, "role", role_name)
        roles[role_name] = _get_or_create(
            session,
            Role,
            role_id,
            select(Role).where(Role.name == role_name),
            {"name": role_name},
            f"role {role_name}",
        )

    for user_data in data["users"]:
        email = user_data["email"]
        user_id = deterministic_id(version, "user", email)
        existing_user = _existing_by_id_or_natural_key(
            session,
            User,
            user_id,
            select(User).where(User.tenant_id == tenant.id, User.email == email),
            f"user {email}",
        )
        public_fields = {
            "tenant_id": tenant.id,
            "email": email,
            "display_name": user_data["display_name"],
            "status": "active",
        }
        if existing_user is None:
            existing_user = User(
                id=user_id,
                password_hash=PASSWORD_HASHER.hash(password),
                **public_fields,
            )
            session.add(existing_user)
            session.flush()
        else:
            _verify_fields(existing_user, public_fields, f"user {email}")
            if not PASSWORD_HASHER.verify(password, existing_user.password_hash):
                raise SeedDataMismatchError(
                    f"Existing user {email} does not match M1_DEMO_PASSWORD"
                )

        role = roles[user_data["role"]]
        assignment = session.get(UserRole, (existing_user.id, role.id))
        expected_assignment = {"market_scopes": user_data["market_scopes"]}
        if assignment is None:
            assignment = UserRole(
                user_id=existing_user.id,
                role_id=role.id,
                **expected_assignment,
            )
            session.add(assignment)
            session.flush()
        else:
            _verify_fields(
                assignment,
                expected_assignment,
                f"role assignment for {email}",
            )

    return tenant, roles


def _seed_catalog_and_inventory(
    session: Session,
    data: dict[str, Any],
    tenant: Tenant,
) -> None:
    version = data["version"]
    product_data = data["product"]
    product_id = deterministic_id(version, "product", product_data["spu"])
    product = _get_or_create(
        session,
        Product,
        product_id,
        select(Product).where(
            Product.tenant_id == tenant.id,
            Product.spu == product_data["spu"],
        ),
        {
            "tenant_id": tenant.id,
            "spu": product_data["spu"],
            "name_zh": product_data["name_zh"],
            "name_en": product_data["name_en"],
            "aliases": product_data["aliases"],
            "status": product_data["status"],
            "is_demo": product_data["is_demo"],
        },
        f"product {product_data['spu']}",
    )

    variant_data = product_data["variant"]
    variant_id = deterministic_id(version, "variant", variant_data["sku"])
    variant = _get_or_create(
        session,
        ProductVariant,
        variant_id,
        select(ProductVariant).where(
            ProductVariant.tenant_id == tenant.id,
            ProductVariant.sku == variant_data["sku"],
        ),
        {
            "tenant_id": tenant.id,
            "product_id": product.id,
            "sku": variant_data["sku"],
            "color": variant_data["color"],
            "size": variant_data["size"],
            "status": variant_data["status"],
        },
        f"variant {variant_data['sku']}",
    )

    for spec_data in variant_data["specs"]:
        spec_id = deterministic_id(
            version,
            "product_spec",
            f"{variant_data['sku']}:{spec_data['name']}",
        )
        _get_or_create(
            session,
            ProductSpec,
            spec_id,
            select(ProductSpec).where(
                ProductSpec.tenant_id == tenant.id,
                ProductSpec.variant_id == variant.id,
                ProductSpec.name == spec_data["name"],
            ),
            {
                "tenant_id": tenant.id,
                "variant_id": variant.id,
                "name": spec_data["name"],
                "value": spec_data["value"],
                "unit": spec_data["unit"],
                "source_type": "synthetic_seed",
                "source_id": version,
                "verification_status": "demo_declared",
            },
            f"product spec {spec_data['name']}",
        )

    for warehouse_data in data["warehouses"]:
        warehouse_id = deterministic_id(version, "warehouse", warehouse_data["code"])
        warehouse = _get_or_create(
            session,
            Warehouse,
            warehouse_id,
            select(Warehouse).where(
                Warehouse.tenant_id == tenant.id,
                Warehouse.code == warehouse_data["code"],
            ),
            {
                "tenant_id": tenant.id,
                "code": warehouse_data["code"],
                "market_code": warehouse_data["market_code"],
                "name": warehouse_data["name"],
                "status": warehouse_data["status"],
                "is_demo": warehouse_data["is_demo"],
            },
            f"warehouse {warehouse_data['code']}",
        )

        inventory = warehouse_data["inventory"]
        snapshot_at = _parse_timestamp(inventory["snapshot_at"])
        snapshot_key = (
            f"{variant_data['sku']}:{warehouse_data['code']}:{inventory['snapshot_at']}"
        )
        snapshot_id = deterministic_id(version, "inventory_snapshot", snapshot_key)
        _get_or_create(
            session,
            InventorySnapshot,
            snapshot_id,
            select(InventorySnapshot).where(
                InventorySnapshot.tenant_id == tenant.id,
                InventorySnapshot.variant_id == variant.id,
                InventorySnapshot.warehouse_id == warehouse.id,
                InventorySnapshot.snapshot_at == snapshot_at,
            ),
            {
                "tenant_id": tenant.id,
                "variant_id": variant.id,
                "warehouse_id": warehouse.id,
                "on_hand": inventory["on_hand"],
                "reserved": inventory["reserved"],
                "unsellable": inventory["unsellable"],
                "inbound": inventory["inbound"],
                "safety_stock": inventory["safety_stock"],
                "snapshot_at": snapshot_at,
                "is_demo": True,
            },
            f"inventory snapshot {snapshot_key}",
        )


def build_manifest(data: dict[str, Any]) -> dict[str, Any]:
    """Build a stable, reviewable summary of the M1 seed contract."""

    de_warehouse = next(
        warehouse for warehouse in data["warehouses"] if warehouse["code"] == "DE-FRA"
    )
    inventory = de_warehouse["inventory"]
    available = inventory["on_hand"] - inventory["reserved"] - inventory["unsellable"]
    return {
        "version": data["version"],
        "random_seed": data["random_seed"],
        "data_classification": data["data_classification"],
        "content_hash": seed_content_hash(data),
        "seeded_row_counts": {
            "tenants": 1,
            "roles": len(data["roles"]),
            "users": len(data["users"]),
            "user_roles": len(data["users"]),
            "products": 1,
            "product_variants": 1,
            "product_specs": len(data["product"]["variant"]["specs"]),
            "warehouses": len(data["warehouses"]),
            "inventory_snapshots": len(data["warehouses"]),
            "threads": 0,
            "messages": 0,
            "agent_runs": 0,
            "tool_calls": 0,
            "evidences": 0,
        },
        "key_answer": {
            "question": "德国仓蘑菇灯还有多少可售库存？",
            "sku": data["product"]["variant"]["sku"],
            "warehouse_code": de_warehouse["code"],
            "market_code": de_warehouse["market_code"],
            "on_hand": inventory["on_hand"],
            "reserved": inventory["reserved"],
            "unsellable": inventory["unsellable"],
            "available": available,
            "inbound": inventory["inbound"],
            "safety_stock": inventory["safety_stock"],
            "snapshot_at": inventory["snapshot_at"],
            "synthetic_data": True,
        },
    }


def seed_m1(
    settings: Settings | None = None,
    seed_path: Path = DEFAULT_SEED_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> SeedResult:
    """Insert missing M1 rows, verify existing rows, and write a stable manifest."""

    resolved_settings = settings or Settings()
    data = load_seed_definition(seed_path)
    manifest = build_manifest(data)
    password = resolved_settings.m1_demo_password.get_secret_value()
    runtime = create_database_runtime(resolved_settings)

    try:
        with runtime.session_factory.begin() as session:
            tenant, _roles = _seed_identity(session, data, password)
            _seed_catalog_and_inventory(session, data, tenant)
    finally:
        runtime.engine.dispose()

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return SeedResult(manifest=manifest, manifest_path=manifest_path)


def main() -> None:
    """CLI entry point for local M1 data preparation."""

    result = seed_m1()
    answer = result.manifest["key_answer"]
    print("M1 synthetic demo data is ready.")
    print(f"Manifest: {result.manifest_path}")
    print(
        "Key answer: "
        f"{answer['sku']} at {answer['warehouse_code']} has "
        f"{answer['available']} sellable units."
    )


if __name__ == "__main__":
    main()
