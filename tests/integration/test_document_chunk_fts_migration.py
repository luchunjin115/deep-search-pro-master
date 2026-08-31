from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import Engine, delete, insert, inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.identity import Tenant
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
)
from app.services.retrieval.lexical_text import FtsTextPurpose, build_fts_text
from tests.integration.test_document_index_set_migration import (
    alembic_config,
    chunk_values,
    index_set_values,
    insert_document_graph,
)

OLD_FTS_BUILDER_VERSION = "m2-fts-raw-retrieval-v1"
NEW_FTS_BUILDER_VERSION = "m2-fts-jieba-search-v1"


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


def _identity_constraint(engine: Engine) -> str:
    constraints = inspect(engine).get_check_constraints("document_index_sets")
    return next(
        constraint["sqltext"]
        for constraint in constraints
        if constraint["name"] == "ck_document_index_sets_identity_format"
    )


def test_versioned_fts_builder_migration_round_trips(
    postgres_settings: Settings,
) -> None:
    del postgres_settings
    config = alembic_config()

    try:
        command.downgrade(config, "20260831_0007")
        runtime = create_database_runtime(Settings())
        try:
            old_constraint = _identity_constraint(runtime.engine)
            assert OLD_FTS_BUILDER_VERSION in old_constraint
            assert NEW_FTS_BUILDER_VERSION not in old_constraint
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260831_0008")
        runtime = create_database_runtime(Settings())
        try:
            upgraded_constraint = _identity_constraint(runtime.engine)
            assert OLD_FTS_BUILDER_VERSION in upgraded_constraint
            assert NEW_FTS_BUILDER_VERSION in upgraded_constraint
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260831_0007")
        runtime = create_database_runtime(Settings())
        try:
            restored_constraint = _identity_constraint(runtime.engine)
            assert OLD_FTS_BUILDER_VERSION in restored_constraint
            assert NEW_FTS_BUILDER_VERSION not in restored_constraint
        finally:
            runtime.engine.dispose()
    finally:
        command.upgrade(config, "head")


def test_old_and_new_fts_index_sets_coexist_and_only_ready_can_activate(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    owner_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    old_index_id = uuid4()
    new_index_id = uuid4()
    source_text = "蘑菇灯亮度调节说明"
    query_text = build_fts_text(
        "亮度",
        purpose=FtsTextPurpose.QUERY,
    ).text

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
            old_values = index_set_values(
                index_set_id=old_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                identity_character="1",
                status="ready",
            )
            new_values = index_set_values(
                index_set_id=new_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                identity_character="1",
            )
            new_values["fts_builder_version"] = NEW_FTS_BUILDER_VERSION
            connection.execute(insert(DocumentIndexSet).values(**old_values))
            connection.execute(insert(DocumentIndexSet).values(**new_values))

            old_chunk = chunk_values(
                index_set_id=old_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            old_chunk.update(
                id=uuid4(),
                retrieval_text=source_text,
                fts_text=source_text,
            )
            connection.execute(insert(DocumentChunk).values(**old_chunk))
            connection.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(index_status="ready", active_index_set_id=old_index_id)
            )
            connection.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(active_version_id=version_id)
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.id == version_id)
                    .values(active_index_set_id=new_index_id)
                )
            assert (
                connection.scalar(
                    select(DocumentVersion.active_index_set_id).where(
                        DocumentVersion.id == version_id
                    )
                )
                == old_index_id
            )

            new_chunk = chunk_values(
                index_set_id=new_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            new_chunk.update(
                id=uuid4(),
                retrieval_text=source_text,
                fts_text=build_fts_text(
                    source_text,
                    purpose=FtsTextPurpose.DOCUMENT,
                ).text,
            )
            connection.execute(insert(DocumentChunk).values(**new_chunk))
            new_created_at = connection.scalar(
                select(DocumentIndexSet.created_at).where(
                    DocumentIndexSet.id == new_index_id
                )
            )
            assert new_created_at is not None
            connection.execute(
                update(DocumentIndexSet)
                .where(DocumentIndexSet.id == new_index_id)
                .values(
                    status="ready",
                    attempt_count=1,
                    started_at=new_created_at + timedelta(seconds=1),
                    completed_at=new_created_at + timedelta(seconds=2),
                    chunk_count=1,
                    text_chunk_count=1,
                    table_chunk_count=0,
                    total_token_count=10,
                )
            )
            connection.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(active_index_set_id=new_index_id)
            )

            versions = connection.scalars(
                select(DocumentIndexSet.fts_builder_version)
                .where(DocumentIndexSet.document_version_id == version_id)
                .order_by(DocumentIndexSet.fts_builder_version)
            ).all()
            assert versions == [NEW_FTS_BUILDER_VERSION, OLD_FTS_BUILDER_VERSION]
            assert (
                connection.scalar(
                    select(DocumentVersion.active_index_set_id).where(
                        DocumentVersion.id == version_id
                    )
                )
                == new_index_id
            )

            hits = (
                connection.execute(
                    sa.text(
                        "SELECT i.fts_builder_version "
                        "FROM document_chunks AS c "
                        "JOIN document_index_sets AS i ON i.id = c.document_index_set_id "
                        "WHERE c.search_vector @@ plainto_tsquery('simple', :query)"
                    ),
                    {"query": query_text},
                )
                .scalars()
                .all()
            )
            assert hits == [NEW_FTS_BUILDER_VERSION]

            invalid_values = index_set_values(
                index_set_id=uuid4(),
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                identity_character="2",
            )
            invalid_values["fts_builder_version"] = "unversioned-custom-builder"
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(DocumentIndexSet).values(**invalid_values))
        finally:
            transaction.rollback()


def test_downgrade_refuses_to_silently_delete_new_fts_index_sets(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    owner_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    new_index_id = uuid4()

    try:
        with postgres_engine.begin() as connection:
            insert_document_graph(
                connection,
                tenant_id=tenant_id,
                owner_id=owner_id,
                file_id=file_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
            )
            values = index_set_values(
                index_set_id=new_index_id,
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                chunk_set_id=chunk_set_id,
                identity_character="3",
            )
            values["fts_builder_version"] = NEW_FTS_BUILDER_VERSION
            connection.execute(insert(DocumentIndexSet).values(**values))

        with pytest.raises(RuntimeError, match="cannot downgrade"):
            command.downgrade(alembic_config(), "20260831_0007")
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                delete(DocumentVersion).where(DocumentVersion.id == version_id)
            )
            connection.execute(delete(Tenant).where(Tenant.id == tenant_id))
        command.upgrade(alembic_config(), "head")
