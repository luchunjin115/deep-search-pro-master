from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, delete, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
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


def insert_document_graph(
    connection: Connection,
    *,
    tenant_id: UUID,
    owner_id: UUID,
    file_id: UUID,
    document_id: UUID,
    version_id: UUID,
    chunk_set_id: UUID,
) -> None:
    counter = UnicodeMixedTokenCounter()
    config = ChunkingConfig()
    created_at = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    connection.execute(insert(Tenant).values(id=tenant_id, name="Index Set tenant"))
    connection.execute(
        insert(User).values(
            id=owner_id,
            tenant_id=tenant_id,
            email=f"index-owner-{tenant_id}@example.com",
            display_name="Index Set Owner",
            password_hash="$argon2id$synthetic-only-hash",
        )
    )
    connection.execute(
        insert(StoredFile).values(
            id=file_id,
            tenant_id=tenant_id,
            owner_user_id=owner_id,
            original_name="synthetic-index.pdf",
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
            title="合成索引文档",
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
            parsed_storage_key=(f"{tenant_id}/parsed/2026/08/{version_id}.json"),
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
            chunk_storage_key=(f"{tenant_id}/chunks/2026/08/{chunk_set_id}.json"),
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


def index_set_values(
    *,
    index_set_id: UUID,
    tenant_id: UUID,
    document_id: UUID,
    version_id: UUID,
    chunk_set_id: UUID,
    identity_character: str,
    status: str = "pending",
) -> dict[str, object]:
    values: dict[str, object] = {
        "id": index_set_id,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "document_version_id": version_id,
        "document_chunk_set_id": chunk_set_id,
        "index_schema_version": "m2-document-index-set-v1",
        "embedding_identity_json": {
            "contract_version": "m2-embedding-provider-v1",
            "provider": "fake",
            "model_id": "fake/m2-deterministic",
            "revision": "m2-fake-v1",
            "pooling": "sha256-shake-v1",
            "max_length": 8192,
            "normalize": True,
            "precision": "float32",
            "dimensions": 1024,
        },
        "embedding_identity_sha256": identity_character * 64,
        "embedding_model": "fake/m2-deterministic",
        "embedding_version": "m2-fake-v1",
        "embedding_purpose": "document",
        "fts_builder_version": "m2-fts-raw-retrieval-v1",
        "status": status,
    }
    if status in {"indexing", "ready", "failed"}:
        created_at = datetime(2026, 8, 31, 12, 5, tzinfo=UTC)
        values.update(
            attempt_count=1,
            created_at=created_at,
            started_at=created_at + timedelta(seconds=1),
        )
        if status in {"ready", "failed"}:
            values["completed_at"] = created_at + timedelta(seconds=2)
        if status == "ready":
            values.update(
                chunk_count=1,
                text_chunk_count=1,
                table_chunk_count=0,
                total_token_count=10,
            )
        if status == "failed":
            values["error_message"] = "safe synthetic failure"
    return values


def chunk_values(
    *,
    index_set_id: UUID,
    tenant_id: UUID,
    document_id: UUID,
    version_id: UUID,
    chunk_set_id: UUID,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "document_version_id": version_id,
        "document_chunk_set_id": chunk_set_id,
        "document_index_set_id": index_set_id,
        "chunk_id": "c000001",
        "chunk_index": 1,
        "kind": "text",
        "body_text": "synthetic index chunk",
        "retrieval_text": "合成索引文档\nsynthetic index chunk",
        "fts_text": "合成索引文档\nsynthetic index chunk",
        "token_count": 10,
        "content_sha256": "e" * 64,
        "heading_path": ["合成索引文档"],
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
        "table_json": None,
        "warnings": [],
        "embedding": [1.0] + [0.0] * 1023,
        "embedding_model": "fake/m2-deterministic",
        "embedding_version": "m2-fake-v1",
        "embedding_cache_key": f"sha256:{'f' * 64}",
    }


def test_index_set_migration_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()

    try:
        command.downgrade(config, "20260831_0006")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "document_index_sets" not in inspector.get_table_names()
            assert "active_index_set_id" not in {
                column["name"] for column in inspector.get_columns("document_versions")
            }
            assert "document_index_set_id" not in {
                column["name"] for column in inspector.get_columns("document_chunks")
            }
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "head")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "document_index_sets" in inspector.get_table_names()
            assert {
                "active_index_set_id",
            } <= {
                column["name"] for column in inspector.get_columns("document_versions")
            }
            chunk_columns = {
                column["name"]: column
                for column in inspector.get_columns("document_chunks")
            }
            assert {
                "document_index_set_id",
                "embedding_cache_key",
            } <= chunk_columns.keys()
            assert chunk_columns["document_index_set_id"]["nullable"] is False
            assert chunk_columns["embedding_cache_key"]["nullable"] is False
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260831_0006")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "document_index_sets" not in inspector.get_table_names()
            assert "active_index_set_id" not in {
                column["name"] for column in inspector.get_columns("document_versions")
            }
            assert "document_index_set_id" not in {
                column["name"] for column in inspector.get_columns("document_chunks")
            }
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "head")
    finally:
        command.upgrade(config, "head")


