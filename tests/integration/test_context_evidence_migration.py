from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, delete, insert, inspect, select
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
)
from app.services.documents.chunking import ChunkingConfig, UnicodeMixedTokenCounter
from app.services.documents.chunking.contracts import (
    CHUNK_ARTIFACT_SCHEMA_VERSION,
    CHUNK_CONTENT_HASH_VERSION,
    canonical_sha256,
)


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


def insert_identity(
    connection: Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    suffix: str,
) -> None:
    connection.execute(insert(Tenant).values(id=tenant_id, name=f"Context {suffix}"))
    connection.execute(
        insert(User).values(
            id=user_id,
            tenant_id=tenant_id,
            email=f"context-{suffix}@example.com",
            display_name=f"Context {suffix}",
            password_hash="$argon2id$synthetic-only-hash",
        )
    )


def insert_runtime_trace(
    connection: Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    suffix: str,
) -> tuple[UUID, UUID]:
    thread_id = uuid4()
    run_id = uuid4()
    tool_call_id = uuid4()
    started_at = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    connection.execute(
        insert(Thread).values(
            id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title=f"Context migration {suffix}",
        )
    )
    connection.execute(
        insert(AgentRun).values(
            id=run_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            trace_id=uuid4(),
            route="inventory_query",
            status="completed",
            model_call_count=1,
            tool_call_count=1,
            started_at=started_at,
            finished_at=started_at + timedelta(milliseconds=50),
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
            arguments_summary={"sku": "LR-TL-MUSH-OR01"},
            permission_result="allowed",
            status="success",
        )
    )
    return run_id, tool_call_id


def insert_document_graph(
    connection: Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    suffix: str,
) -> dict[str, UUID]:
    file_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    index_set_id = uuid4()
    chunk_row_id = uuid4()
    created_at = datetime(2026, 9, 1, 8, 5, tzinfo=UTC)
    counter = UnicodeMixedTokenCounter()
    config = ChunkingConfig()

    connection.execute(
        insert(StoredFile).values(
            id=file_id,
            tenant_id=tenant_id,
            owner_user_id=user_id,
            original_name=f"context-{suffix}.pdf",
            storage_key=f"{tenant_id}/uploads/2026/09/{file_id}.pdf",
            extension=".pdf",
            mime_type="application/pdf",
            size_bytes=128,
            sha256="a" * 64,
            category="uploads",
        )
    )
    connection.execute(
        insert(Document).values(
            id=document_id,
            tenant_id=tenant_id,
            owner_user_id=user_id,
            title=f"合成Context文档{suffix}",
            document_type="product_manual",
            access_level="private",
        )
    )
    connection.execute(
        insert(DocumentVersion).values(
            id=version_id,
            tenant_id=tenant_id,
            document_id=document_id,
            file_id=file_id,
            version_no=1,
            content_hash="a" * 64,
            parser_name="native_pdf",
            parser_version="m2-native-pdf-v1",
            parsed_storage_key=f"{tenant_id}/parsed/2026/09/{version_id}.json",
            parse_status="ready",
            index_status="pending",
        )
    )
    connection.execute(
        insert(DocumentChunkSet).values(
            id=chunk_set_id,
            tenant_id=tenant_id,
            document_id=document_id,
            document_version_id=version_id,
            artifact_schema_version=CHUNK_ARTIFACT_SCHEMA_VERSION,
            content_hash_version=CHUNK_CONTENT_HASH_VERSION,
            routed_schema_version="m2-routed-parsed-document-v1",
            canonical_schema_version="m2-canonical-parsed-artifact-v1",
            source_sha256="a" * 64,
            parsed_publication_sha256="b" * 64,
            selected_artifact_content_sha256="c" * 64,
            chunker_name="structure_aware",
            chunker_version="m2-structure-aware-chunker-v1",
            token_counter_name=counter.name,
            token_counter_version=counter.version,
            normalization_version=config.normalization_version,
            config_json=config.model_dump(mode="json"),
            config_sha256=canonical_sha256(config.model_dump(mode="json")),
            status="ready",
            attempt_count=1,
            output_sha256="d" * 64,
            chunk_storage_key=f"{tenant_id}/chunks/2026/09/{chunk_set_id}.json",
            chunk_count=1,
            text_chunk_count=1,
            table_chunk_count=0,
            total_token_count=10,
            excluded_span_count=0,
            created_at=created_at,
            started_at=created_at + timedelta(seconds=1),
            completed_at=created_at + timedelta(seconds=2),
        )
    )
    connection.execute(
        insert(DocumentIndexSet).values(
            id=index_set_id,
            tenant_id=tenant_id,
            document_id=document_id,
            document_version_id=version_id,
            document_chunk_set_id=chunk_set_id,
            index_schema_version="m2-document-index-set-v1",
            embedding_identity_json={
                "contract_version": "m2-embedding-provider-v1",
                "provider": "fake",
            },
            embedding_identity_sha256="1" * 64,
            embedding_model="fake/m2-deterministic",
            embedding_version="m2-fake-v1",
            embedding_purpose="document",
            fts_builder_version="m2-fts-jieba-search-v1",
            status="ready",
            attempt_count=1,
            chunk_count=1,
            text_chunk_count=1,
            table_chunk_count=0,
            total_token_count=10,
            created_at=created_at,
            started_at=created_at + timedelta(seconds=1),
            completed_at=created_at + timedelta(seconds=2),
        )
    )
    connection.execute(
        insert(DocumentChunk).values(
            id=chunk_row_id,
            tenant_id=tenant_id,
            document_id=document_id,
            document_version_id=version_id,
            document_chunk_set_id=chunk_set_id,
            document_index_set_id=index_set_id,
            chunk_id="c000001",
            chunk_index=1,
            kind="text",
            body_text="清洁蘑菇灯前请先断开电源。",
            retrieval_text="蘑菇灯手册\n清洁蘑菇灯前请先断开电源。",
            fts_text="蘑菇灯 手册 清洁 断开 电源",
            token_count=10,
            content_sha256="e" * 64,
            heading_path=["维护", "清洁"],
            page_numbers=[2],
            source_block_ids=["b000001"],
            source_spans=[
                {
                    "block_id": "b000001",
                    "start_locator": {"page_number": 2},
                    "end_locator": {"page_number": 2},
                }
            ],
            bounding_boxes=[],
            overlap_json=None,
            table_json=None,
            warnings=[],
            embedding=[1.0] + [0.0] * 1023,
            embedding_model="fake/m2-deterministic",
            embedding_version="m2-fake-v1",
            embedding_cache_key=f"sha256:{'f' * 64}",
        )
    )
    return {
        "file_id": file_id,
        "document_id": document_id,
        "version_id": version_id,
        "chunk_set_id": chunk_set_id,
        "index_set_id": index_set_id,
        "chunk_row_id": chunk_row_id,
    }


