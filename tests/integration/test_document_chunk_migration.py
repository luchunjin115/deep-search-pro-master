from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Connection,
    Engine,
    delete,
    func,
    insert,
    inspect,
    literal_column,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentChunkSet,
    DocumentVersion,
    StoredFile,
)
from app.services.documents.chunking import ChunkingConfig, UnicodeMixedTokenCounter
from app.services.documents.chunking.contracts import (
    CHUNK_ARTIFACT_SCHEMA_VERSION,
    CHUNK_CONTENT_HASH_VERSION,
    canonical_sha256,
)


@pytest.fixture
def postgres_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    return settings


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


def alembic_config() -> Config:
    return Config("alembic.ini")


def chunk_set_values(
    *,
    tenant_id: UUID,
    document_id: UUID,
    version_id: UUID,
    chunk_set_id: UUID,
    chunk_count: int,
    table_chunk_count: int,
) -> dict[str, object]:
    counter = UnicodeMixedTokenCounter()
    config = ChunkingConfig()
    created_at = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    started_at = created_at + timedelta(seconds=1)
    return {
        "id": chunk_set_id,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "document_version_id": version_id,
        "artifact_schema_version": CHUNK_ARTIFACT_SCHEMA_VERSION,
        "content_hash_version": CHUNK_CONTENT_HASH_VERSION,
        "routed_schema_version": "m2-routed-parsed-document-v1",
        "canonical_schema_version": "m2-canonical-parsed-artifact-v1",
        "source_sha256": "a" * 64,
        "parsed_publication_sha256": "b" * 64,
        "selected_artifact_content_sha256": "c" * 64,
        "chunker_name": "structure_aware",
        "chunker_version": "m2-structure-aware-chunker-v1",
        "token_counter_name": counter.name,
        "token_counter_version": counter.version,
        "normalization_version": config.normalization_version,
        "config_json": config.model_dump(mode="json"),
        "config_sha256": canonical_sha256(config.model_dump(mode="json")),
        "status": "ready",
        "attempt_count": 1,
        "output_sha256": "d" * 64,
        "chunk_storage_key": (f"{tenant_id}/chunks/2026/08/{chunk_set_id}.json"),
        "chunk_count": chunk_count,
        "text_chunk_count": chunk_count - table_chunk_count,
        "table_chunk_count": table_chunk_count,
        "total_token_count": chunk_count * 10,
        "excluded_span_count": 0,
        "created_at": created_at,
        "started_at": started_at,
        "completed_at": started_at + timedelta(seconds=1),
    }


def chunk_values(
    *,
    tenant_id: UUID,
    document_id: UUID,
    version_id: UUID,
    chunk_set_id: UUID,
    chunk_id: str,
    chunk_index: int,
    kind: str = "text",
    retrieval_text: str = "alphaunique synthetic knowledge chunk",
    content_sha256: str = "e" * 64,
    embedding: object | None = None,
) -> dict[str, object]:
    table_json: dict[str, object] | None = None
    if kind == "table":
        table_json = {
            "source_kind": "worksheet",
            "sheet_name": "报价",
            "sheet_state": "visible",
            "cell_range": "A1:B2",
            "rows": [
                {
                    "source_row_number": 1,
                    "role": "header",
                    "repeated_as_context": False,
                    "cells": [
                        {"row_number": 1, "column_number": 1, "display_text": "型号"}
                    ],
                }
            ],
        }
    values: dict[str, object] = {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "document_version_id": version_id,
        "document_chunk_set_id": chunk_set_id,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "kind": kind,
        "body_text": retrieval_text,
        "retrieval_text": retrieval_text,
        "fts_text": retrieval_text,
        "token_count": 10,
        "content_sha256": content_sha256,
        "heading_path": ["合成知识库"],
        "page_numbers": [1],
        "source_block_ids": ["b000001"],
        "source_spans": [
            {
                "block_id": "b000001",
                "start_locator": {"page_number": 1},
                "end_locator": {"page_number": 1},
            }
        ],
        "bounding_boxes": [],
        "overlap_json": None,
        "table_json": table_json,
        "warnings": [],
    }
    if embedding is not None:
        values.update(
            embedding=embedding,
            embedding_model="synthetic/fixed-vector",
            embedding_version="m2-13-test-v1",
        )
    return values


