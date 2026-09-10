from __future__ import annotations

import io
from collections.abc import Generator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.errors import (
    DocumentChunkPublicationError,
    DocumentIndexingError,
    DocumentNotFoundError,
    DocumentParsingError,
    DocumentStateConflictError,
    EmbeddingProviderError,
)
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
from app.repositories.document_indexes import DocumentIndexRepository
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.schemas.auth import CurrentUser
from app.schemas.knowledge import DocumentCreateInput, DocumentVersionCreateInput
from app.services.documents import DocumentService
from app.services.documents.indexing.service import DocumentIndexService
from app.services.documents.parsers.docling import (
    DoclingParseSnapshot,
    DoclingTextSnapshot,
)
from app.services.files import FileService
from app.services.retrieval import (
    FTS_BUILDER_VERSION,
    FakeEmbeddingProvider,
    FtsTextPurpose,
    build_fts_text,
)
from app.services.storage import LocalStorageBackend
from tests.fixtures.pdf_factory import make_text_pdf

_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


class CountingFakeEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def embed(self, texts, *, purpose):  # type: ignore[no-untyped-def]
        self.call_count += 1
        return super().embed(texts, purpose=purpose)


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    def embed(self, texts, *, purpose):  # type: ignore[no-untyped-def]
        raise EmbeddingProviderError(retryable=True)


class RevisedFakeEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(self) -> None:
        super().__init__()
        self._identity = replace(self.identity, revision="m2-fake-v2")


class TruncatedPageDoclingProvider:
    def parse(
        self,
        *,
        source_name: str,
        source_type: str,
        content: bytes,
    ) -> DoclingParseSnapshot:
        del source_name, content
        return DoclingParseSnapshot(
            source_type=source_type,  # type: ignore[arg-type]
            parser_version="m2-docling-v1+truncated-index-fake",
            page_count=2,
            items=[
                DoclingTextSnapshot(
                    text="x" * 300,
                    label="text",
                    page_number=1,
                ),
                DoclingTextSnapshot(
                    text="lostpage",
                    label="text",
                    page_number=2,
                ),
            ],
        )


@dataclass(slots=True)
class IndexServiceFixture:
    runtime: DatabaseRuntime
    settings: Settings
    storage: LocalStorageBackend
    user: CurrentUser
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    file_id: UUID
    source_storage_key: str

    def service(
        self,
        provider: FakeEmbeddingProvider | None = None,
    ) -> DocumentIndexService:
        return DocumentIndexService(
            self.runtime.session_factory,
            self.storage,
            self.settings,
            provider or FakeEmbeddingProvider(),
            clock=lambda: _NOW,
        )


@pytest.fixture
def index_service_fixture(
    tmp_path: Path,
) -> Generator[IndexServiceFixture, None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=tmp_path / "storage",
    )
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    storage = LocalStorageBackend(settings.local_storage_root)
    tenant_id = uuid4()
    user_id = uuid4()
    user = CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        email="index-service-owner@example.com",
        display_name="Index Service Owner",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )

    session = runtime.session_factory()
    try:
        session.add(Tenant(id=tenant_id, name="M2-15.4 index service tenant"))
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=user.email,
                display_name=user.display_name,
                password_hash="$argon2id$synthetic-index-service-only",
            )
        )
        session.flush()
        files = FileService(
            FileRepository(session, settings.database_statement_timeout_ms),
            storage,
        )
        uploaded = files.upload_file(
            user,
            original_name="synthetic-index-service.pdf",
            declared_content_type="application/pdf",
            stream=io.BytesIO(make_text_pdf(include_empty_page=False)),
            allowed_extensions=settings.upload_allowed_extensions,
            max_size_bytes=settings.upload_max_file_size_bytes,
        )
        detail = DocumentService(
            DocumentRepository(session, settings.database_statement_timeout_ms),
            files,
        ).create_document(
            user,
            DocumentCreateInput(
                file_id=uploaded.response.file_id,
                title="M2-15.4合成索引说明书",
                document_type="product_manual",
                language="zh-CN",
                market="DE",
            ),
        )
        session.commit()
        version_id = detail.versions[0].version_id
        yield IndexServiceFixture(
            runtime=runtime,
            settings=settings,
            storage=storage,
            user=user,
            tenant_id=tenant_id,
            document_id=detail.document_id,
            version_id=version_id,
            file_id=uploaded.response.file_id,
            source_storage_key=uploaded.storage_key,
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
            cleanup.execute(delete(Tenant).where(Tenant.id == tenant_id))
            cleanup.commit()
        finally:
            cleanup.close()
            runtime.engine.dispose()


def test_first_index_runs_full_pipeline_and_activates_only_ready_result(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture

    result = fixture.service().index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert result.status == "ready"
    assert result.reused is False
    assert result.version_activated is True
    assert result.document_id == fixture.document_id
    assert result.version_id == fixture.version_id
    assert result.embedding_model == "fake/m2-deterministic"
    assert result.embedding_version == "m2-fake-v1"
    assert result.chunk_count >= 1

    session = fixture.runtime.session_factory()
    try:
        document = session.get(Document, fixture.document_id)
        version = session.get(DocumentVersion, fixture.version_id)
        index_set = session.get(DocumentIndexSet, result.index_set_id)
        assert document is not None
        assert version is not None
        assert index_set is not None
        assert document.active_version_id == fixture.version_id
        assert version.parse_status == "ready"
        assert version.index_status == "ready"
        assert version.active_index_set_id == result.index_set_id
        assert index_set.status == "ready"
        assert index_set.document_chunk_set_id == result.chunk_set_id
        assert index_set.fts_builder_version == FTS_BUILDER_VERSION
        chunks = list(
            session.scalars(
                select(DocumentChunk).where(
                    DocumentChunk.document_index_set_id == result.index_set_id
                )
            )
        )
        assert chunks
        assert all(
            chunk.fts_text
            == build_fts_text(
                chunk.retrieval_text,
                purpose=FtsTextPurpose.DOCUMENT,
            ).text
            for chunk in chunks
        )
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == result.index_set_id
                )
            )
            == result.chunk_count
        )
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == result.index_set_id,
                    DocumentChunk.embedding.is_not(None),
                )
            )
            == result.chunk_count
        )
        assert (
            session.scalar(
                select(func.count(DocumentChunkSet.id)).where(
                    DocumentChunkSet.document_version_id == fixture.version_id,
                    DocumentChunkSet.status == "ready",
                )
            )
            == 1
        )
    finally:
        session.close()