def context_values(
    *, tenant_id: UUID, user_id: UUID, identity_character: str = "6"
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "requested_by_user_id": user_id,
        "contract_version": "m2-context-bundle-v1",
        "token_counter_version": "m2-unicode-token-counter-v1",
        "query_sha256": "2" * 64,
        "retrieval_snapshot_json": {"reranked_chunk_ids": []},
        "retrieval_snapshot_sha256": "3" * 64,
        "config_json": {"max_tokens": 4000, "max_segments": 12},
        "config_sha256": "4" * 64,
        "context_sha256": "5" * 64,
        "identity_sha256": identity_character * 64,
        "max_tokens": 4000,
        "total_tokens": 10,
        "segment_count": 1,
    }


def document_evidence_values(
    *,
    tenant_id: UUID,
    context_id: UUID,
    provenance: dict[str, UUID],
    source_type: str = "user_file",
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "agent_run_id": None,
        "tool_call_id": None,
        "evidence_schema_version": "m2-document-evidence-v1",
        "source_type": source_type,
        "source_name": "document_chunk",
        "source_locator": None,
        "source_locator_json": {"source_type": "pdf", "page_number": 2},
        "title": "合成Context文档",
        "excerpt": "清洁蘑菇灯前请先断开电源。",
        "query_summary": None,
        "structured_data": None,
        "observed_at": datetime(2026, 9, 1, 8, 10, tzinfo=UTC),
        "confidence": None,
        "trust_level": "document_snapshot",
        "access_scope": None,
        "synthetic_data": True,
        "context_artifact_id": context_id,
        "citation_ordinal": 1,
        "file_id": provenance["file_id"],
        "document_id": provenance["document_id"],
        "document_version_id": provenance["version_id"],
        "document_chunk_set_id": provenance["chunk_set_id"],
        "document_index_set_id": provenance["index_set_id"],
        "document_chunk_id": provenance["chunk_row_id"],
        "source_content_sha256": "e" * 64,
        "context_text_sha256": "7" * 64,
    }


