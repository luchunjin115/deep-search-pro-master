"""Fixed tenant/owner/ACL-scoped file metadata queries for M2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, false, not_, or_, select, true
from sqlalchemy.orm import Session

from app.models.knowledge import Document, DocumentVersion, StoredFile
from app.repositories.common import apply_statement_timeout
from app.repositories.documents import document_access_clause


@dataclass(frozen=True, slots=True)
class ReadableParsedFile:
    """Authorized file/version facts; the private key stays inside services."""

    file_id: UUID
    document_id: UUID
    version_id: UUID
    version_no: int
    original_name: str
    extension: str
    sha256: str
    content_hash: str
    parse_status: str
    parsed_storage_key: str | None
    is_active_version: bool


class FileRepository:
    """Persist file rows and hide cross-tenant, unauthorized, or deleted objects."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def create_file(
        self,
        *,
        file_id: UUID,
        tenant_id: UUID,
        owner_user_id: UUID,
        original_name: str,
        storage_key: str,
        extension: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        category: str,
    ) -> StoredFile:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row = StoredFile(
            id=file_id,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            original_name=original_name,
            storage_key=storage_key,
            extension=extension,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            category=category,
            status="uploaded",
        )
        self._session.add(row)
        self._session.flush()
        return row

    def find_owned_unlinked_file(
        self,
        *,
        tenant_id: UUID,
        owner_user_id: UUID,
        file_id: UUID,
    ) -> StoredFile | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        linked = exists(
            select(DocumentVersion.id).where(
                DocumentVersion.tenant_id == StoredFile.tenant_id,
                DocumentVersion.file_id == StoredFile.id,
            )
        )
        return self._session.scalar(
            select(StoredFile).where(
                StoredFile.id == file_id,
                StoredFile.tenant_id == tenant_id,
                StoredFile.owner_user_id == owner_user_id,
                StoredFile.status == "uploaded",
                StoredFile.deleted_at.is_(None),
                not_(linked),
            )
        )

    def find_manageable_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        company_owner: bool,
        file_id: UUID,
    ) -> StoredFile | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        ownership = true() if company_owner else StoredFile.owner_user_id == user_id
        return self._session.scalar(
            select(StoredFile).where(
                StoredFile.id == file_id,
                StoredFile.tenant_id == tenant_id,
                StoredFile.status != "soft_deleted",
                StoredFile.deleted_at.is_(None),
                ownership,
            )
        )

    def _access_conditions(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
    ) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
        any_linked_document = exists(
            select(DocumentVersion.id).where(
                DocumentVersion.tenant_id == StoredFile.tenant_id,
                DocumentVersion.file_id == StoredFile.id,
            )
        )
        accessible_linked_document = exists(
            select(DocumentVersion.id)
            .join(
                Document,
                and_(
                    Document.tenant_id == DocumentVersion.tenant_id,
                    Document.id == DocumentVersion.document_id,
                ),
            )
            .where(
                DocumentVersion.tenant_id == StoredFile.tenant_id,
                DocumentVersion.file_id == StoredFile.id,
                Document.deleted_at.is_(None),
                document_access_clause(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role_names=role_names,
                    market_scopes=market_scopes,
                    company_owner="company_owner" in role_names,
                ),
            )
        )
        standalone_access = and_(
            not_(any_linked_document),
            or_(
                StoredFile.owner_user_id == user_id,
                true() if "company_owner" in role_names else false(),
            ),
        )
        return standalone_access, accessible_linked_document

    def find_accessible_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        file_id: UUID,
    ) -> StoredFile | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        access = self._access_conditions(
            tenant_id=tenant_id,
            user_id=user_id,
            role_names=role_names,
            market_scopes=market_scopes,
        )
        return self._session.scalar(
            select(StoredFile).where(
                StoredFile.id == file_id,
                StoredFile.tenant_id == tenant_id,
                StoredFile.status != "soft_deleted",
                StoredFile.deleted_at.is_(None),
                or_(*access),
            )
        )

    def find_readable_parsed_file(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        file_id: UUID,
    ) -> ReadableParsedFile | None:
        """Fetch one linked version and authorize its document in the same query."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row = self._session.execute(
            select(
                StoredFile.id,
                Document.id,
                DocumentVersion.id,
                DocumentVersion.version_no,
                StoredFile.original_name,
                StoredFile.extension,
                StoredFile.sha256,
                DocumentVersion.content_hash,
                DocumentVersion.parse_status,
                DocumentVersion.parsed_storage_key,
                Document.active_version_id,
            )
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.tenant_id == StoredFile.tenant_id,
                    DocumentVersion.file_id == StoredFile.id,
                ),
            )
            .join(
                Document,
                and_(
                    Document.tenant_id == DocumentVersion.tenant_id,
                    Document.id == DocumentVersion.document_id,
                ),
            )
            .where(
                StoredFile.id == file_id,
                StoredFile.tenant_id == tenant_id,
                StoredFile.status != "soft_deleted",
                StoredFile.deleted_at.is_(None),
                Document.deleted_at.is_(None),
                document_access_clause(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role_names=role_names,
                    market_scopes=market_scopes,
                    company_owner="company_owner" in role_names,
                ),
            )
        ).one_or_none()
        if row is None:
            return None
        return ReadableParsedFile(
            file_id=row[0],
            document_id=row[1],
            version_id=row[2],
            version_no=row[3],
            original_name=row[4],
            extension=row[5],
            sha256=row[6],
            content_hash=row[7],
            parse_status=row[8],
            parsed_storage_key=row[9],
            is_active_version=row[10] == row[2],
        )

    def list_accessible(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        limit: int,
    ) -> list[StoredFile]:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        access = self._access_conditions(
            tenant_id=tenant_id,
            user_id=user_id,
            role_names=role_names,
            market_scopes=market_scopes,
        )
        statement = (
            select(StoredFile)
            .where(
                StoredFile.tenant_id == tenant_id,
                StoredFile.status != "soft_deleted",
                StoredFile.deleted_at.is_(None),
                or_(*access),
            )
            .order_by(StoredFile.created_at.desc(), StoredFile.id)
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def update_state(
        self,
        row: StoredFile,
        *,
        status: str,
        error_message: str | None,
        deleted_at: datetime | None,
    ) -> StoredFile:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row.status = status
        row.error_message = error_message
        row.deleted_at = deleted_at
        self._session.flush()
        return row
