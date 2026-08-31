from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories import DocumentIndexRepository
from app.services.documents.chunking import (
    CanonicalChunkArtifact,
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    UnicodeMixedTokenCounter,
    build_chunk_artifact,
    build_document_chunk,
)
from app.services.documents.chunking.contracts import ChunkSourceSpan
from app.services.documents.indexing import (
    DocumentChunkWriteFacts,
    DocumentIndexSetIdentity,
    build_document_index_set_identity,
    map_document_chunk_rows,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.retrieval import (
    EmbeddingBatch,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
)
from app.services.retrieval.embedding import build_embedding_cache_key

_BASE_TIME = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class IndexRepositoryFixture:
    runtime: DatabaseRuntime
    tenant_id: UUID
    other_tenant_id: UUID
    document_id: UUID
    version_ids: dict[str, UUID]
    file_ids: dict[str, UUID]
    artifacts: dict[str, CanonicalChunkArtifact]

    def repository(self, session):  # type: ignore[no-untyped-def]
        return DocumentIndexRepository(session, statement_timeout_ms=2000)


def _artifact(
    *,
    document_id: UUID,
    version_id: UUID,
    hash_character: str,
) -> CanonicalChunkArtifact:
    counter = UnicodeMixedTokenCounter()
    chunks = []
    for index, (heading, text) in enumerate(
        (
            ("安全要求", "额定电压为220V。"),
            ("保修政策", "产品保修期为两年。"),
        ),
        start=1,
    ):
        locator = SourceLocator(page_number=index, heading_path=[heading])
        retrieval_text = f"{heading}\n{text}"
        chunks.append(
            build_document_chunk(
                chunk_id=f"c{index:06d}",
                chunk_index=index,
                kind="text",
                body_text=text,
                retrieval_text=retrieval_text,
                token_count=counter.count(retrieval_text),
                heading_path=[heading],
                source_block_ids=[f"b{index:06d}"],
                source_spans=[
                    ChunkSourceSpan(
                        block_id=f"b{index:06d}",
                        start_locator=locator,
                        end_locator=locator,
                        character_start=0,
                        character_end=len(text),
                    )
                ],
                page_numbers=[index],
            )
        )
    return build_chunk_artifact(
        input_provenance=ChunkInputProvenance(
            document_id=document_id,
            document_version_id=version_id,
            source_sha256=hash_character * 64,
            parsed_publication_sha256=chr(ord(hash_character) + 1) * 64,
            selected_artifact_content_sha256=chr(ord(hash_character) + 2) * 64,
        ),
        chunker=ChunkerIdentity(
            token_counter_name=counter.name,
            token_counter_version=counter.version,
        ),
        config=ChunkingConfig(),
        chunks=chunks,
    )


@pytest.fixture
def index_repository_fixture() -> Generator[IndexRepositoryFixture, None, None]:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    owner_id = uuid4()
    document_id = uuid4()
    version_ids = {"v1": uuid4(), "v2": uuid4()}
    file_ids = {"v1": uuid4(), "v2": uuid4()}
    artifacts = {
        "v1": _artifact(
            document_id=document_id,
            version_id=version_ids["v1"],
            hash_character="a",
        ),
        "v2": _artifact(
            document_id=document_id,
            version_id=version_ids["v2"],
            hash_character="d",
        ),
    }

    session = runtime.session_factory()
    try:
        session.add_all(
            [
                Tenant(id=tenant_id, name="M2-15.3 index repository tenant"),
                Tenant(id=other_tenant_id, name="M2-15.3 other tenant"),
                User(
                    id=owner_id,
                    tenant_id=tenant_id,
                    email=f"index-repository-{tenant_id}@example.com",
                    display_name="Index Repository Owner",
                    password_hash="$argon2id$synthetic-index-repository-only",
                ),
            ]
        )
        session.flush()
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant_id,
                owner_user_id=owner_id,
                title="M2-15.3合成索引文档",
                document_type="product_manual",
                access_level="private",
                created_at=_BASE_TIME,
            )
        )
        session.flush()
        for version_no, key in enumerate(("v1", "v2"), start=1):
            artifact = artifacts[key]
            file_id = file_ids[key]
            version_id = version_ids[key]
            session.add(
                StoredFile(
                    id=file_id,
                    tenant_id=tenant_id,
                    owner_user_id=owner_id,
                    original_name=f"synthetic-{key}.pdf",
                    storage_key=(f"{tenant_id}/uploads/2026/08/{file_id}.pdf"),
                    extension=".pdf",
                    mime_type="application/pdf",
                    size_bytes=128,
                    sha256=artifact.input.source_sha256,
                    category="uploads",
                    status="parsing",
                    created_at=_BASE_TIME,
                )
            )
            session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    file_id=file_id,
                    version_no=version_no,
                    content_hash=artifact.input.source_sha256,
                    parser_name="native_pdf",
                    parser_version="m2-native-pdf-v1",
                    parsed_storage_key=(
                        f"{tenant_id}/parsed/2026/08/{version_id}.json"
                    ),
                    parse_status="ready",
                    index_status="pending",
                    created_at=_BASE_TIME,
                )
            )
            session.flush()
            session.add(
                DocumentChunkSet(
                    id=artifact.chunk_set_id,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    artifact_schema_version=artifact.schema_version,
                    content_hash_version=artifact.content_hash_version,
                    routed_schema_version=artifact.input.routed_schema_version,
                    canonical_schema_version=artifact.input.canonical_schema_version,
                    source_sha256=artifact.input.source_sha256,
                    parsed_publication_sha256=(
                        artifact.input.parsed_publication_sha256
                    ),
                    selected_artifact_content_sha256=(
                        artifact.input.selected_artifact_content_sha256
                    ),
                    chunker_name=artifact.chunker.name,
                    chunker_version=artifact.chunker.version,
                    token_counter_name=artifact.chunker.token_counter_name,
                    token_counter_version=artifact.chunker.token_counter_version,
                    normalization_version=artifact.config.normalization_version,
                    config_json=artifact.config.model_dump(mode="json"),
                    config_sha256=artifact.config_sha256,
                    status="ready",
                    attempt_count=1,
                    output_sha256=artifact.output_sha256,
                    chunk_storage_key=(
                        f"{tenant_id}/chunks/2026/08/{artifact.chunk_set_id}.json"
                    ),
                    chunk_count=artifact.statistics.chunk_count,
                    text_chunk_count=artifact.statistics.text_chunk_count,
                    table_chunk_count=artifact.statistics.table_chunk_count,
                    total_token_count=artifact.statistics.total_token_count,
                    excluded_span_count=artifact.statistics.excluded_span_count,
                    created_at=_BASE_TIME,
                    started_at=_BASE_TIME + timedelta(seconds=1),
                    completed_at=_BASE_TIME + timedelta(seconds=2),
                )
            )
        session.commit()
        yield IndexRepositoryFixture(
            runtime=runtime,
            tenant_id=tenant_id,
            other_tenant_id=other_tenant_id,
            document_id=document_id,
            version_ids=version_ids,
            file_ids=file_ids,
            artifacts=artifacts,
        )
    finally:
        session.close()
        cleanup = runtime.session_factory()
        try:
            cleanup.execute(
                update(Document)
                .where(Document.tenant_id == tenant_id)
                .values(active_version_id=None)
            )
            cleanup.execute(
                update(DocumentVersion)
                .where(DocumentVersion.tenant_id == tenant_id)
                .values(active_index_set_id=None)
            )
            cleanup.execute(
                delete(DocumentVersion).where(DocumentVersion.tenant_id == tenant_id)
            )
            cleanup.execute(delete(Document).where(Document.tenant_id == tenant_id))
            cleanup.execute(delete(StoredFile).where(StoredFile.tenant_id == tenant_id))
            cleanup.execute(delete(User).where(User.tenant_id == tenant_id))
            cleanup.execute(
                delete(Tenant).where(Tenant.id.in_((tenant_id, other_tenant_id)))
            )
            cleanup.commit()
        finally:
            cleanup.close()
            runtime.engine.dispose()