def insert_document_graph(
    connection: Connection,
    *,
    tenant_id: UUID,
    owner_id: UUID,
    file_id: UUID,
    document_id: UUID,
    version_id: UUID,
    chunk_set_id: UUID,
    suffix: str,
    chunk_count: int,
    table_chunk_count: int = 0,
    create_tenant: bool = True,
) -> None:
    if create_tenant:
        connection.execute(insert(Tenant).values(id=tenant_id, name=f"Tenant {suffix}"))
    connection.execute(
        insert(User).values(
            id=owner_id,
            tenant_id=tenant_id,
            email=f"chunk-owner-{suffix}@example.com",
            display_name=f"Chunk Owner {suffix}",
            password_hash="$argon2id$synthetic-only-hash",
        )
    )
    connection.execute(
        insert(StoredFile).values(
            id=file_id,
            tenant_id=tenant_id,
            owner_user_id=owner_id,
            original_name=f"synthetic-{suffix}.pdf",
            storage_key=f"{tenant_id}/uploads/2026/08/{file_id}.pdf",
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
            owner_user_id=owner_id,
            title=f"合成Chunk文档{suffix}",
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
        )
    )
    connection.execute(
        insert(DocumentChunkSet).values(
            **chunk_set_values(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                chunk_count=chunk_count,
                table_chunk_count=table_chunk_count,
            )
        )
    )


def test_document_chunk_migration_down_up_down_up(
    postgres_settings: Settings,
) -> None:
    del postgres_settings
    config = alembic_config()

    try:
        command.downgrade(config, "20260831_0005")
        runtime = create_database_runtime(Settings())
        try:
            tables = set(inspect(runtime.engine).get_table_names())
            assert "document_chunks" not in tables
            assert "document_chunk_sets" in tables
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "head")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "document_chunks" in inspector.get_table_names()
            columns = {
                column["name"]: column
                for column in inspector.get_columns("document_chunks")
            }
            embedding_type = columns["embedding"]["type"]
            assert isinstance(embedding_type, Vector)
            assert embedding_type.dim == 1024
            assert columns["search_vector"]["computed"] is not None
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260831_0005")
        runtime = create_database_runtime(Settings())
        try:
            assert "document_chunks" not in inspect(runtime.engine).get_table_names()
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "head")
    finally:
        command.upgrade(config, "head")