def test_context_evidence_migration_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()

    try:
        command.downgrade(config, "20260831_0008")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "context_artifacts" not in inspector.get_table_names()
            assert "context_artifact_id" not in {
                column["name"] for column in inspector.get_columns("evidences")
            }
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "head")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "context_artifacts" in inspector.get_table_names()
            evidence_columns = {
                column["name"]: column for column in inspector.get_columns("evidences")
            }
            assert {
                "evidence_schema_version",
                "source_locator_json",
                "context_artifact_id",
                "citation_ordinal",
                "file_id",
                "document_id",
                "document_version_id",
                "document_chunk_set_id",
                "document_index_set_id",
                "document_chunk_id",
                "source_content_sha256",
                "context_text_sha256",
            } <= evidence_columns.keys()
            assert evidence_columns["agent_run_id"]["nullable"] is True
            assert evidence_columns["tool_call_id"]["nullable"] is True
            assert evidence_columns["source_locator"]["nullable"] is True
        finally:
            runtime.engine.dispose()
    finally:
        command.upgrade(config, "head")


def test_database_preserves_m1_and_enforces_document_provenance(
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
            insert_identity(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="primary",
            )
            insert_identity(
                connection,
                tenant_id=other_tenant_id,
                user_id=other_user_id,
                suffix="other",
            )
            run_id, tool_call_id = insert_runtime_trace(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="database",
            )
            database_evidence_id = uuid4()
            connection.execute(
                insert(Evidence).values(
                    id=database_evidence_id,
                    tenant_id=tenant_id,
                    agent_run_id=run_id,
                    tool_call_id=tool_call_id,
                    source_type="database",
                    source_name="synthetic_inventory",
                    source_locator="inventory_snapshots/demo-row-id",
                    title="M1库存证据",
                    excerpt="M1旧写入形状保持可用",
                    query_summary={"sku": "LR-TL-MUSH-OR01"},
                    structured_data={"available": 125},
                    observed_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
                    confidence=Decimal("1.000"),
                    access_scope={"tenant_id": str(tenant_id), "markets": ["DE"]},
                )
            )

            provenance = insert_document_graph(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="primary",
            )
            context = context_values(tenant_id=tenant_id, user_id=user_id)
            connection.execute(insert(ContextArtifact).values(**context))
            valid_values = document_evidence_values(
                tenant_id=tenant_id,
                context_id=context["id"],  # type: ignore[arg-type]
                provenance=provenance,
            )
            connection.execute(insert(Evidence).values(**valid_values))

            stored_schema_version, stored_source_type = connection.execute(
                select(Evidence.evidence_schema_version, Evidence.source_type).where(
                    Evidence.id == database_evidence_id
                )
            ).one()
            assert stored_schema_version == "m1-database-evidence-v1"
            assert stored_source_type == "database"

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **{
                            **valid_values,
                            "id": uuid4(),
                            "citation_ordinal": 2,
                            "document_chunk_id": uuid4(),
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **{
                            **valid_values,
                            "id": uuid4(),
                            "tenant_id": other_tenant_id,
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **{
                            **valid_values,
                            "id": uuid4(),
                            "document_id": None,
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **{
                            **valid_values,
                            "id": uuid4(),
                            "agent_run_id": run_id,
                            "tool_call_id": None,
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **{
                            **valid_values,
                            "id": uuid4(),
                            "citation_ordinal": 2,
                            "source_locator_json": ["page", 2],
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Evidence).values(
                        **{
                            **valid_values,
                            "id": uuid4(),
                        }
                    )
                )
        finally:
            transaction.rollback()


def test_downgrade_refuses_to_discard_context_artifacts(
    postgres_engine: Engine,
) -> None:
    config = alembic_config()
    command.upgrade(config, "head")
    tenant_id = uuid4()
    user_id = uuid4()
    context_id: UUID

    try:
        with postgres_engine.begin() as connection:
            insert_identity(
                connection,
                tenant_id=tenant_id,
                user_id=user_id,
                suffix="downgrade-guard",
            )
            values = context_values(
                tenant_id=tenant_id,
                user_id=user_id,
                identity_character="8",
            )
            context_id = values["id"]  # type: ignore[assignment]
            connection.execute(insert(ContextArtifact).values(**values))

        with pytest.raises(RuntimeError, match="Context/Evidence"):
            command.downgrade(config, "20260831_0008")

        with postgres_engine.begin() as connection:
            connection.execute(
                delete(ContextArtifact).where(ContextArtifact.id == context_id)
            )
            connection.execute(delete(User).where(User.id == user_id))
            connection.execute(delete(Tenant).where(Tenant.id == tenant_id))
    finally:
        command.upgrade(config, "head")


def test_model_metadata_contains_context_and_extended_evidence(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")

    assert "context_artifacts" in Base.metadata.tables
    assert "context_artifact_id" in Base.metadata.tables["evidences"].columns
    assert "context_artifacts" in inspect(postgres_engine).get_table_names()