def _index_inputs(
    fixture: IndexRepositoryFixture,
    version_key: str,
    *,
    revision: str = "m2-fake-v1",
) -> tuple[DocumentIndexSetIdentity, tuple[DocumentChunkWriteFacts, ...]]:
    artifact = fixture.artifacts[version_key]
    provider = FakeEmbeddingProvider()
    base = provider.embed(
        [chunk.retrieval_text for chunk in artifact.chunks],
        purpose=EmbeddingPurpose.DOCUMENT,
    )
    embedding_identity = replace(provider.identity, revision=revision)
    batch = EmbeddingBatch(
        vectors=base.vectors,
        cache_keys=tuple(
            build_embedding_cache_key(
                embedding_identity,
                EmbeddingPurpose.DOCUMENT,
                chunk.retrieval_text,
            )
            for chunk in artifact.chunks
        ),
        purpose=EmbeddingPurpose.DOCUMENT,
        identity=embedding_identity,
        effective_batch_size=base.effective_batch_size,
    )
    identity = build_document_index_set_identity(artifact, embedding_identity)
    rows = map_document_chunk_rows(
        tenant_id=fixture.tenant_id,
        artifact=artifact,
        index_identity=identity,
        embeddings=batch,
    )
    return identity, rows


def _claim(
    fixture: IndexRepositoryFixture,
    identity: DocumentIndexSetIdentity,
    *,
    at: datetime = _BASE_TIME + timedelta(minutes=1),
) -> DocumentIndexSet | None:
    session = fixture.runtime.session_factory()
    try:
        row = fixture.repository(session).claim_index_set(
            tenant_id=fixture.tenant_id,
            identity=identity,
            claimed_at=at,
        )
        session.commit()
        return row
    finally:
        session.close()