def test_database_enforces_index_identity_status_and_active_ready_pointer(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    owner_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    ready_index_id = uuid4()
    pending_index_id = uuid4()

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            insert_document_graph(
                connection,
                tenant_id=tenant_id,
                owner_id=owner_id,
                file_id=file_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            ready_values = index_set_values(
                index_set_id=ready_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                identity_character="1",
                status="ready",
            )
            connection.execute(insert(DocumentIndexSet).values(**ready_values))

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentIndexSet).values(
                        **{
                            **ready_values,
                            "id": uuid4(),
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                invalid_ready = index_set_values(
                    index_set_id=uuid4(),
                    tenant_id=tenant_id,
                    document_id=document_id,
                    version_id=version_id,
                    chunk_set_id=chunk_set_id,
                    identity_character="2",
                )
                connection.execute(
                    insert(DocumentIndexSet).values(
                        **{
                            **invalid_ready,
                            "status": "ready",
                            "attempt_count": 1,
                            "started_at": datetime(2026, 8, 31, 12, 6, tzinfo=UTC),
                            "completed_at": datetime(
                                2026,
                                8,
                                31,
                                12,
                                7,
                                tzinfo=UTC,
                            ),
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentIndexSet).values(
                        **index_set_values(
                            index_set_id=uuid4(),
                            tenant_id=tenant_id,
                            document_id=uuid4(),
                            version_id=version_id,
                            chunk_set_id=chunk_set_id,
                            identity_character="3",
                        )
                    )
                )

            connection.execute(
                insert(DocumentIndexSet).values(
                    **index_set_values(
                        index_set_id=pending_index_id,
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        identity_character="4",
                    )
                )
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.id == version_id)
                    .values(
                        index_status="ready",
                        active_index_set_id=pending_index_id,
                    )
                )

            connection.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(
                    index_status="ready",
                    active_index_set_id=ready_index_id,
                )
            )
            active_id = connection.scalar(
                select(DocumentVersion.active_index_set_id).where(
                    DocumentVersion.id == version_id
                )
            )
            assert active_id == ready_index_id

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    update(DocumentIndexSet)
                    .where(DocumentIndexSet.id == ready_index_id)
                    .values(
                        status="indexing",
                        chunk_count=None,
                        text_chunk_count=None,
                        table_chunk_count=None,
                        total_token_count=None,
                        completed_at=None,
                    )
                )
        finally:
            transaction.rollback()


def test_chunks_are_unique_per_index_set_and_cascade_with_version(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    owner_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    first_index_id = uuid4()
    second_index_id = uuid4()

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            insert_document_graph(
                connection,
                tenant_id=tenant_id,
                owner_id=owner_id,
                file_id=file_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            connection.execute(
                insert(DocumentIndexSet),
                [
                    index_set_values(
                        index_set_id=first_index_id,
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        identity_character="5",
                        status="ready",
                    ),
                    index_set_values(
                        index_set_id=second_index_id,
                        tenant_id=tenant_id,
                        document_id=document_id,
                        version_id=version_id,
                        chunk_set_id=chunk_set_id,
                        identity_character="6",
                        status="ready",
                    ),
                ],
            )
            first_chunk = chunk_values(
                index_set_id=first_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            second_chunk = chunk_values(
                index_set_id=second_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            connection.execute(insert(DocumentChunk), [first_chunk, second_chunk])
            assert (
                len(
                    connection.scalars(
                        select(DocumentChunk.id).where(
                            DocumentChunk.document_version_id == version_id
                        )
                    ).all()
                )
                == 2
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentChunk).values(
                        **{
                            **first_chunk,
                            "id": uuid4(),
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentChunk).values(
                        **{
                            **first_chunk,
                            "id": uuid4(),
                            "document_id": uuid4(),
                        }
                    )
                )

            connection.execute(
                delete(DocumentVersion).where(DocumentVersion.id == version_id)
            )
            assert (
                connection.scalars(
                    select(DocumentIndexSet.id).where(
                        DocumentIndexSet.document_version_id == version_id
                    )
                ).all()
                == []
            )
            assert (
                connection.scalars(
                    select(DocumentChunk.id).where(
                        DocumentChunk.document_version_id == version_id
                    )
                ).all()
                == []
            )
        finally:
            transaction.rollback()
