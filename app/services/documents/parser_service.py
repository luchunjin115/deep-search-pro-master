"""Transactional document parsing, immutable publication, and compensation."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    DocumentNotFoundError,
    DocumentParsingError,
    DocumentStateConflictError,
    FileNotFoundError,
    FileStateConflictError,
    KnowledgePersistenceError,
)
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.schemas.auth import CurrentUser
from app.schemas.files import FileStateUpdate
from app.schemas.knowledge import ParsedDocumentPublication
from app.services.documents.routing import DocumentParserRouter
from app.services.files import FileService
from app.services.storage import StorageBackend, StorageError

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.documents.parsers.docling import DoclingProvider

_JSON_CONTENT_TYPE = "application/json"
_FAILURE_MESSAGE = "文档解析失败"


@dataclass(frozen=True, slots=True)
class _ParseClaim:
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    file_id: UUID
    source_name: str
    source_storage_key: str
    expected_sha256: str
    expected_size_bytes: int


class DocumentParserService:
    """Own short DB transactions around potentially slow parser execution."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: StorageBackend,
        settings: Settings,
        *,
        docling_provider: DoclingProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._settings = settings
        self._router = DocumentParserRouter(
            settings,
            docling_provider=docling_provider,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def parse_version(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> ParsedDocumentPublication:
        """Claim, parse, publish, and close one version without indexing it."""

        claim = self._claim(user, document_id=document_id, version_id=version_id)
        published_key: str | None = None
        try:
            content = self._read_claimed_source(claim)
            routed = self._router.parse(
                source_name=claim.source_name,
                content=content,
            )
            payload = routed.model_dump_json().encode("utf-8")
            published_key = self._parsed_key(claim)
            stored = self._storage.put(
                published_key,
                io.BytesIO(payload),
                _JSON_CONTENT_TYPE,
            )
            expected_publication_hash = hashlib.sha256(payload).hexdigest()
            if (
                stored.key != published_key
                or stored.size_bytes != len(payload)
                or stored.sha256 != expected_publication_hash
                or stored.content_type != _JSON_CONTENT_TYPE
            ):
                raise DocumentParsingError

            selected = routed.selected_artifact
            publication = ParsedDocumentPublication(
                version_id=claim.version_id,
                route=routed.route,
                parser_provider=selected.parser.provider,
                parser_name=selected.parser.name,
                parser_version=selected.parser.version,
                artifact_content_sha256=selected.content_sha256,
                published_sha256=stored.sha256,
                warning_count=len(selected.warnings),
            )
            self._complete(
                claim,
                parser_name=selected.parser.name,
                parser_version=selected.parser.version,
                parsed_storage_key=published_key,
            )
            return publication
        except Exception:  # noqa: BLE001 - all post-claim failures close safely.
            if published_key is not None:
                try:
                    self._storage.delete(published_key)
                except StorageError:
                    pass
            self._record_failure(user, claim)
            raise DocumentParsingError from None

    def _claim(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> _ParseClaim:
        session = self._session_factory()
        try:
            documents = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            document = documents.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                document_id=document_id,
            )
            if document is None:
                raise DocumentNotFoundError
            version = documents.claim_parse(
                tenant_id=user.tenant_id,
                document_id=document_id,
                version_id=version_id,
            )
            if version is None:
                if documents.find_version(
                    tenant_id=user.tenant_id,
                    document_id=document_id,
                    version_id=version_id,
                ) is None:
                    raise DocumentNotFoundError
                raise DocumentStateConflictError

            files = FileRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            file_row = files.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                file_id=version.file_id,
            )
            if file_row is None:
                raise FileNotFoundError
            file_service = FileService(files, self._storage)
            if file_row.status in {"uploaded", "failed"}:
                file_service.transition_file(
                    user,
                    file_row.id,
                    FileStateUpdate(status="validating"),
                )
                file_row.status = "validating"
            if file_row.status == "validating":
                file_service.transition_file(
                    user,
                    file_row.id,
                    FileStateUpdate(status="parsing"),
                )
                file_row.status = "parsing"
            if file_row.status != "parsing":
                raise FileStateConflictError

            claim = _ParseClaim(
                tenant_id=user.tenant_id,
                document_id=document_id,
                version_id=version.id,
                file_id=file_row.id,
                source_name=file_row.original_name,
                source_storage_key=file_row.storage_key,
                expected_sha256=version.content_hash,
                expected_size_bytes=file_row.size_bytes,
            )
            session.commit()
            return claim
        except (
            DocumentNotFoundError,
            DocumentStateConflictError,
            FileNotFoundError,
            FileStateConflictError,
        ):
            session.rollback()
            raise
        except SQLAlchemyError:
            session.rollback()
            raise KnowledgePersistenceError from None
        finally:
            session.close()

    def _read_claimed_source(self, claim: _ParseClaim) -> bytes:
        try:
            with self._storage.open(claim.source_storage_key) as stream:
                content = stream.read(self._settings.upload_max_file_size_bytes + 1)
        except StorageError:
            raise DocumentParsingError from None
        if (
            not isinstance(content, bytes)
            or len(content) != claim.expected_size_bytes
            or len(content) > self._settings.upload_max_file_size_bytes
            or hashlib.sha256(content).hexdigest() != claim.expected_sha256
        ):
            raise DocumentParsingError
        return content

    def _parsed_key(self, claim: _ParseClaim) -> str:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise DocumentParsingError
        return (
            f"{claim.tenant_id}/parsed/{now:%Y}/{now:%m}/"
            f"{claim.version_id}.json"
        )

    def _complete(
        self,
        claim: _ParseClaim,
        *,
        parser_name: str,
        parser_version: str,
        parsed_storage_key: str,
    ) -> None:
        session = self._session_factory()
        try:
            row = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).complete_parse(
                tenant_id=claim.tenant_id,
                document_id=claim.document_id,
                version_id=claim.version_id,
                parser_name=parser_name,
                parser_version=parser_version,
                parsed_storage_key=parsed_storage_key,
            )
            if row is None:
                raise DocumentStateConflictError
            session.commit()
        except DocumentStateConflictError:
            session.rollback()
            raise
        except SQLAlchemyError:
            session.rollback()
            raise KnowledgePersistenceError from None
        finally:
            session.close()

    def _record_failure(self, user: CurrentUser, claim: _ParseClaim) -> None:
        session = self._session_factory()
        try:
            DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).fail_parse(
                tenant_id=claim.tenant_id,
                document_id=claim.document_id,
                version_id=claim.version_id,
            )
            files = FileRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            file_row = files.find_manageable_by_id(
                tenant_id=claim.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                file_id=claim.file_id,
            )
            if file_row is not None and file_row.status == "parsing":
                files.update_state(
                    file_row,
                    status="failed",
                    error_message=_FAILURE_MESSAGE,
                    deleted_at=None,
                )
            session.commit()
        except Exception:  # noqa: BLE001 - preserve the original safe failure.
            session.rollback()
        finally:
            session.close()
