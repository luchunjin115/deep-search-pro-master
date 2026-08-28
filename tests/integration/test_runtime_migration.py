from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, insert, inspect
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_runtime
from app.models.identity import Tenant, User
from app.models.runtime import AgentRun, Evidence, Message, Thread, ToolCall


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


def test_runtime_migration_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()
    runtime_tables = {"agent_runs", "evidences", "messages", "threads", "tool_calls"}
    prior_tables = {
        "inventory_snapshots",
        "product_specs",
        "product_variants",
        "products",
        "roles",
        "tenants",
        "user_roles",
        "users",
        "warehouses",
    }

    try:
        command.downgrade(config, "20260828_0002")
        runtime = create_database_runtime(Settings())
        try:
            table_names = set(inspect(runtime.engine).get_table_names())
            assert runtime_tables.isdisjoint(table_names)
            assert prior_tables <= table_names
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260828_0003")
        runtime = create_database_runtime(Settings())
        try:
            assert runtime_tables <= set(inspect(runtime.engine).get_table_names())
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260828_0002")
        command.upgrade(config, "20260828_0003")
    finally:
        command.upgrade(config, "head")


def test_database_rejects_invalid_runtime_evidence_rows(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    user_id = uuid4()
    other_user_id = uuid4()
    thread_id = uuid4()
    run_id = uuid4()
    other_run_id = uuid4()
    tool_call_id = uuid4()
    other_tool_call_id = uuid4()
    trace_id = uuid4()
    started_at = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                insert(Tenant),
                [
                    {"id": tenant_id, "name": "M1 runtime tenant"},
                    {"id": other_tenant_id, "name": "M1 runtime other tenant"},
                ],
            )
            connection.execute(
                insert(User),
                [
                    {
                        "id": user_id,
                        "tenant_id": tenant_id,
                        "email": "runtime@example.com",
                        "display_name": "Runtime User",
                        "password_hash": "$argon2id$demo-only-hash",
                    },
                    {
                        "id": other_user_id,
                        "tenant_id": other_tenant_id,
                        "email": "other-runtime@example.com",
                        "display_name": "Other Runtime User",
                        "password_hash": "$argon2id$demo-only-hash",
                    },
                ],
            )
            connection.execute(
                insert(Thread).values(
                    id=thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    title="德国仓库存查询",
                )
            )
            connection.execute(
                insert(Message).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    role="user",
                    content_summary="德国仓蘑菇灯还有多少可售库存？",
                )
            )
            connection.execute(
                insert(AgentRun).values(
                    id=run_id,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    route="inventory_query",
                    status="completed",
                    model_call_count=1,
                    tool_call_count=1,
                    duration_ms=83,
                    started_at=started_at,
                    finished_at=started_at + timedelta(milliseconds=83),
                )
            )
            connection.execute(
                insert(ToolCall).values(
                    id=tool_call_id,
                    tenant_id=tenant_id,
                    agent_run_id=run_id,
                    sequence_no=1,
                    tool_name="search_inventory",
                    tool_version="1.0.0",
                    arguments_summary={"sku": "LR-TL-MUSH-OR01", "market": "DE"},
                    permission_result="allowed",
                    status="success",
                    duration_ms=42,
                )
            )
            connection.execute(
                insert(Evidence).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    agent_run_id=run_id,
                    tool_call_id=tool_call_id,
                    source_type="database",
                    source_name="synthetic_inventory",
                    source_locator="inventory_snapshots/demo-row-id",
                    title="德国仓蘑菇灯库存快照",
                    excerpt="可售库存依据原始数量计算",
                    query_summary={"sku": "LR-TL-MUSH-OR01", "market": "DE"},
                    structured_data={"on_hand": 150, "reserved": 20, "unsellable": 5},
                    observed_at=started_at,
                    confidence=Decimal("1.000"),
                    access_scope={"tenant_id": str(tenant_id), "markets": ["DE"]},
                )
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Thread).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        user_id=other_user_id,
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Message).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        role="tool",
                        content_summary="raw tool payload",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(AgentRun).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        thread_id=thread_id,
                        user_id=user_id,
                        trace_id=trace_id,
                        route="inventory_query",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(ToolCall).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        agent_run_id=run_id,
                        sequence_no=2,
                        tool_name="search_inventory",
                        tool_version="1.0.0",
                        arguments_summary=["raw", "arguments"],
                        permission_result="allowed",
                        status="success",
                    )
                )

            connection.execute(
                insert(AgentRun).values(
                    id=other_run_id,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    trace_id=uuid4(),
                    route="product_spec",
                )
            )
            connection.execute(
                insert(ToolCall).values(
                    id=other_tool_call_id,
                    tenant_id=tenant_id,
                    agent_run_id=other_run_id,
                    sequence_no=1,
                    tool_name="get_product_spec",
                    tool_version="1.0.0",
                    arguments_summary={"product_query": "蘑菇灯"},
                    permission_result="allowed",
                    status="success",
                )
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        agent_run_id=run_id,
                        tool_call_id=other_tool_call_id,
                        source_type="database",
                        source_name="synthetic_product_catalog",
                        source_locator="product_specs/demo-row-id",
                        title="串错运行的证据",
                        excerpt="该记录应被复合外键拒绝",
                        query_summary={},
                        structured_data={},
                        observed_at=started_at,
                        access_scope={"tenant_id": str(tenant_id)},
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        agent_run_id=run_id,
                        tool_call_id=tool_call_id,
                        source_type="web",
                        source_name="synthetic_inventory",
                        source_locator="https://example.invalid",
                        title="M1不允许的网页证据",
                        excerpt="M1 Evidence只能来自数据库",
                        query_summary={},
                        structured_data={},
                        observed_at=started_at,
                        access_scope={"tenant_id": str(tenant_id)},
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        agent_run_id=run_id,
                        tool_call_id=tool_call_id,
                        source_type="database",
                        source_name="synthetic_inventory",
                        source_locator="inventory_snapshots/demo-row-id",
                        title="非法访问范围",
                        excerpt="access_scope必须是JSON对象",
                        query_summary={},
                        structured_data={},
                        observed_at=started_at,
                        access_scope=["DE"],
                    )
                )
        finally:
            transaction.rollback()


def test_model_metadata_contains_applied_runtime_tables(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    runtime_tables = {"agent_runs", "evidences", "messages", "threads", "tool_calls"}

    assert runtime_tables <= set(Base.metadata.tables)
    assert runtime_tables <= set(inspect(postgres_engine).get_table_names())
