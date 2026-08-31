from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, insert, inspect, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import Document, DocumentChunkSet, DocumentVersion, StoredFile
from app.services.documents.chunking import (
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    UnicodeMixedTokenCounter,
)
from app.services.documents.chunking.contracts import (
    CHUNK_ARTIFACT_SCHEMA_VERSION,
    CHUNK_CONTENT_HASH_VERSION,
    canonical_sha256,
    derive_chunk_set_id,
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
) -> dict[str, object]:
    counter = UnicodeMixedTokenCounter()
    config = ChunkingConfig()
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
    }


def test_chunk_set_migration_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()

    try:
        command.downgrade(config, "20260829_0004")
        runtime = create_database_runtime(Settings())
        try:
            tables = set(inspect(runtime.engine).get_table_names())
            assert "document_chunk_sets" not in tables
            assert {"files", "documents", "document_versions"} <= tables
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260831_0005")
        runtime = create_database_runtime(Settings())
        try:
            inspector = inspect(runtime.engine)
            assert "document_chunk_sets" in inspector.get_table_names()
            assert {
                "config_json",
                "config_sha256",
                "chunk_storage_key",
                "output_sha256",
                "chunk_count",
            } <= {
                column["name"]
                for column in inspector.get_columns("document_chunk_sets")
            }
        finally:
            runtime.engine.dispose()
    finally:
        command.upgrade(config, "head")


def test_database_enforces_chunk_set_identity_status_and_tenant_boundaries(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    owner_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    other_document_id = uuid4()
    version_id = uuid4()
    created_at = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
    input_provenance = ChunkInputProvenance(
        document_id=document_id,
        document_version_id=version_id,
        source_sha256="a" * 64,
        parsed_publication_sha256="b" * 64,
        selected_artifact_content_sha256="c" * 64,
    )
    counter = UnicodeMixedTokenCounter()
    identity = ChunkerIdentity(
        token_counter_name=counter.name,
        token_counter_version=counter.version,
    )
    config_sha256 = canonical_sha256(ChunkingConfig().model_dump(mode="json"))
    chunk_set_id = derive_chunk_set_id(
        input_provenance=input_provenance,
        chunker=identity,
        config_sha256=config_sha256,
    )
    values = chunk_set_values(
        tenant_id=tenant_id,
        document_id=document_id,
        version_id=version_id,
        chunk_set_id=chunk_set_id,
    )
    values["created_at"] = created_at

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                insert(Tenant).values(id=tenant_id, name="Chunk Set tenant")
            )
            connection.execute(
                insert(User).values(
                    id=owner_id,
                    tenant_id=tenant_id,
                    email="chunk-set-owner@example.com",
                    display_name="Chunk Set Owner",
                    password_hash="$argon2id$synthetic-only-hash",
                )
            )
            connection.execute(
                insert(StoredFile).values(
                    id=file_id,
                    tenant_id=tenant_id,
                    owner_user_id=owner_id,
                    original_name="synthetic-chunk-set.pdf",
                    storage_key=(f"{tenant_id}/uploads/2026/08/{file_id}.pdf"),
                    extension=".pdf",
                    mime_type="application/pdf",
                    size_bytes=128,
                    sha256="a" * 64,
                    category="uploads",
                )
            )
            connection.execute(
                insert(Document),
                [
                    {
                        "id": document_id,
                        "tenant_id": tenant_id,
                        "owner_user_id": owner_id,
                        "title": "合成Chunk文档",
                        "document_type": "product_manual",
                        "access_level": "private",
                    },
                    {
                        "id": other_document_id,
                        "tenant_id": tenant_id,
                        "owner_user_id": owner_id,
                        "title": "另一个合成文档",
                        "document_type": "product_manual",
                        "access_level": "private",
                    },
                ],
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
            connection.execute(insert(DocumentChunkSet).values(**values))

            connection.execute(
                postgresql_insert(DocumentChunkSet)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            assert connection.scalars(select(DocumentChunkSet.id)).all() == [
                chunk_set_id
            ]

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentChunkSet).values(
                        **{
                            **values,
                            "id": uuid4(),
                            "document_id": other_document_id,
                        }
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    update(DocumentChunkSet)
                    .where(DocumentChunkSet.id == chunk_set_id)
                    .values(status="ready")
                )

            started_at = created_at + timedelta(minutes=1)
            completed_at = started_at + timedelta(seconds=2)
            connection.execute(
                update(DocumentChunkSet)
                .where(DocumentChunkSet.id == chunk_set_id)
                .values(
                    status="chunking",
                    attempt_count=1,
                    started_at=started_at,
                )
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    update(DocumentChunkSet)
                    .where(DocumentChunkSet.id == chunk_set_id)
                    .values(
                        status="ready",
                        completed_at=completed_at,
                        output_sha256="d" * 64,
                        chunk_storage_key=(
                            f"{tenant_id}/chunks/2026/08/{chunk_set_id}.json"
                        ),
                        chunk_count=3,
                        text_chunk_count=1,
                        table_chunk_count=1,
                        total_token_count=1200,
                        excluded_span_count=0,
                    )
                )

            connection.execute(
                update(DocumentChunkSet)
                .where(DocumentChunkSet.id == chunk_set_id)
                .values(
                    status="ready",
                    completed_at=completed_at,
                    output_sha256="d" * 64,
                    chunk_storage_key=(
                        f"{tenant_id}/chunks/2026/08/{chunk_set_id}.json"
                    ),
                    chunk_count=3,
                    text_chunk_count=2,
                    table_chunk_count=1,
                    total_token_count=1200,
                    excluded_span_count=0,
                )
            )
            ready = connection.execute(
                select(
                    DocumentChunkSet.status,
                    DocumentChunkSet.chunk_count,
                    DocumentChunkSet.chunk_storage_key,
                ).where(DocumentChunkSet.id == chunk_set_id)
            ).one()
            assert ready.status == "ready"
            assert ready.chunk_count == 3
            assert ready.chunk_storage_key.endswith(f"/{chunk_set_id}.json")

            connection.execute(
                delete(DocumentVersion).where(DocumentVersion.id == version_id)
            )
            assert connection.scalar(select(DocumentChunkSet.id)) is None
        finally:
            transaction.rollback()
