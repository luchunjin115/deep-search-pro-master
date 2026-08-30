from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import (
    DocumentNotFoundError,
    DocumentParsingError,
    DocumentStateConflictError,
)
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import Document, DocumentVersion, StoredFile
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.schemas.auth import CurrentUser
from app.schemas.files import FileStateUpdate
from app.schemas.knowledge import (
    DocumentCreateInput,
    DocumentIndexStateUpdate,
    DocumentVersionCreateInput,
)
from app.services.documents import DocumentParserService, DocumentService
from app.services.documents.routing import RoutedParseResult
from app.services.files import FileService
from app.services.storage import LocalStorageBackend
from tests.fixtures.pdf_factory import make_text_pdf


@dataclass(slots=True)
class ParserFixture:
    runtime: DatabaseRuntime
    settings: Settings
    storage: LocalStorageBackend
    user: CurrentUser
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    file_id: UUID
    source_key: str
    source: bytes

    @property
    def parsed_key(self) -> str:
        return (
            f"{self.tenant_id}/parsed/2026/08/"
            f"{self.version_id}.json"
        )

    def parser(self) -> DocumentParserService:
        return DocumentParserService(
            self.runtime.session_factory,
            self.storage,
            self.settings,
            clock=lambda: datetime(2026, 8, 30, tzinfo=UTC),
        )


@pytest.fixture
def parser_fixture(tmp_path: Path) -> ParserFixture:
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
        email="parser-owner@example.com",
        display_name="Parser Owner",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )
    source = make_text_pdf(include_empty_page=False)

    session = runtime.session_factory()
    try:
        session.add(Tenant(id=tenant_id, name="M2-11.5 parser tenant"))
        session.add(
            User(
                id=user_id,
                tenant_id=tenant_id,
                email=user.email,
                display_name=user.display_name,
                password_hash="$argon2id$synthetic-parser-only",
            )
        )
        session.flush()
        files = FileService(
            FileRepository(session, settings.database_statement_timeout_ms),
            storage,
        )
        uploaded = files.upload_file(
            user,
            original_name="synthetic-parser-manual.pdf",
            declared_content_type="application/pdf",
            stream=io.BytesIO(source),
            allowed_extensions=settings.upload_allowed_extensions,
            max_size_bytes=settings.upload_max_file_size_bytes,
        )
        documents = DocumentService(
            DocumentRepository(session, settings.database_statement_timeout_ms),
            files,
        )
        detail = documents.create_document(
            user,
            DocumentCreateInput(
                file_id=uploaded.response.file_id,
                title="M2-11.5合成解析说明书",
                document_type="product_manual",
                language="zh-CN",
                market="DE",
            ),
        )
        session.commit()
        fixture = ParserFixture(
            runtime=runtime,
            settings=settings,
            storage=storage,
            user=user,
            tenant_id=tenant_id,
            document_id=detail.document_id,
            version_id=detail.versions[0].version_id,
            file_id=uploaded.response.file_id,
            source_key=uploaded.storage_key,
            source=source,
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


def _database_rows(
    factory: sessionmaker[Session],
    fixture: ParserFixture,
) -> tuple[Document, DocumentVersion, StoredFile]:
    session = factory()
    try:
        document = session.get(Document, fixture.document_id)
        version = session.get(DocumentVersion, fixture.version_id)
        file_row = session.get(StoredFile, fixture.file_id)
        assert document is not None
        assert version is not None
        assert file_row is not None
        session.expunge_all()
        return document, version, file_row
    finally:
        session.close()


def test_parse_version_publishes_auditable_json_and_ready_state(
    parser_fixture: ParserFixture,
) -> None:
    fixture = parser_fixture

    result = fixture.parser().parse_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )

    assert result.parse_status == "ready"
    assert result.route == "native"
    assert result.parser_provider == "native"
    assert result.parser_name == "pymupdf"
    assert "parsed_storage_key" not in result.model_dump()
    document, version, file_row = _database_rows(fixture.runtime.session_factory, fixture)
    assert version.parse_status == "ready"
    assert version.parsed_storage_key == fixture.parsed_key
    assert version.parser_name == result.parser_name
    assert version.parser_version == result.parser_version
    assert file_row.status == "parsing"
    assert document.active_version_id is None

    with fixture.storage.open(fixture.parsed_key) as stream:
        payload = stream.read()
    published = RoutedParseResult.model_validate_json(payload)
    assert published.schema_version == "m2-routed-parsed-document-v1"
    assert published.selected_artifact.source_sha256 == hashlib.sha256(
        fixture.source
    ).hexdigest()
    assert published.selected_artifact.content_sha256 == (
        result.artifact_content_sha256
    )
    assert hashlib.sha256(payload).hexdigest() == result.published_sha256
    assert fixture.source_key.encode() not in payload
    assert b"synthetic-parser-manual.pdf" not in payload

    with pytest.raises(DocumentStateConflictError):
        fixture.parser().parse_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )
    assert fixture.storage.exists(fixture.parsed_key)


