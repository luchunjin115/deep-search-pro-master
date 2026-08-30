from collections.abc import Generator

import pytest
from sqlalchemy import Engine, inspect, text

from app.core.config import Settings
from app.db.session import create_database_runtime


@pytest.fixture
def postgres_engine() -> Generator[Engine, None, None]:
    settings = Settings(app_env="test")
    runtime = create_database_runtime(settings)
    yield runtime.engine
    runtime.engine.dispose()


def test_postgresql_17_has_expected_pgvector_extension(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.connect() as connection:
        server_version_num = int(
            connection.scalar(text("SHOW server_version_num")) or 0
        )
        vector_version = connection.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        distance = connection.scalar(
            text("SELECT '[1,2,3]'::vector(3) <-> '[1,2,4]'::vector(3)")
        )

    assert server_version_num // 10_000 == 17
    assert vector_version == "0.8.6"
    assert distance == pytest.approx(1.0)


def test_pgvector_infrastructure_preserves_m1_tables(
    postgres_engine: Engine,
) -> None:
    m1_tables = {
        "agent_runs",
        "evidences",
        "inventory_snapshots",
        "product_variants",
        "products",
        "tenants",
        "tool_calls",
        "users",
        "warehouses",
    }

    assert m1_tables <= set(inspect(postgres_engine).get_table_names())