def _complete(
    fixture: IndexRepositoryFixture,
    identity: DocumentIndexSetIdentity,
    rows: tuple[DocumentChunkWriteFacts, ...],
    *,
    attempt: int = 1,
    at: datetime = _BASE_TIME + timedelta(minutes=2),
) -> DocumentIndexSet | None:
    session = fixture.runtime.session_factory()
    try:
        result = fixture.repository(session).complete_index_set(
            tenant_id=fixture.tenant_id,
            identity=identity,
            expected_attempt_count=attempt,
            chunks=rows,
            completed_at=at,
        )
        session.commit()
        return result
    finally:
        session.close()


def test_same_index_identity_can_only_be_claimed_by_one_worker(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    identity, _ = _index_inputs(fixture, "v1")

    first = _claim(fixture, identity)
    second = _claim(fixture, identity, at=_BASE_TIME + timedelta(minutes=2))

    assert first is not None
    assert first.status == "indexing"
    assert first.attempt_count == 1
    assert second is None
    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_ids["v1"])
        file_row = session.get(StoredFile, fixture.file_ids["v1"])
        assert version is not None and version.index_status == "indexing"
        assert version.active_index_set_id is None
        assert file_row is not None and file_row.status == "indexing"
    finally:
        session.close()


def test_failed_attempt_can_retry_and_rejects_a_stale_worker(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    identity, rows = _index_inputs(fixture, "v1")
    assert _claim(fixture, identity) is not None

    session = fixture.runtime.session_factory()
    try:
        failed = fixture.repository(session).fail_index_set(
            tenant_id=fixture.tenant_id,
            identity=identity,
            expected_attempt_count=1,
            error_message="synthetic embedding failure",
            completed_at=_BASE_TIME + timedelta(minutes=2),
        )
        session.commit()
        assert failed is not None and failed.status == "failed"
        assert failed.error_message == "synthetic embedding failure"
    finally:
        session.close()

    retried = _claim(fixture, identity, at=_BASE_TIME + timedelta(minutes=3))
    assert retried is not None
    assert retried.status == "indexing"
    assert retried.attempt_count == 2
    assert retried.error_message is None

    stale_session = fixture.runtime.session_factory()
    try:
        stale = fixture.repository(stale_session).complete_index_set(
            tenant_id=fixture.tenant_id,
            identity=identity,
            expected_attempt_count=1,
            chunks=rows,
            completed_at=_BASE_TIME + timedelta(minutes=4),
        )
        stale_session.commit()
        assert stale is None
    finally:
        stale_session.close()

    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_ids["v1"])
        file_row = session.get(StoredFile, fixture.file_ids["v1"])
        assert version is not None and version.index_status == "indexing"
        assert file_row is not None and file_row.status == "indexing"
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == identity.index_set_id
                )
            )
            == 0
        )
    finally:
        session.close()


