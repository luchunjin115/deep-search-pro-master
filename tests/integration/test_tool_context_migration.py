from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, delete, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.models.runtime import (
    AgentRun,
    ContextArtifact,
    Evidence,
    Thread,
    ToolCall,
    ToolContextLink,
)
from tests.integration import test_context_evidence_migration as context_support


@pytest.fixture
def postgres_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    return settings


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


def alembic_config() -> Config:
    return Config("alembic.ini")


def _tool_context_values(
    *,
    tenant_id: UUID,
    run_id: UUID,
    tool_call_id: UUID,
    context_id: UUID,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "agent_run_id": run_id,
        "tool_call_id": tool_call_id,
        "context_artifact_id": context_id,
    }


def _insert_knowledge_trace(
    connection: Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    suffix: str,
) -> tuple[UUID, UUID]:
    run_id, tool_call_id = context_support.insert_runtime_trace(
        connection,
        tenant_id=tenant_id,
        user_id=user_id,
        suffix=suffix,
    )
    connection.execute(
        update(ToolCall)
        .where(ToolCall.id == tool_call_id)
        .values(tool_name="search_knowledge", arguments_summary={"query": suffix})
    )
    return run_id, tool_call_id


def _cleanup_tenant(connection: Connection, tenant_id: UUID) -> None:
    for model in (
        ToolContextLink,
        Evidence,
        ContextArtifact,
        DocumentChunk,
        DocumentIndexSet,
        DocumentChunkSet,
        DocumentVersion,
        Document,
        StoredFile,
        ToolCall,
        AgentRun,
        Thread,
        User,
    ):
        connection.execute(delete(model).where(model.tenant_id == tenant_id))
    connection.execute(delete(Tenant).where(Tenant.id == tenant_id))


def test_tool_context_migration_round_trip_and_metadata(
    postgres_settings: Settings,
) -> None:
    del postgres_settings
    config = alembic_config()

    try:
        command.downgrade(config, "20260901_0009")
        runtime = create_database_runtime(Settings())
        try:
            assert "tool_context_links" not in inspect(runtime.engine).get_table_names()
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "head")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "tool_context_links" in inspector.get_table_names()
            assert {
                "id",
                "tenant_id",
                "agent_run_id",
                "tool_call_id",
                "context_artifact_id",
                "created_at",
            } == {
                column["name"] for column in inspector.get_columns("tool_context_links")
            }
            assert "tool_context_links" in Base.metadata.tables
            model_constraints = {
                constraint.name
                for constraint in Base.metadata.tables["tool_context_links"].constraints
            }
            database_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("tool_context_links")
            }
            assert "uq_tool_context_links_tenant_tool_call" in model_constraints
            assert "uq_tool_context_links_tenant_tool_call" in database_constraints
            source_shape = next(
                item["sqltext"]
                for item in inspector.get_check_constraints("evidences")
                if item["name"] == "ck_evidences_source_shape"
            )
            assert "agent_run_id IS NULL" in source_shape
            assert "tool_call_id IS NULL" in source_shape
        finally:
            runtime.engine.dispose()
    finally:
        command.upgrade(config, "head")


def test_upgrade_backfills_legacy_document_runtime_and_protects_downgrade(
    postgres_engine: Engine,
) -> None:
    config = alembic_config()
    command.downgrade(config, "20260901_0009")
    tenant_id = uuid4()
    user_id = uuid4()
    context_id: UUID
    run_id: UUID
    tool_call_id: UUID

    try:
        with postgres_engine.begin() as connection:
            context_support.insert_identity(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="tool-link-backfill",
            )
            run_id, tool_call_id = _insert_knowledge_trace(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="tool-link-backfill",
            )
            provenance = context_support.insert_document_graph(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="tool-link-backfill",
            )
            context_values = context_support.context_values(
                tenant_id=tenant_id,
                user_id=user_id,
            )
            context_id = context_values["id"]  # type: ignore[assignment]
            connection.execute(insert(ContextArtifact).values(**context_values))
            evidence_values = context_support.document_evidence_values(
                tenant_id=tenant_id,
                context_id=context_id,
                provenance=provenance,
            )
            connection.execute(
                insert(Evidence).values(
                    **(
                        evidence_values
                        | {
                            "agent_run_id": run_id,
                            "tool_call_id": tool_call_id,
                        }
                    )
                )
            )

        command.upgrade(config, "head")
        with postgres_engine.connect() as connection:
            link = connection.execute(
                select(
                    ToolContextLink.tenant_id,
                    ToolContextLink.agent_run_id,
                    ToolContextLink.tool_call_id,
                    ToolContextLink.context_artifact_id,
                ).where(ToolContextLink.tenant_id == tenant_id)
            ).one()
            evidence_runtime = connection.execute(
                select(Evidence.agent_run_id, Evidence.tool_call_id).where(
                    Evidence.tenant_id == tenant_id
                )
            ).one()
        assert link == (tenant_id, run_id, tool_call_id, context_id)
        assert evidence_runtime == (None, None)

        with pytest.raises(RuntimeError, match="Tool-Context"):
            command.downgrade(config, "20260901_0009")
    finally:
        command.upgrade(config, "head")
        with postgres_engine.begin() as connection:
            _cleanup_tenant(connection, tenant_id)