def test_postgresql_enforces_chunk_identity_structure_fts_vector_and_cascades(
    postgres_engine: Engine,
) -> None:
    config = alembic_config()
    command.downgrade(config, "20260831_0006")
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    document_id = uuid4()
    other_document_id = uuid4()
    version_id = uuid4()
    other_version_id = uuid4()
    chunk_set_id = uuid4()
    other_chunk_set_id = uuid4()
    cross_tenant_document_id = uuid4()
    cross_tenant_version_id = uuid4()
    cross_tenant_chunk_set_id = uuid4()

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            insert_document_graph(
                connection,
                tenant_id=tenant_id,
                owner_id=uuid4(),
                file_id=uuid4(),
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                suffix="primary",
                chunk_count=3,
                table_chunk_count=1,
            )
            insert_document_graph(
                connection,
                tenant_id=tenant_id,
                owner_id=uuid4(),
                file_id=uuid4(),
                document_id=other_document_id,
                version_id=other_version_id,
                chunk_set_id=other_chunk_set_id,
                suffix="secondary",
                chunk_count=1,
                create_tenant=False,
            )
            insert_document_graph(
                connection,
                tenant_id=other_tenant_id,
                owner_id=uuid4(),
                file_id=uuid4(),
                document_id=cross_tenant_document_id,
                version_id=cross_tenant_version_id,
                chunk_set_id=cross_tenant_chunk_set_id,
                suffix="cross-tenant",
                chunk_count=1,
            )

            first_vector = [1.0, 0.0] + [0.0] * 1022
            second_vector = [0.8, 0.6] + [0.0] * 1022
            third_vector = [0.0, 1.0] + [0.0] * 1022
            connection.execute(
                insert(DocumentChunk),
                [
                    chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000001",
                        chunk_index=1,
                        retrieval_text="alphaunique 蘑菇灯清洁说明",
                        content_sha256="1" * 64,
                        embedding=first_vector,
                    ),
                    chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000002",
                        chunk_index=2,
                        kind="table",
                        retrieval_text="supplier matrix synthetic table",
                        content_sha256="2" * 64,
                        embedding=second_vector,
                    ),
                    chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000003",
                        chunk_index=3,
                        retrieval_text="distant vector sample",
                        content_sha256="3" * 64,
                        embedding=third_vector,
                    ),
                ],
            )
            connection.execute(
                insert(DocumentChunk).values(
                    **chunk_values(
                        tenant_id=tenant_id,
                        document_id=other_document_id,
                        version_id=other_version_id,
                        chunk_set_id=other_chunk_set_id,
                        chunk_id="c000001",
                        chunk_index=1,
                        retrieval_text="cascade sentinel",
                        content_sha256="4" * 64,
                    )
                )
            )

            rejected_rows = [
                chunk_values(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    version_id=version_id,
                    chunk_set_id=chunk_set_id,
                    chunk_id="c000001",
                    chunk_index=4,
                ),
                chunk_values(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    version_id=version_id,
                    chunk_set_id=chunk_set_id,
                    chunk_id="c000004",
                    chunk_index=1,
                ),
                chunk_values(
                    tenant_id=other_tenant_id,
                    document_id=document_id,
                    version_id=version_id,
                    chunk_set_id=chunk_set_id,
                    chunk_id="c000004",
                    chunk_index=4,
                ),
                chunk_values(
                    tenant_id=tenant_id,
                    document_id=other_document_id,
                    version_id=version_id,
                    chunk_set_id=chunk_set_id,
                    chunk_id="c000004",
                    chunk_index=4,
                ),
                chunk_values(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    version_id=other_version_id,
                    chunk_set_id=chunk_set_id,
                    chunk_id="c000004",
                    chunk_index=4,
                ),
                chunk_values(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    version_id=version_id,
                    chunk_set_id=other_chunk_set_id,
                    chunk_id="c000004",
                    chunk_index=4,
                ),
                {
                    **chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000004",
                        chunk_index=4,
                    ),
                    "content_sha256": "not-a-sha256",
                },
                {
                    **chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000004",
                        chunk_index=0,
                    ),
                },
                {
                    **chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000004",
                        chunk_index=4,
                    ),
                    "token_count": 0,
                },
                {
                    **chunk_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        chunk_id="c000004",
                        chunk_index=4,
                    ),
                    "kind": "table",
                    "table_json": None,
                },
            ]
            for case_number, values in enumerate(rejected_rows, start=1):
                try:
                    with connection.begin_nested():
                        connection.execute(insert(DocumentChunk).values(**values))
                except IntegrityError:
                    continue
                pytest.fail(f"invalid Chunk case {case_number} was accepted")

            invalid_dimension = chunk_values(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                chunk_id="c000004",
                chunk_index=4,
            )
            invalid_dimension.update(
                embedding=literal_column("'[1,2]'::vector"),
                embedding_model="synthetic/fixed-vector",
                embedding_version="m2-13-test-v1",
            )
            with pytest.raises(SQLAlchemyError), connection.begin_nested():
                connection.execute(insert(DocumentChunk).values(**invalid_dimension))

            fts_matches = connection.scalars(
                select(DocumentChunk.chunk_id)
                .where(DocumentChunk.document_chunk_set_id == chunk_set_id)
                .where(
                    DocumentChunk.search_vector.op("@@")(
                        func.plainto_tsquery("simple", "alphaunique")
                    )
                )
            ).all()
            assert fts_matches == ["c000001"]
            no_embedding = connection.execute(
                select(
                    DocumentChunk.embedding,
                    DocumentChunk.embedding_model,
                    DocumentChunk.embedding_version,
                ).where(DocumentChunk.document_chunk_set_id == other_chunk_set_id)
            ).one()
            assert no_embedding == (None, None, None)

            distance = DocumentChunk.embedding.cosine_distance(first_vector)
            vector_ranking = connection.execute(
                select(DocumentChunk.chunk_id, distance.label("distance"))
                .where(DocumentChunk.document_chunk_set_id == chunk_set_id)
                .order_by(distance, DocumentChunk.chunk_index)
            ).all()
            assert [row.chunk_id for row in vector_ranking] == [
                "c000001",
                "c000002",
                "c000003",
            ]
            assert vector_ranking[0].distance == pytest.approx(0.0)
            assert vector_ranking[1].distance == pytest.approx(0.2)
            assert vector_ranking[2].distance == pytest.approx(1.0)

            index_rows = connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'document_chunks'"
                )
            ).all()
            indexes = {row.indexname: row.indexdef for row in index_rows}
            assert (
                "USING gin (search_vector)"
                in indexes["ix_document_chunks_search_vector_gin"]
            )
            assert (
                "USING hnsw (embedding vector_cosine_ops)"
                in indexes["ix_document_chunks_embedding_hnsw_cosine"]
            )

            connection.execute(
                delete(DocumentChunkSet).where(DocumentChunkSet.id == chunk_set_id)
            )
            assert (
                connection.scalar(select(func.count()).select_from(DocumentChunk)) == 1
            )

            connection.execute(
                delete(DocumentVersion).where(DocumentVersion.id == other_version_id)
            )
            assert (
                connection.scalar(select(func.count()).select_from(DocumentChunk)) == 0
            )
            assert (
                connection.scalar(
                    select(DocumentChunkSet.id).where(
                        DocumentChunkSet.id == other_chunk_set_id
                    )
                )
                is None
            )
        finally:
            transaction.rollback()
            command.upgrade(config, "head")