def test_source_failure_marks_failed_and_same_version_can_retry(
    parser_fixture: ParserFixture,
) -> None:
    fixture = parser_fixture
    fixture.storage.delete(fixture.source_key)

    with pytest.raises(DocumentParsingError) as error:
        fixture.parser().parse_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    assert str(error.value) == "文档解析未能完成，请稍后重试"
    _document, version, file_row = _database_rows(
        fixture.runtime.session_factory,
        fixture,
    )
    assert version.parse_status == "failed"
    assert version.parser_name is None
    assert version.parsed_storage_key is None
    assert file_row.status == "failed"
    assert file_row.error_message == "文档解析失败"
    assert not fixture.storage.exists(fixture.parsed_key)

    fixture.storage.put(
        fixture.source_key,
        io.BytesIO(fixture.source),
        "application/pdf",
    )
    retried = fixture.parser().parse_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    assert retried.parse_status == "ready"
    assert fixture.storage.exists(fixture.parsed_key)


def test_database_failure_after_publication_is_compensated_and_retryable(
    parser_fixture: ParserFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = parser_fixture

    with monkeypatch.context() as patch:
        def fail_complete(*_args: object, **_kwargs: object) -> None:
            raise SQLAlchemyError("D:/private/database detail")

        patch.setattr(DocumentRepository, "complete_parse", fail_complete)
        with pytest.raises(DocumentParsingError) as error:
            fixture.parser().parse_version(
                fixture.user,
                document_id=fixture.document_id,
                version_id=fixture.version_id,
            )

    assert "private" not in str(error.value).lower()
    assert not fixture.storage.exists(fixture.parsed_key)
    _document, version, file_row = _database_rows(
        fixture.runtime.session_factory,
        fixture,
    )
    assert version.parse_status == "failed"
    assert version.parsed_storage_key is None
    assert file_row.status == "failed"

    retried = fixture.parser().parse_version(
        fixture.user,
        document_id=fixture.document_id,
        version_id=fixture.version_id,
    )
    assert retried.parse_status == "ready"
    assert fixture.storage.exists(fixture.parsed_key)


def test_non_owner_cannot_claim_parse_or_change_existing_state(
    parser_fixture: ParserFixture,
) -> None:
    fixture = parser_fixture
    stranger = fixture.user.model_copy(
        update={
            "user_id": uuid4(),
            "email": "stranger@example.com",
        }
    )

    with pytest.raises(DocumentNotFoundError):
        fixture.parser().parse_version(
            stranger,
            document_id=fixture.document_id,
            version_id=fixture.version_id,
        )

    document, version, file_row = _database_rows(
        fixture.runtime.session_factory,
        fixture,
    )
    assert document.active_version_id is None
    assert version.parse_status == "pending"
    assert file_row.status == "uploaded"
    assert not fixture.storage.exists(fixture.parsed_key)


def test_failed_new_version_never_replaces_the_old_active_version(
    parser_fixture: ParserFixture,
) -> None:
    fixture = parser_fixture
    fixture.parser().parse_version(
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
        documents = DocumentService(
            DocumentRepository(
                session,
                fixture.settings.database_statement_timeout_ms,
            ),
            files,
        )
        files.transition_file(
            fixture.user,
            fixture.file_id,
            FileStateUpdate(status="indexing"),
        )
        documents.transition_index_state(
            fixture.user,
            fixture.document_id,
            fixture.version_id,
            DocumentIndexStateUpdate(status="indexing"),
        )
        documents.transition_index_state(
            fixture.user,
            fixture.document_id,
            fixture.version_id,
            DocumentIndexStateUpdate(status="ready"),
        )
        files.transition_file(
            fixture.user,
            fixture.file_id,
            FileStateUpdate(status="ready"),
        )
        active = documents.activate_version(
            fixture.user,
            fixture.document_id,
            fixture.version_id,
        )
        assert active.active_version_id == fixture.version_id

        next_source = make_text_pdf(include_empty_page=True)
        next_upload = files.upload_file(
            fixture.user,
            original_name="synthetic-parser-manual-v2.pdf",
            declared_content_type="application/pdf",
            stream=io.BytesIO(next_source),
            allowed_extensions=fixture.settings.upload_allowed_extensions,
            max_size_bytes=fixture.settings.upload_max_file_size_bytes,
        )
        next_version = documents.add_version(
            fixture.user,
            fixture.document_id,
            DocumentVersionCreateInput(file_id=next_upload.response.file_id),
        )
        session.commit()
    finally:
        session.close()

    fixture.storage.delete(next_upload.storage_key)
    with pytest.raises(DocumentParsingError):
        fixture.parser().parse_version(
            fixture.user,
            document_id=fixture.document_id,
            version_id=next_version.version_id,
        )

    check = fixture.runtime.session_factory()
    try:
        document = check.get(Document, fixture.document_id)
        failed_version = check.get(DocumentVersion, next_version.version_id)
        assert document is not None
        assert failed_version is not None
        assert document.active_version_id == fixture.version_id
        assert failed_version.parse_status == "failed"
        assert failed_version.parsed_storage_key is None
        assert fixture.storage.exists(fixture.parsed_key)
    finally:
        check.close()