def test_database_enforces_tool_context_identity_and_m1_compatibility(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    user_id = uuid4()
    other_tenant_id = uuid4()
    other_user_id = uuid4()

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            context_support.insert_identity(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="tool-link-primary",
            )
            context_support.insert_identity(
                connection,
                tenant_id=other_tenant_id,
                user_id=other_user_id,
                suffix="tool-link-other",
            )
            first_run, first_tool = _insert_knowledge_trace(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="first",
            )
            second_run, second_tool = _insert_knowledge_trace(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="second",
            )
            third_run, third_tool = _insert_knowledge_trace(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="third",
            )
            other_run, other_tool = _insert_knowledge_trace(
                connection,
                tenant_id=other_tenant_id,
                user_id=other_user_id,
                suffix="other",
            )
            del other_run, other_tool

            first_context = context_support.context_values(
                tenant_id=tenant_id,
                user_id=user_id,
                identity_character="6",
            )
            second_context = context_support.context_values(
                tenant_id=tenant_id,
                user_id=user_id,
                identity_character="7",
            )
            other_context = context_support.context_values(
                tenant_id=other_tenant_id,
                user_id=other_user_id,
                identity_character="8",
            )
            connection.execute(
                insert(ContextArtifact).values(
                    [first_context, second_context, other_context]
                )
            )
            first_context_id = first_context["id"]
            second_context_id = second_context["id"]
            other_context_id = other_context["id"]

            connection.execute(
                insert(ToolContextLink).values(
                    **_tool_context_values(
                        tenant_id=tenant_id,
                        run_id=first_run,
                        tool_call_id=first_tool,
                        context_id=first_context_id,  # type: ignore[arg-type]
                    )
                )
            )
            connection.execute(
                insert(ToolContextLink).values(
                    **_tool_context_values(
                        tenant_id=tenant_id,
                        run_id=second_run,
                        tool_call_id=second_tool,
                        context_id=first_context_id,  # type: ignore[arg-type]
                    )
                )
            )
            assert (
                connection.scalar(
                    select(ToolContextLink)
                    .where(ToolContextLink.context_artifact_id == first_context_id)
                    .with_only_columns(ToolContextLink.id)
                    .order_by(ToolContextLink.id)
                    .limit(1)
                )
                is not None
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(ToolContextLink).values(
                        **_tool_context_values(
                            tenant_id=tenant_id,
                            run_id=first_run,
                            tool_call_id=first_tool,
                            context_id=second_context_id,  # type: ignore[arg-type]
                        )
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(ToolContextLink).values(
                        **_tool_context_values(
                            tenant_id=tenant_id,
                            run_id=second_run,
                            tool_call_id=third_tool,
                            context_id=second_context_id,  # type: ignore[arg-type]
                        )
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(ToolContextLink).values(
                        **_tool_context_values(
                            tenant_id=tenant_id,
                            run_id=third_run,
                            tool_call_id=third_tool,
                            context_id=other_context_id,  # type: ignore[arg-type]
                        )
                    )
                )

            provenance = context_support.insert_document_graph(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="tool-link-shape",
            )
            document_values = context_support.document_evidence_values(
                tenant_id=tenant_id,
                context_id=first_context_id,  # type: ignore[arg-type]
                provenance=provenance,
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **(
                            document_values
                            | {
                                "agent_run_id": third_run,
                                "tool_call_id": third_tool,
                            }
                        )
                    )
                )

            connection.execute(
                insert(Evidence).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    agent_run_id=third_run,
                    tool_call_id=third_tool,
                    source_type="database",
                    source_name="synthetic_inventory",
                    source_locator="inventory_snapshots/m2-19-2",
                    title="M1库存证据",
                    excerpt="M1数据库Evidence继续直接绑定ToolCall",
                    query_summary={"sku": "LR-TL-MUSH-OR01"},
                    structured_data={"available": 125},
                    observed_at=datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
                    confidence=Decimal("1.000"),
                    access_scope={"tenant_id": str(tenant_id), "markets": ["DE"]},
                )
            )
        finally:
            transaction.rollback()
