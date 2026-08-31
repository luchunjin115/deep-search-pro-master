from __future__ import annotations

import io
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.errors import (
    DocumentChunkPublicationError,
    DocumentNotFoundError,
    DocumentStateConflictError,
)
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentChunkSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.schemas.auth import CurrentUser
from app.schemas.knowledge import DocumentCreateInput
from app.services.documents import (
    DocumentChunkService,
    DocumentParserService,
    DocumentService,
)
from app.services.documents.artifacts import CanonicalParsedArtifact
from app.services.documents.chunking import (
    CanonicalChunkArtifact,
    DocumentChunkingResult,
    StructureAwareDocumentChunker,
)
from app.services.files import FileService
from app.services.storage import LocalStorageBackend
from tests.fixtures.pdf_factory import make_text_pdf


@dataclass(slots=True)
class ChunkServiceFixture:
    runtime: DatabaseRuntime
    settings: Settings
    storage: LocalStorageBackend
    user: CurrentUser
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    file_id: UUID
    parsed_key: str

    def service(self, *, settings: Settings | None = None) -> DocumentChunkService:
        return DocumentChunkService(
            self.runtime.session_factory,
            self.storage,
            settings or self.settings,
            clock=lambda: datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
        )

    def chunk_key(self, chunk_set_id: UUID) -> str:
        return f"{self.tenant_id}/chunks/2026/08/{chunk_set_id}.json"


@pytest.fixture
def chunk_service_fixture(
    tmp_path: Path,
) -> Generator[ChunkServiceFixture, None, None]:
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
        email="chunk-owner@example.com",
        display_name="Chunk Owner",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )
    source = make_text_pdf(include_empty_page=False)

    session = runtime.session_factory()
    try:
        session.add(Tenant(id=tenant_id, name="M2-12.5 chunk tenant"))
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=user.email,
                display_name=user.display_name,
                password_hash="$argon2id$synthetic-chunk-only",
            )
        )
        session.flush()
        files = FileService(
            FileRepository(session, settings.database_statement_timeout_ms),
            storage,
        )
        uploaded = files.upload_file(
            user,
            original_name="synthetic-chunk-manual.pdf",
            declared_content_type="application/pdf",
            stream=io.BytesIO(source),
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
                title="M2-12.5合成切块说明书",
                document_type="product_manual",
                language="zh-CN",
                market="DE",
            ),
        )
        session.commit()
        version_id = detail.versions[0].version_id
        DocumentParserService(
            runtime.session_factory,
            storage,
            settings,
            clock=lambda: datetime(2026, 8, 31, 11, 0, tzinfo=UTC),
        ).parse_version(
            user,
            document_id=detail.document_id,
            version_id=version_id,
        )
        fixture = ChunkServiceFixture(
            runtime=runtime,
            settings=settings,
            storage=storage,
            user=user,
            tenant_id=tenant_id,
            document_id=detail.document_id,
            version_id=version_id,
            file_id=uploaded.response.file_id,
            parsed_key=(f"{tenant_id}/parsed/2026/08/{version_id}.json"),
        )
        yield fixture
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


def _chunk_sets(fixture: ChunkServiceFixture) -> list[DocumentChunkSet]:
    session = fixture.runtime.session_factory()
    try:
        rows = list(
            session.scalars(
                select(DocumentChunkSet)
                .where(DocumentChunkSet.tenant_id == fixture.tenant_id)
                .order_by(DocumentChunkSet.created_at, DocumentChunkSet.id)
            )
        )
        session.expunge_all()
        return rows
    finally:
        session.close()


def test_chunk_version_publishes_self_validating_json_and_ready_metadata(
    chunk_service_fixture: ChunkServiceFixture,
) -> None:
    fixture = chunk_service_fixture

    result = fixture.service().chunk_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert result.status == "ready"
    assert result.chunk_count >= 1
    assert result.text_chunk_count >= 1
    assert result.text_chunk_count + result.table_chunk_count == result.chunk_count
    assert "chunk_storage_key" not in result.model_dump()

    rows = _chunk_sets(fixture)
    assert len(rows) == 1
    row = rows[0]
    key = fixture.chunk_key(result.chunk_set_id)
    assert row.id == result.chunk_set_id
    assert row.status == "ready"
    assert row.attempt_count == 1
    assert row.chunk_storage_key == key
    assert row.output_sha256 == result.output_sha256
    assert row.chunk_count == result.chunk_count
    assert row.config_sha256 == result.config_sha256
    assert fixture.storage.exists(key)

    with fixture.storage.open(key) as stream:
        payload = stream.read()
    artifact = CanonicalChunkArtifact.model_validate_json(payload)
    assert artifact.chunk_set_id == result.chunk_set_id
    assert artifact.output_sha256 == result.output_sha256
    assert artifact.input.document_version_id == fixture.version_id
    assert artifact.statistics.chunk_count == result.chunk_count
    assert row.config_json == artifact.config.model_dump(mode="json")
    assert fixture.parsed_key.encode() not in payload
    assert b"synthetic-chunk-manual.pdf" not in payload

    session = fixture.runtime.session_factory()
    try:
        version = session.get(DocumentVersion, fixture.version_id)
        assert version is not None
        assert version.parse_status == "ready"
        assert version.index_status == "pending"
    finally:
        session.close()

    with pytest.raises(DocumentStateConflictError):
        fixture.service().chunk_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )
    assert fixture.storage.exists(key)
    assert _chunk_sets(fixture)[0].attempt_count == 1