def test_first_completion_atomically_saves_rows_and_activates_both_pointers(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    identity, rows = _index_inputs(fixture, "v1")
    assert _claim(fixture, identity) is not None

    completed = _complete(fixture, identity, rows)

    assert completed is not None
    assert completed.status == "ready"
    assert completed.chunk_count == 2
    assert completed.text_chunk_count == 2
    assert completed.table_chunk_count == 0
    assert completed.total_token_count == sum(row.token_count for row in rows)
    session = fixture.runtime.session_factory()
    try:
        document = session.get(Document, fixture.document_id)
        version = session.get(DocumentVersion, fixture.version_ids["v1"])
        file_row = session.get(StoredFile, fixture.file_ids["v1"])
        stored = list(
            session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_index_set_id == identity.index_set_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        assert document is not None
        assert document.active_version_id == fixture.version_ids["v1"]
        assert version is not None
        assert version.index_status == "ready"
        assert version.active_index_set_id == identity.index_set_id
        assert file_row is not None and file_row.status == "ready"
        assert [row.chunk_id for row in stored] == ["c000001", "c000002"]
        assert [row.embedding_cache_key for row in stored] == [
            row.embedding_cache_key for row in rows
        ]
    finally:
        session.close()


def test_ready_identity_is_reused_without_new_attempt_or_duplicate_chunks(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    identity, rows = _index_inputs(fixture, "v1")
    assert _claim(fixture, identity) is not None
    assert _complete(fixture, identity, rows) is not None

    reused = _claim(fixture, identity, at=_BASE_TIME + timedelta(minutes=5))

    assert reused is not None
    assert reused.status == "ready"
    assert reused.attempt_count == 1
    session = fixture.runtime.session_factory()
    try:
        assert (
            session.scalar(
                select(func.count(DocumentIndexSet.id)).where(
                    DocumentIndexSet.document_version_id == fixture.version_ids["v1"]
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == identity.index_set_id
                )
            )
            == 2
        )
    finally:
        session.close()


def test_bad_batch_rolls_back_all_new_rows_and_keeps_old_active(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    old_identity, old_rows = _index_inputs(fixture, "v1")
    assert _claim(fixture, old_identity) is not None
    assert _complete(fixture, old_identity, old_rows) is not None
    new_identity, new_rows = _index_inputs(
        fixture,
        "v1",
        revision="m2-fake-v2",
    )
    assert _claim(fixture, new_identity) is not None
    duplicate_index_rows = (
        new_rows[0],
        new_rows[1].model_copy(update={"chunk_index": 1}),
    )

    session = fixture.runtime.session_factory()
    try:
        with pytest.raises(IntegrityError):
            fixture.repository(session).complete_index_set(
                tenant_id=fixture.tenant_id,
                identity=new_identity,
                expected_attempt_count=1,
                chunks=duplicate_index_rows,
                completed_at=_BASE_TIME + timedelta(minutes=6),
            )
        session.rollback()
    finally:
        session.close()

    check = fixture.runtime.session_factory()
    try:
        version = check.get(DocumentVersion, fixture.version_ids["v1"])
        candidate = check.get(DocumentIndexSet, new_identity.index_set_id)
        assert version is not None
        assert version.index_status == "ready"
        assert version.active_index_set_id == old_identity.index_set_id
        assert candidate is not None and candidate.status == "indexing"
        assert (
            check.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == new_identity.index_set_id
                )
            )
            == 0
        )
        assert (
            check.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == old_identity.index_set_id
                )
            )
            == 2
        )
    finally:
        check.close()


