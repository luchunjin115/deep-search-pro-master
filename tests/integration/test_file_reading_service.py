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
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import FileNotFoundError, FileStateConflictError
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import Document, DocumentAcl, DocumentVersion, StoredFile
from app.repositories.files import FileRepository
from app.schemas.auth import CurrentUser
from app.schemas.files import ReadUploadedFileInput
from app.services.documents.parsers import PdfParser
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.quality import decide_parse_route
from app.services.documents.routing import RoutedParseResult
from app.services.file_reading import FileReadingService
from app.services.storage import LocalStorageBackend
from tests.fixtures.pdf_factory import make_text_pdf


@dataclass(slots=True)
class ReadingFixture:
    runtime: DatabaseRuntime
    settings: Settings
    storage: LocalStorageBackend
    session: Session
    tenant_id: UUID
    owner: CurrentUser
    acl_reader: CurrentUser
    file_id: UUID
    document_id: UUID
    version_id: UUID
    acl_id: UUID

    def service(self) -> FileReadingService:
        return FileReadingService(
            FileRepository(
                self.session,
                self.settings.database_statement_timeout_ms,
            ),
            self.storage,
            maximum_artifact_bytes=self.settings.file_read_max_artifact_bytes,
        )


@pytest.fixture
def reading_fixture(tmp_path: Path) -> ReadingFixture:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=tmp_path / "storage",
    )
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    storage = LocalStorageBackend(settings.local_storage_root)
    tenant_id = uuid4()
    owner_id = uuid4()
    reader_id = uuid4()
    file_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    acl_id = uuid4()
    owner = _current_user(tenant_id, owner_id, "owner")
    acl_reader = _current_user(tenant_id, reader_id, "reader")

    source = make_text_pdf(include_empty_page=False)
    source_sha256 = hashlib.sha256(source).hexdigest()
    parsed = PdfParser().parse(io.BytesIO(source))
    artifact = adapt_native_parse_result(parsed, source_sha256=source_sha256)
    quality = decide_parse_route(artifact)
    routed = RoutedParseResult(
        route=quality.route,
        reasons=quality.reasons,
        quality=quality,
        selected_artifact=artifact,
        native_artifact=artifact,
    )
    parsed_key = f"{tenant_id}/parsed/2026/09/{version_id}.json"
    storage.put(
        parsed_key,
        io.BytesIO(routed.model_dump_json().encode("utf-8")),
        "application/json",
    )

    session = runtime.session_factory()
    try:
        session.add(Tenant(id=tenant_id, name="M2-20.2 file reading tenant"))
        session.add_all(
            [
                User(
                    id=owner_id,
                    tenant_id=tenant_id,
                    email=owner.email,
                    display_name=owner.display_name,
                    password_hash="$argon2id$synthetic-file-reader-only",
                ),
                User(
                    id=reader_id,
                    tenant_id=tenant_id,
                    email=acl_reader.email,
                    display_name=acl_reader.display_name,
                    password_hash="$argon2id$synthetic-file-reader-only",
                ),
            ]
        )
        session.flush()
        session.add(
            StoredFile(
                id=file_id,
                tenant_id=tenant_id,
                owner_user_id=owner_id,
                original_name="synthetic-authorized-manual.pdf",
                storage_key=f"{tenant_id}/uploads/2026/09/{file_id}.pdf",
                extension=".pdf",
                mime_type="application/pdf",
                size_bytes=len(source),
                sha256=source_sha256,
                category="uploads",
                status="parsing",
            )
        )
        session.add(
            Document(
                id=document_id,
                tenant_id=tenant_id,
                owner_user_id=owner_id,
                title="M2-20.2合成获权文件",
                document_type="product_manual",
                language="zh-CN",
                market="DE",
                access_level="restricted",
            )
        )
        session.flush()
        session.add(
            DocumentVersion(
                id=version_id,
                tenant_id=tenant_id,
                document_id=document_id,
                file_id=file_id,
                version_no=1,
                content_hash=source_sha256,
                parser_name="pymupdf",
                parser_version="synthetic-test-v1",
                parsed_storage_key=parsed_key,
                parse_status="ready",
                index_status="pending",
            )
        )
        session.flush()
        session.add(
            DocumentAcl(
                id=acl_id,
                tenant_id=tenant_id,
                document_id=document_id,
                subject_type="user",
                user_id=reader_id,
                permission="read",
            )
        )
        session.commit()
        yield ReadingFixture(
            runtime=runtime,
            settings=settings,
            storage=storage,
            session=session,
            tenant_id=tenant_id,
            owner=owner,
            acl_reader=acl_reader,
            file_id=file_id,
            document_id=document_id,
            version_id=version_id,
            acl_id=acl_id,
        )
    finally:
        session.rollback()
        cleanup = runtime.session_factory()
        try:
            cleanup.execute(
                delete(DocumentAcl).where(DocumentAcl.tenant_id == tenant_id)
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
            session.close()
            runtime.engine.dispose()


def _current_user(tenant_id: UUID, user_id: UUID, label: str) -> CurrentUser:
    return CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        email=f"file-{label}@example.com",
        display_name=f"File {label.title()}",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def test_real_repository_and_storage_allow_owner_and_current_user_acl(
    reading_fixture: ReadingFixture,
) -> None:
    fixture = reading_fixture
    request = ReadUploadedFileInput(
        file_id=fixture.file_id,
        locator={"source_type": "pdf", "page_start": 1},
    )

    owner_result = fixture.service().read_uploaded_file(fixture.owner, request)
    acl_result = fixture.service().read_uploaded_file(fixture.acl_reader, request)

    assert owner_result.document_id == fixture.document_id
    assert owner_result.version_id == fixture.version_id
    assert owner_result.is_active_version is False
    assert acl_result.sections == owner_result.sections
    assert "parsed" not in owner_result.model_dump_json().lower()


def test_real_query_hides_cross_tenant_revoked_acl_and_soft_deleted_document(
    reading_fixture: ReadingFixture,
) -> None:
    fixture = reading_fixture
    request = ReadUploadedFileInput(file_id=fixture.file_id)
    cross_tenant = fixture.acl_reader.model_copy(
        update={"tenant_id": uuid4(), "email": "cross-tenant@example.com"}
    )
    with pytest.raises(FileNotFoundError):
        fixture.service().read_uploaded_file(cross_tenant, request)

    fixture.session.execute(delete(DocumentAcl).where(DocumentAcl.id == fixture.acl_id))
    fixture.session.commit()
    with pytest.raises(FileNotFoundError):
        fixture.service().read_uploaded_file(fixture.acl_reader, request)

    document = fixture.session.get(Document, fixture.document_id)
    assert document is not None
    document.deleted_at = datetime.now(UTC)
    fixture.session.commit()
    with pytest.raises(FileNotFoundError):
        fixture.service().read_uploaded_file(fixture.owner, request)


def test_real_query_returns_safe_state_conflict_for_authorized_pending_version(
    reading_fixture: ReadingFixture,
) -> None:
    fixture = reading_fixture
    version = fixture.session.get(DocumentVersion, fixture.version_id)
    assert version is not None
    version.parse_status = "pending"
    fixture.session.commit()

    with pytest.raises(FileStateConflictError):
        fixture.service().read_uploaded_file(
            fixture.owner,
            ReadUploadedFileInput(file_id=fixture.file_id),
        )