def test_chunk_failure_is_safe_and_same_deterministic_set_can_retry(
    chunk_service_fixture: ChunkServiceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = chunk_service_fixture

    with monkeypatch.context() as patch:

        def fail_chunk(
            _self: StructureAwareDocumentChunker,
            _artifact: object,
        ) -> None:
            raise RuntimeError("D:/private/chunk detail")

        patch.setattr(StructureAwareDocumentChunker, "chunk", fail_chunk)
        with pytest.raises(DocumentChunkPublicationError) as error:
            fixture.service().chunk_version(
                fixture.user,
                document_id=fixture.document_id,
                version_id=fixture.version_id,
            )

    assert str(error.value) == "文档切块未能完成，请稍后重试"
    assert "private" not in str(error.value).lower()
    failed = _chunk_sets(fixture)[0]
    assert failed.status == "failed"
    assert failed.attempt_count == 1
    assert failed.error_message == "文档切块失败"
    assert failed.chunk_storage_key is None
    assert not fixture.storage.exists(fixture.chunk_key(failed.id))

    retried = fixture.service().chunk_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    ready = _chunk_sets(fixture)[0]
    assert retried.chunk_set_id == failed.id
    assert ready.status == "ready"
    assert ready.attempt_count == 2
    assert fixture.storage.exists(fixture.chunk_key(ready.id))


def test_database_completion_failure_compensates_and_reuses_exact_orphan(
    chunk_service_fixture: ChunkServiceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = chunk_service_fixture

    with monkeypatch.context() as patch:

        def fail_complete(*_args: object, **_kwargs: object) -> None:
            raise SQLAlchemyError("D:/private/database detail")

        patch.setattr(DocumentRepository, "complete_chunk_set", fail_complete)
        patch.setattr(fixture.storage, "delete", lambda _key: None)
        with pytest.raises(DocumentChunkPublicationError):
            fixture.service().chunk_version(
                fixture.user,
                document_id=fixture.document_id,
                version_id=fixture.version_id,
            )

    failed = _chunk_sets(fixture)[0]
    orphan_key = fixture.chunk_key(failed.id)
    assert failed.status == "failed"
    assert failed.chunk_storage_key is None
    assert fixture.storage.exists(orphan_key)

    retried = fixture.service().chunk_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    ready = _chunk_sets(fixture)[0]
    assert retried.chunk_set_id == failed.id
    assert ready.status == "ready"
    assert ready.attempt_count == 2
    assert ready.chunk_storage_key == orphan_key
    assert fixture.storage.exists(orphan_key)


def test_second_worker_cannot_claim_an_in_progress_chunk_set(
    chunk_service_fixture: ChunkServiceFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = chunk_service_fixture
    original_chunk = StructureAwareDocumentChunker.chunk
    competing_call_was_rejected = False

    def chunk_after_competing_claim(
        chunker: StructureAwareDocumentChunker,
        artifact: CanonicalParsedArtifact,
    ) -> DocumentChunkingResult:
        nonlocal competing_call_was_rejected
        with pytest.raises(DocumentStateConflictError):
            fixture.service().chunk_version(
                fixture.user,
                document_id=fixture.document_id,
                version_id=fixture.version_id,
            )
        competing_call_was_rejected = True
        return original_chunk(chunker, artifact)

    with monkeypatch.context() as patch:
        patch.setattr(
            StructureAwareDocumentChunker,
            "chunk",
            chunk_after_competing_claim,
        )
        result = fixture.service().chunk_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    assert competing_call_was_rejected is True
    row = _chunk_sets(fixture)[0]
    assert row.id == result.chunk_set_id
    assert row.status == "ready"
    assert row.attempt_count == 1


def test_non_owner_and_unready_version_cannot_create_chunk_set(
    chunk_service_fixture: ChunkServiceFixture,
) -> None:
    fixture = chunk_service_fixture
    stranger = fixture.user.model_copy(
        update={"user_id": uuid4(), "email": "stranger@example.com"}
    )

    with pytest.raises(DocumentNotFoundError):
        fixture.service().chunk_version(
            stranger,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )
    assert _chunk_sets(fixture) == []

    session = fixture.runtime.session_factory()
    try:
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == fixture.version_id)
            .values(
                parse_status="pending",
                parser_name=None,
                parser_version=None,
                parsed_storage_key=None,
            )
        )
        session.commit()
    finally:
        session.close()

    with pytest.raises(DocumentStateConflictError):
        fixture.service().chunk_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )
    assert _chunk_sets(fixture) == []


def test_tampered_parsed_artifact_fails_before_claim(
    chunk_service_fixture: ChunkServiceFixture,
) -> None:
    fixture = chunk_service_fixture
    fixture.storage.delete(fixture.parsed_key)
    fixture.storage.put(
        fixture.parsed_key,
        io.BytesIO(b'{"schema_version":"tampered"}'),
        "application/json",
    )

    with pytest.raises(DocumentChunkPublicationError):
        fixture.service().chunk_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    assert _chunk_sets(fixture) == []


def test_changed_config_creates_a_second_independent_ready_chunk_set(
    chunk_service_fixture: ChunkServiceFixture,
) -> None:
    fixture = chunk_service_fixture
    first = fixture.service().chunk_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    changed_settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=fixture.settings.local_storage_root,
        chunk_target_tokens=650,
    )
    second = fixture.service(settings=changed_settings).chunk_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert first.chunk_set_id != second.chunk_set_id
    assert first.config_sha256 != second.config_sha256
    rows = _chunk_sets(fixture)
    assert len(rows) == 2
    assert {row.status for row in rows} == {"ready"}
    assert all(row.attempt_count == 1 for row in rows)
    assert fixture.storage.exists(fixture.chunk_key(first.chunk_set_id))
    assert fixture.storage.exists(fixture.chunk_key(second.chunk_set_id))