def test_reindex_keeps_old_active_until_the_new_set_is_complete(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    old_identity, old_rows = _index_inputs(fixture, "v1")
    assert _claim(fixture, old_identity) is not None
    assert _complete(fixture, old_identity, old_rows) is not None
    new_identity, new_rows = _index_inputs(
        fixture,
        "v1",
        revision="m2-fake-v2",
    )

    claimed = _claim(fixture, new_identity)

    assert claimed is not None and claimed.status == "indexing"
    before = fixture.runtime.session_factory()
    try:
        version = before.get(DocumentVersion, fixture.version_ids["v1"])
        assert version is not None
        assert version.index_status == "ready"
        assert version.active_index_set_id == old_identity.index_set_id
    finally:
        before.close()

    assert _complete(fixture, new_identity, new_rows) is not None
    after = fixture.runtime.session_factory()
    try:
        document = after.get(Document, fixture.document_id)
        version = after.get(DocumentVersion, fixture.version_ids["v1"])
        old_set = after.get(DocumentIndexSet, old_identity.index_set_id)
        assert document is not None
        assert document.active_version_id == fixture.version_ids["v1"]
        assert version is not None
        assert version.active_index_set_id == new_identity.index_set_id
        assert old_set is not None and old_set.status == "ready"
    finally:
        after.close()


def test_new_version_only_replaces_the_document_pointer_after_ready(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    first_identity, first_rows = _index_inputs(fixture, "v1")
    assert _claim(fixture, first_identity) is not None
    assert _complete(fixture, first_identity, first_rows) is not None
    second_identity, second_rows = _index_inputs(fixture, "v2")

    assert _claim(fixture, second_identity) is not None
    before = fixture.runtime.session_factory()
    try:
        document = before.get(Document, fixture.document_id)
        second_version = before.get(DocumentVersion, fixture.version_ids["v2"])
        assert document is not None
        assert document.active_version_id == fixture.version_ids["v1"]
        assert second_version is not None
        assert second_version.index_status == "indexing"
        assert second_version.active_index_set_id is None
    finally:
        before.close()

    assert _complete(fixture, second_identity, second_rows) is not None
    after = fixture.runtime.session_factory()
    try:
        document = after.get(Document, fixture.document_id)
        first_version = after.get(DocumentVersion, fixture.version_ids["v1"])
        second_version = after.get(DocumentVersion, fixture.version_ids["v2"])
        assert document is not None
        assert document.active_version_id == fixture.version_ids["v2"]
        assert first_version is not None
        assert first_version.active_index_set_id == first_identity.index_set_id
        assert second_version is not None
        assert second_version.active_index_set_id == second_identity.index_set_id
        assert second_version.index_status == "ready"
    finally:
        after.close()


def test_soft_delete_and_cross_boundary_checks_reject_claim_or_completion(
    index_repository_fixture: IndexRepositoryFixture,
) -> None:
    fixture = index_repository_fixture
    identity, rows = _index_inputs(fixture, "v1")
    second_identity, _ = _index_inputs(fixture, "v2")

    wrong_tenant_session = fixture.runtime.session_factory()
    try:
        assert (
            fixture.repository(wrong_tenant_session).claim_index_set(
                tenant_id=fixture.other_tenant_id,
                identity=identity,
                claimed_at=_BASE_TIME + timedelta(minutes=1),
            )
            is None
        )
        wrong_tenant_session.commit()
    finally:
        wrong_tenant_session.close()

    wrong_document_session = fixture.runtime.session_factory()
    try:
        wrong_document = identity.model_copy(update={"document_id": uuid4()})
        assert (
            fixture.repository(wrong_document_session).claim_index_set(
                tenant_id=fixture.tenant_id,
                identity=wrong_document,
                claimed_at=_BASE_TIME + timedelta(minutes=1),
            )
            is None
        )
        wrong_document_session.commit()
    finally:
        wrong_document_session.close()

    deleted_file_session = fixture.runtime.session_factory()
    try:
        deleted_file_session.execute(
            update(StoredFile)
            .where(StoredFile.id == fixture.file_ids["v2"])
            .values(
                status="soft_deleted",
                deleted_at=_BASE_TIME + timedelta(minutes=1),
            )
        )
        deleted_file_session.commit()
    finally:
        deleted_file_session.close()
    assert _claim(fixture, second_identity) is None

    assert _claim(fixture, identity) is not None
    deletion = fixture.runtime.session_factory()
    try:
        deletion.execute(
            update(Document)
            .where(Document.id == fixture.document_id)
            .values(deleted_at=_BASE_TIME + timedelta(minutes=2))
        )
        deletion.commit()
    finally:
        deletion.close()

    completion = fixture.runtime.session_factory()
    try:
        assert (
            fixture.repository(completion).complete_index_set(
                tenant_id=fixture.tenant_id,
                identity=identity,
                expected_attempt_count=1,
                chunks=rows,
                completed_at=_BASE_TIME + timedelta(minutes=3),
            )
            is None
        )
        completion.commit()
    finally:
        completion.close()

    check = fixture.runtime.session_factory()
    try:
        document = check.get(Document, fixture.document_id)
        index_set = check.get(DocumentIndexSet, identity.index_set_id)
        assert document is not None and document.active_version_id is None
        assert index_set is not None and index_set.status == "indexing"
        assert (
            check.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == identity.index_set_id
                )
            )
            == 0
        )
    finally:
        check.close()