def test_repeated_ready_request_reuses_parse_chunk_and_index_without_embedding(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    provider = CountingFakeEmbeddingProvider()
    service = fixture.service(provider)

    first = service.index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    second = service.index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert second.index_set_id == first.index_set_id
    assert second.chunk_set_id == first.chunk_set_id
    assert second.reused is True
    assert second.version_activated is False
    assert provider.call_count == 1

    session = fixture.runtime.session_factory()
    try:
        chunk_set = session.get(DocumentChunkSet, first.chunk_set_id)
        index_set = session.get(DocumentIndexSet, first.index_set_id)
        assert chunk_set is not None
        assert index_set is not None
        assert chunk_set.attempt_count == 1
        assert index_set.attempt_count == 1
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == first.index_set_id
                )
            )
            == first.chunk_count
        )
    finally:
        session.close()


def test_parse_failure_marks_first_index_failed_without_creating_index_set(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    fixture.storage.delete(fixture.source_storage_key)

    with pytest.raises(DocumentParsingError):
        fixture.service().index_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_id)
        file_row = session.get(StoredFile, fixture.file_id)
        assert version is not None
        assert file_row is not None
        assert version.parse_status == "failed"
        assert version.index_status == "failed"
        assert file_row.status == "failed"
        assert session.scalar(select(func.count(DocumentIndexSet.id))) == 0
    finally:
        session.close()


def test_quality_rejection_marks_parse_and_index_failed_without_index_set(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    quality_settings = fixture.settings.model_copy(
        update={"native_text_min_characters": 500}
    )
    service = DocumentIndexService(
        fixture.runtime.session_factory,
        fixture.storage,
        quality_settings,
        FakeEmbeddingProvider(),
        docling_provider=TruncatedPageDoclingProvider(),
        clock=lambda: _NOW,
    )

    with pytest.raises(DocumentParsingError):
        service.index_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_id)
        file_row = session.get(StoredFile, fixture.file_id)
        assert version is not None
        assert file_row is not None
        assert version.parse_status == "failed"
        assert version.index_status == "failed"
        assert version.parsed_storage_key is None
        assert file_row.status == "failed"
        assert session.scalar(select(func.count(DocumentIndexSet.id))) == 0
    finally:
        session.close()


def test_chunk_failure_marks_first_index_failed_without_creating_index_set(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    from app.services.documents import DocumentParserService

    DocumentParserService(
        fixture.runtime.session_factory,
        fixture.storage,
        fixture.settings,
        clock=lambda: _NOW,
    ).parse_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    parsed_key = f"{fixture.tenant_id}/parsed/2026/08/{fixture.version_id}.json"
    fixture.storage.delete(parsed_key)

    with pytest.raises(DocumentChunkPublicationError):
        fixture.service().index_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_id)
        file_row = session.get(StoredFile, fixture.file_id)
        assert version is not None
        assert file_row is not None
        assert version.index_status == "failed"
        assert file_row.status == "failed"
        assert session.scalar(select(func.count(DocumentIndexSet.id))) == 0
    finally:
        session.close()


