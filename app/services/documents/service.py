"""Document creation, ACL, version state, and active-version rules for M2."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import (
    DocumentAclConflictError,
    DocumentNotFoundError,
    DocumentStateConflictError,
    DocumentVersionConflictError,
    KnowledgeDataContractError,
    KnowledgePersistenceError,
)
from app.models.knowledge import Document, DocumentAcl, DocumentVersion
from app.schemas.auth import CurrentUser
from app.schemas.common import MarketCode, RoleName
from app.schemas.knowledge import (
    AccessLevel,
    AclSubjectType,
    DocumentAclGrantInput,
    DocumentAclResponse,
    DocumentCreateInput,
    DocumentDetailResponse,
    DocumentIndexStateUpdate,
    DocumentParseStateUpdate,
    DocumentResponse,
    DocumentVersionCreateInput,
    DocumentVersionResponse,
    IndexStatus,
    ParseStatus,
)
from app.services.files import FileService
from app.services.storage import StorageError, validate_storage_key

PARSE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"parsing"}),
    "parsing": frozenset({"ready", "failed"}),
    "failed": frozenset({"parsing"}),
    "ready": frozenset(),
}
INDEX_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"indexing"}),
    "indexing": frozenset({"ready", "failed"}),
    "failed": frozenset({"indexing"}),
    "ready": frozenset(),
}


class DocumentStore(Protocol):
    def create_initial(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        tenant_id: UUID,
        owner_user_id: UUID,
        file_id: UUID,
        title: str,
        document_type: str,
        language: str | None,
        market: str | None,
        product_id: UUID | None,
        access_level: str,
        content_hash: str,
    ) -> tuple[Document, DocumentVersion]: ...

    def find_accessible_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        document_id: UUID,
    ) -> Document | None: ...

    def find_manageable_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        company_owner: bool,
        document_id: UUID,
    ) -> Document | None: ...

    def list_versions(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> list[DocumentVersion]: ...

    def list_acl(self, *, tenant_id: UUID, document_id: UUID) -> list[DocumentAcl]: ...

    def find_version(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None: ...

    def find_version_by_hash(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        content_hash: str,
    ) -> DocumentVersion | None: ...

    def add_version(
        self,
        *,
        version_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        file_id: UUID,
        content_hash: str,
    ) -> DocumentVersion: ...

    def find_acl(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        subject_type: str,
        role_name: str | None,
        user_id: UUID | None,
        market_code: str | None,
    ) -> DocumentAcl | None: ...

    def acl_subject_exists(
        self,
        *,
        tenant_id: UUID,
        subject_type: str,
        role_name: str | None,
        user_id: UUID | None,
        market_code: str | None,
    ) -> bool: ...

    def add_acl(
        self,
        *,
        acl_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        subject_type: str,
        role_name: str | None,
        user_id: UUID | None,
        market_code: str | None,
    ) -> DocumentAcl: ...

    def update_parse_state(
        self,
        row: DocumentVersion,
        *,
        status: str,
        parser_name: str | None,
        parser_version: str | None,
        parsed_storage_key: str | None,
    ) -> DocumentVersion: ...

    def update_index_state(
        self,
        row: DocumentVersion,
        *,
        status: str,
    ) -> DocumentVersion: ...

    def activate_version(
        self, document: Document, version: DocumentVersion
    ) -> Document: ...

    def soft_delete(self, document: Document, *, deleted_at: datetime) -> Document: ...


class DocumentService:
    """Apply owner/ACL and deterministic version-state rules around repositories."""

    def __init__(self, repository: DocumentStore, file_service: FileService) -> None:
        self._repository = repository
        self._file_service = file_service

    def create_document(
        self,
        user: CurrentUser,
        request: DocumentCreateInput,
    ) -> DocumentDetailResponse:
        file_row = self._file_service.require_owned_unlinked_file(user, request.file_id)
        try:
            document, _version = self._repository.create_initial(
                document_id=uuid4(),
                version_id=uuid4(),
                tenant_id=user.tenant_id,
                owner_user_id=user.user_id,
                file_id=file_row.id,
                title=request.title,
                document_type=request.document_type,
                language=request.language,
                market=request.market,
                product_id=request.product_id,
                access_level=request.access_level,
                content_hash=file_row.sha256,
            )
            return self._detail(user, document)
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def get_document(
        self,
        user: CurrentUser,
        document_id: UUID,
    ) -> DocumentDetailResponse:
        try:
            row = self._repository.find_accessible_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                role_names=tuple(user.roles),
                market_scopes=tuple(user.market_scopes),
                document_id=document_id,
            )
            if row is None:
                raise DocumentNotFoundError
            return self._detail(user, row)
        except DocumentNotFoundError:
            raise
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def add_version(
        self,
        user: CurrentUser,
        document_id: UUID,
        request: DocumentVersionCreateInput,
    ) -> DocumentVersionResponse:
        document = self._require_manageable(user, document_id)
        file_row = self._file_service.require_owned_unlinked_file(user, request.file_id)
        try:
            duplicate = self._repository.find_version_by_hash(
                tenant_id=user.tenant_id,
                document_id=document.id,
                content_hash=file_row.sha256,
            )
            if duplicate is not None:
                raise DocumentVersionConflictError
            version = self._repository.add_version(
                version_id=uuid4(),
                tenant_id=user.tenant_id,
                document_id=document.id,
                file_id=file_row.id,
                content_hash=file_row.sha256,
            )
            return self._version_response(version)
        except DocumentVersionConflictError:
            raise
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def grant_acl(
        self,
        user: CurrentUser,
        document_id: UUID,
        request: DocumentAclGrantInput,
    ) -> DocumentAclResponse:
        document = self._require_manageable(user, document_id)
        try:
            duplicate = self._repository.find_acl(
                tenant_id=user.tenant_id,
                document_id=document.id,
                subject_type=request.subject_type,
                role_name=request.role_name,
                user_id=request.user_id,
                market_code=request.market_code,
            )
            if duplicate is not None:
                raise DocumentAclConflictError
            if not self._repository.acl_subject_exists(
                tenant_id=user.tenant_id,
                subject_type=request.subject_type,
                role_name=request.role_name,
                user_id=request.user_id,
                market_code=request.market_code,
            ):
                raise DocumentAclConflictError
            row = self._repository.add_acl(
                acl_id=uuid4(),
                tenant_id=user.tenant_id,
                document_id=document.id,
                subject_type=request.subject_type,
                role_name=request.role_name,
                user_id=request.user_id,
                market_code=request.market_code,
            )
            return self._acl_response(row)
        except DocumentAclConflictError:
            raise
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def transition_parse_state(
        self,
        user: CurrentUser,
        document_id: UUID,
        version_id: UUID,
        request: DocumentParseStateUpdate,
    ) -> DocumentVersionResponse:
        self._require_manageable(user, document_id)
        version = self._require_version(user, document_id, version_id)
        if request.status not in PARSE_TRANSITIONS.get(
            version.parse_status, frozenset()
        ):
            raise DocumentStateConflictError
        if request.status == "ready":
            self._validate_parsed_key(user.tenant_id, version.id, request)
        try:
            updated = self._repository.update_parse_state(
                version,
                status=request.status,
                parser_name=request.parser_name,
                parser_version=request.parser_version,
                parsed_storage_key=request.parsed_storage_key,
            )
            return self._version_response(updated)
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def transition_index_state(
        self,
        user: CurrentUser,
        document_id: UUID,
        version_id: UUID,
        request: DocumentIndexStateUpdate,
    ) -> DocumentVersionResponse:
        self._require_manageable(user, document_id)
        version = self._require_version(user, document_id, version_id)
        if request.status not in INDEX_TRANSITIONS.get(
            version.index_status, frozenset()
        ):
            raise DocumentStateConflictError
        if request.status == "indexing" and version.parse_status != "ready":
            raise DocumentStateConflictError
        try:
            updated = self._repository.update_index_state(
                version,
                status=request.status,
            )
            return self._version_response(updated)
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def activate_version(
        self,
        user: CurrentUser,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentResponse:
        document = self._require_manageable(user, document_id)
        version = self._require_version(user, document_id, version_id)
        if version.parse_status != "ready" or version.index_status != "ready":
            raise DocumentStateConflictError
        file_row = self._file_service.require_manageable_file(user, version.file_id)
        if file_row.status != "ready":
            raise DocumentStateConflictError
        try:
            return self._document_response(
                self._repository.activate_version(document, version)
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def soft_delete_document(
        self,
        user: CurrentUser,
        document_id: UUID,
    ) -> None:
        document = self._require_manageable(user, document_id)
        try:
            self._repository.soft_delete(document, deleted_at=datetime.now(UTC))
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def _require_manageable(self, user: CurrentUser, document_id: UUID) -> Document:
        try:
            row = self._repository.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                document_id=document_id,
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        if row is None:
            raise DocumentNotFoundError
        return row

    def _require_version(
        self,
        user: CurrentUser,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion:
        try:
            row = self._repository.find_version(
                tenant_id=user.tenant_id,
                document_id=document_id,
                version_id=version_id,
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        if row is None:
            raise DocumentNotFoundError
        return row

    def _detail(
        self,
        user: CurrentUser,
        document: Document,
    ) -> DocumentDetailResponse:
        try:
            versions = self._repository.list_versions(
                tenant_id=user.tenant_id,
                document_id=document.id,
            )
            can_manage = (
                document.owner_user_id == user.user_id or "company_owner" in user.roles
            )
            acl = (
                self._repository.list_acl(
                    tenant_id=user.tenant_id,
                    document_id=document.id,
                )
                if can_manage
                else []
            )
            return DocumentDetailResponse(
                **self._document_response(document).model_dump(),
                versions=[self._version_response(version) for version in versions],
                acl=[self._acl_response(entry) for entry in acl],
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    @staticmethod
    def _validate_parsed_key(
        tenant_id: UUID,
        version_id: UUID,
        request: DocumentParseStateUpdate,
    ) -> None:
        try:
            key = validate_storage_key(request.parsed_storage_key or "")
        except StorageError:
            raise DocumentStateConflictError from None
        parts = key.split("/")
        if (
            parts[0] != str(tenant_id)
            or parts[1] != "parsed"
            or parts[4] != f"{version_id}.json"
        ):
            raise DocumentStateConflictError

    @staticmethod
    def _document_response(row: Document) -> DocumentResponse:
        try:
            return DocumentResponse(
                document_id=row.id,
                owner_user_id=row.owner_user_id,
                title=row.title,
                document_type=row.document_type,
                language=row.language,
                market=cast(MarketCode | None, row.market),
                product_id=row.product_id,
                access_level=cast(AccessLevel, row.access_level),
                active_version_id=row.active_version_id,
                created_at=row.created_at,
            )
        except ValidationError:
            raise KnowledgeDataContractError from None

    @staticmethod
    def _version_response(row: DocumentVersion) -> DocumentVersionResponse:
        try:
            return DocumentVersionResponse(
                version_id=row.id,
                file_id=row.file_id,
                version_no=row.version_no,
                content_hash=row.content_hash,
                parser_name=row.parser_name,
                parser_version=row.parser_version,
                parse_status=cast(ParseStatus, row.parse_status),
                index_status=cast(IndexStatus, row.index_status),
                created_at=row.created_at,
            )
        except ValidationError:
            raise KnowledgeDataContractError from None

    @staticmethod
    def _acl_response(row: DocumentAcl) -> DocumentAclResponse:
        try:
            return DocumentAclResponse(
                acl_id=row.id,
                subject_type=cast(AclSubjectType, row.subject_type),
                role_name=cast(RoleName | None, row.role_name),
                user_id=row.user_id,
                market_code=cast(MarketCode | None, row.market_code),
                permission="read",
                created_at=row.created_at,
            )
        except ValidationError:
            raise KnowledgeDataContractError from None
