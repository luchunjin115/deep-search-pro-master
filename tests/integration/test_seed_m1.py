import json
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pwdlib import PasswordHash
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.identity import Role, Tenant, User, UserRole
from app.models.inventory import InventorySnapshot, Warehouse
from app.models.runtime import AgentRun, Evidence, Message, Thread, ToolCall
from scripts.seed_m1 import (
    DEFAULT_SEED_PATH,
    deterministic_id,
    load_seed_definition,
    seed_m1,
)


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


def _clean_seed_rows(engine: Engine, version: str) -> None:
    tenant_id = deterministic_id(version, "tenant", "LUMORIVA M1 合成演示公司")
    role_ids = [
        deterministic_id(version, "role", role_name)
        for role_name in ("company_owner", "product_scout", "amazon_operator")
    ]
    with engine.begin() as connection:
        connection.execute(delete(Tenant).where(Tenant.id == tenant_id))
        connection.execute(delete(Role).where(Role.id.in_(role_ids)))


def _count(engine: Engine, model: type[object]) -> int:
    with engine.connect() as connection:
        return int(connection.scalar(select(func.count()).select_from(model)) or 0)


def test_seed_is_repeatable_and_matches_business_contract(
    postgres_settings: Settings,
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    command.upgrade(Config("alembic.ini"), "head")
    data = load_seed_definition(DEFAULT_SEED_PATH)
    version = data["version"]
    manifest_path = tmp_path / "m1_manifest.json"
    _clean_seed_rows(postgres_engine, version)

    try:
        first = seed_m1(postgres_settings, manifest_path=manifest_path)
        first_file = manifest_path.read_bytes()
        second = seed_m1(postgres_settings, manifest_path=manifest_path)
        second_file = manifest_path.read_bytes()

        assert first.manifest == second.manifest
        assert first_file == second_file
        assert json.loads(second_file)["content_hash"].startswith("sha256:")

        expected_counts = first.manifest["seeded_row_counts"]
        model_counts = {
            "tenants": Tenant,
            "roles": Role,
            "users": User,
            "user_roles": UserRole,
            "products": Product,
            "product_variants": ProductVariant,
            "product_specs": ProductSpec,
            "warehouses": Warehouse,
            "inventory_snapshots": InventorySnapshot,
            "threads": Thread,
            "messages": Message,
            "agent_runs": AgentRun,
            "tool_calls": ToolCall,
            "evidences": Evidence,
        }
        for table_name, model in model_counts.items():
            assert _count(postgres_engine, model) == expected_counts[table_name]

        answer = first.manifest["key_answer"]
        assert answer["sku"] == "LR-TL-MUSH-OR01"
        assert answer["warehouse_code"] == "DE-FRA"
        assert answer["available"] == 125
        assert answer["available"] == (
            answer["on_hand"] - answer["reserved"] - answer["unsellable"]
        )
        assert answer["synthetic_data"] is True

        with Session(postgres_engine) as session:
            users = list(session.scalars(select(User).order_by(User.email)))
            assignments = list(session.scalars(select(UserRole)))
            products = list(session.scalars(select(Product)))
            warehouses = list(session.scalars(select(Warehouse)))
            snapshots = list(session.scalars(select(InventorySnapshot)))

        password = postgres_settings.m1_demo_password.get_secret_value()
        password_hasher = PasswordHash.recommended()
        assert len(users) == 4
        assert all(user.password_hash != password for user in users)
        assert all(user.password_hash.startswith("$argon2") for user in users)
        assert all(
            password_hasher.verify(password, user.password_hash) for user in users
        )
        assert sorted(assignment.market_scopes for assignment in assignments) == [
            ["DE"],
            ["DE", "FR"],
            ["DE", "FR"],
            ["FR"],
        ]
        assert all(product.is_demo for product in products)
        assert all(warehouse.is_demo for warehouse in warehouses)
        assert all(snapshot.is_demo for snapshot in snapshots)
    finally:
        _clean_seed_rows(postgres_engine, version)