def test_embedding_failure_is_recorded_and_retry_reuses_identity_and_attempt(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture

    with pytest.raises(DocumentIndexingError):
        fixture.service(FailingEmbeddingProvider()).index_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    session = fixture.runtime.session_factory()
    try:
        failed = session.scalar(
            select(DocumentIndexSet).where(
                DocumentIndexSet.document_version_id == fixture.version_id
            )
        )
        version = session.get(DocumentVersion, fixture.version_id)
        assert failed is not None
        assert version is not None
        failed_id = failed.id
        assert failed.status == "failed"
        assert failed.attempt_count == 1
        assert version.index_status == "failed"
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == failed_id
                )
            )
            == 0
        )
    finally:
        session.close()

    ready = fixture.service().index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert ready.index_set_id == failed_id
    session = fixture.runtime.session_factory()
    try:
        retried = session.get(DocumentIndexSet, failed_id)
        assert retried is not None
        assert retried.status == "ready"
        assert retried.attempt_count == 2
    finally:
        session.close()


def test_ready_index_with_missing_chunk_is_rejected_instead_of_reused(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    provider = CountingFakeEmbeddingProvider()
    service = fixture.service(provider)
    ready = service.index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    session = fixture.runtime.session_factory()
    try:
        victim = session.scalar(
            select(DocumentChunk).where(
                DocumentChunk.document_index_set_id == ready.index_set_id
            )
        )
        assert victim is not None
        session.delete(victim)
        session.commit()
    finally:
        session.close()

    with pytest.raises(DocumentStateConflictError):
        service.index_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )
    assert provider.call_count == 1


def test_database_completion_failure_rolls_back_chunks_and_records_failed_attempt(
    index_service_fixture: IndexServiceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = index_service_fixture

    def fail_completion(self, **kwargs):  # type: ignore[no-untyped-def]
        raise SQLAlchemyError("synthetic completion failure")

    monkeypatch.setattr(
        DocumentIndexRepository,
        "complete_index_set",
        fail_completion,
    )
    with pytest.raises(DocumentIndexingError):
        fixture.service().index_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    session = fixture.runtime.session_factory()
    try:
        index_set = session.scalar(
            select(DocumentIndexSet).where(
                DocumentIndexSet.document_version_id == fixture.version_id
            )
        )
        assert index_set is not None
        assert index_set.status == "failed"
        assert (
            session.scalar(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_index_set_id == index_set.id
                )
            )
            == 0
        )
    finally:
        session.close()


def test_cross_tenant_request_is_hidden_before_any_pipeline_work(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    other_user = fixture.user.model_copy(update={"tenant_id": uuid4()})

    with pytest.raises(DocumentNotFoundError):
        fixture.service().index_version(
            other_user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_id)
        assert version is not None
        assert version.parse_status == "pending"
        assert version.index_status == "pending"
        assert session.scalar(select(func.count(DocumentChunkSet.id))) == 0
        assert session.scalar(select(func.count(DocumentIndexSet.id))) == 0
    finally:
        session.close()


def test_same_version_new_embedding_identity_keeps_old_ready_until_switch(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    first = fixture.service().index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    second = fixture.service(RevisedFakeEmbeddingProvider()).index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert second.index_set_id != first.index_set_id
    assert second.chunk_set_id == first.chunk_set_id
    assert second.embedding_version == "m2-fake-v2"
    assert second.version_activated is False
    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_id)
        old_set = session.get(DocumentIndexSet, first.index_set_id)
        new_set = session.get(DocumentIndexSet, second.index_set_id)
        assert version is not None
        assert old_set is not None
        assert new_set is not None
        assert version.active_index_set_id == second.index_set_id
        assert old_set.status == "ready"
        assert new_set.status == "ready"
    finally:
        session.close()


def test_new_version_switches_document_only_after_its_index_is_ready(
    index_service_fixture: IndexServiceFixture,
) -> None:
    fixture = index_service_fixture
    first = fixture.service().index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    session = fixture.runtime.session_factory()
    try:
        files = FileService(
            FileRepository(session, fixture.settings.database_statement_timeout_ms),
            fixture.storage,
        )
        uploaded = files.upload_file(
            fixture.user,
            original_name="synthetic-index-service-v2.pdf",
            declared_content_type="application/pdf",
            stream=io.BytesIO(make_text_pdf(include_empty_page=False) + b"\n"),
            allowed_extensions=fixture.settings.upload_allowed_extensions,
            max_size_bytes=fixture.settings.upload_max_file_size_bytes,
        )
        version = DocumentService(
            DocumentRepository(
                session,
                fixture.settings.database_statement_timeout_ms,
            ),
            files,
        ).add_version(
            fixture.user,
            fixture.document_id,
            DocumentVersionCreateInput(file_id=uploaded.response.file_id),
        )
        session.commit()
        second_version_id = version.version_id
        document = session.get(Document, fixture.document_id)
        assert document is not None
        assert document.active_version_id == fixture.version_id
    finally:
        session.close()

    second = fixture.service().index_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=second_version_id,
    )

    assert second.version_id == second_version_id
    assert second.version_activated is True
    session = fixture.runtime.session_factory()
    try:
        document = session.get(Document, fixture.document_id)
        old_version = session.get(DocumentVersion, fixture.version_id)
        assert document is not None
        assert old_version is not None
        assert document.active_version_id == second_version_id
        assert old_version.active_index_set_id == first.index_set_id
    finally:
        session.close()
