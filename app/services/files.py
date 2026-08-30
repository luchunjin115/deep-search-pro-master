"""File metadata registration, authorization, and lifecycle rules for M2."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO, Protocol, cast
from uuid import UUID, uuid4

import filetype  # type: ignore[import-untyped]
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import (
    FileMetadataError,
    FileNotFoundError,
    FileStateConflictError,
    FileStorageError,
    FileUploadValidationError,
    KnowledgeDataContractError,
    KnowledgePersistenceError,
)
from app.models.knowledge import StoredFile
from app.schemas.auth import CurrentUser
from app.schemas.files import (
    FileExtension,
    FileListResponse,
    FileRegistrationInput,
    FileResponse,
    FileStateUpdate,
    FileStatus,
)
from app.services.storage import (
    StorageBackend,
    StorageError,
    StoredObject,
    validate_content_type,
    validate_storage_key,
)

_CANONICAL_MIME_TYPES: dict[FileExtension, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}
_ALLOWED_DECLARED_MIME_TYPES: dict[FileExtension, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".docx": frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
    ".xlsx": frozenset(
        {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    ),
    ".csv": frozenset({"text/csv", "application/csv", "text/plain"}),
}
_ZIP_REQUIRED_MEMBERS: dict[FileExtension, frozenset[str]] = {
    ".docx": frozenset({"[Content_Types].xml", "_rels/.rels", "word/document.xml"}),
    ".xlsx": frozenset({"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"}),
}
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_EXPANSION = 20

FILE_TRANSITIONS: dict[str, frozenset[str]] = {
    "uploaded": frozenset({"validating", "failed", "soft_deleted"}),
    "validating": frozenset({"parsing", "failed", "soft_deleted"}),
    "parsing": frozenset({"indexing", "failed", "soft_deleted"}),
    "indexing": frozenset({"ready", "failed", "soft_deleted"}),
    "ready": frozenset({"soft_deleted"}),
    "failed": frozenset({"validating", "soft_deleted"}),
    "soft_deleted": frozenset(),
}


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """Public metadata plus the private key needed for rollback compensation."""

    response: FileResponse
    storage_key: str


@dataclass(frozen=True, slots=True)
class FileDownload:
    """Authorized download metadata and an already-open managed stream."""

    stream: BinaryIO
    original_name: str
    content_type: str
    size_bytes: int


class FileStore(Protocol):
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
    ) -> StoredFile: ...

    def find_owned_unlinked_file(
        self, *, tenant_id: UUID, owner_user_id: UUID, file_id: UUID
    ) -> StoredFile | None: ...

    def find_manageable_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        company_owner: bool,
        file_id: UUID,
    ) -> StoredFile | None: ...

    def find_accessible_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        file_id: UUID,
    ) -> StoredFile | None: ...

    def list_accessible(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        limit: int,
    ) -> list[StoredFile]: ...

    def update_state(
        self,
        row: StoredFile,
        *,
        status: str,
        error_message: str | None,
        deleted_at: datetime | None,
    ) -> StoredFile: ...


class FileService:
    """Expose safe metadata while keeping Storage keys internal to services."""

    def __init__(
        self,
        repository: FileStore,
        storage: StorageBackend | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage

    def upload_file(
        self,
        user: CurrentUser,
        *,
        original_name: str,
        declared_content_type: str,
        stream: BinaryIO,
        allowed_extensions: tuple[str, ...],
        max_size_bytes: int,
    ) -> UploadedFile:
        """Validate one seekable multipart stream, persist it, then flush metadata."""

        extension = self._validate_upload(
            original_name=original_name,
            declared_content_type=declared_content_type,
            stream=stream,
            allowed_extensions=allowed_extensions,
            max_size_bytes=max_size_bytes,
        )
        file_id = uuid4()
        now = datetime.now(UTC)
        storage_key = f"{user.tenant_id}/uploads/{now:%Y}/{now:%m}/{file_id}{extension}"
        storage = self._require_storage()
        try:
            stored = storage.put(
                storage_key,
                stream,
                _CANONICAL_MIME_TYPES[extension],
            )
        except StorageError:
            raise FileStorageError from None

        try:
            response = self.register_file(
                user,
                file_id=file_id,
                request=FileRegistrationInput(
                    original_name=original_name,
                    extension=extension,
                ),
                stored=stored,
            )
        except Exception:
            self.compensate_upload(storage_key)
            raise
        return UploadedFile(response=response, storage_key=storage_key)

    def compensate_upload(self, storage_key: str) -> None:
        """Remove an object whose database transaction did not commit."""

        try:
            self._require_storage().delete(storage_key)
        except StorageError:
            raise FileStorageError from None

    def open_download(self, user: CurrentUser, file_id: UUID) -> FileDownload:
        """Authorize by opaque ID before opening the private Storage key."""

        try:
            row = self._repository.find_accessible_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                role_names=tuple(user.roles),
                market_scopes=tuple(user.market_scopes),
                file_id=file_id,
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        if row is None:
            raise FileNotFoundError
        try:
            stream = self._require_storage().open(row.storage_key)
        except StorageError:
            raise FileStorageError from None
        return FileDownload(
            stream=stream,
            original_name=row.original_name,
            content_type=row.mime_type,
            size_bytes=row.size_bytes,
        )

    def register_file(
        self,
        user: CurrentUser,
        *,
        file_id: UUID,
        request: FileRegistrationInput,
        stored: StoredObject,
    ) -> FileResponse:
        self._validate_stored_object(user, file_id, request, stored)
        try:
            row = self._repository.create_file(
                file_id=file_id,
                tenant_id=user.tenant_id,
                owner_user_id=user.user_id,
                original_name=request.original_name,
                storage_key=stored.key,
                extension=request.extension,
                mime_type=stored.content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                category=request.category,
            )
            return self._to_response(row)
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def get_file(self, user: CurrentUser, file_id: UUID) -> FileResponse:
        try:
            row = self._repository.find_accessible_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                role_names=tuple(user.roles),
                market_scopes=tuple(user.market_scopes),
                file_id=file_id,
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        if row is None:
            raise FileNotFoundError
        return self._to_response(row)

    def list_files(self, user: CurrentUser, *, limit: int = 100) -> FileListResponse:
        if not 1 <= limit <= 100:
            raise FileMetadataError
        try:
            rows = self._repository.list_accessible(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                role_names=tuple(user.roles),
                market_scopes=tuple(user.market_scopes),
                limit=limit,
            )
            return FileListResponse(items=[self._to_response(row) for row in rows])
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def transition_file(
        self,
        user: CurrentUser,
        file_id: UUID,
        request: FileStateUpdate,
    ) -> FileResponse:
        try:
            row = self._repository.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                file_id=file_id,
            )
            if row is None:
                raise FileNotFoundError
            if request.status not in FILE_TRANSITIONS.get(row.status, frozenset()):
                raise FileStateConflictError

            deleted_at = datetime.now(UTC) if request.status == "soft_deleted" else None
            error_message = request.error_message
            if request.status == "soft_deleted" and error_message is None:
                error_message = row.error_message
            updated = self._repository.update_state(
                row,
                status=request.status,
                error_message=error_message,
                deleted_at=deleted_at,
            )
            return self._to_response(updated)
        except (FileNotFoundError, FileStateConflictError):
            raise
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None

    def require_owned_unlinked_file(
        self,
        user: CurrentUser,
        file_id: UUID,
    ) -> StoredFile:
        try:
            row = self._repository.find_owned_unlinked_file(
                tenant_id=user.tenant_id,
                owner_user_id=user.user_id,
                file_id=file_id,
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        if row is None:
            raise FileNotFoundError
        return row

    def require_manageable_file(
        self,
        user: CurrentUser,
        file_id: UUID,
    ) -> StoredFile:
        try:
            row = self._repository.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                file_id=file_id,
            )
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        if row is None:
            raise FileNotFoundError
        return row

    def _require_storage(self) -> StorageBackend:
        if self._storage is None:
            raise FileStorageError
        return self._storage

    @staticmethod
    def _validate_upload(
        *,
        original_name: str,
        declared_content_type: str,
        stream: BinaryIO,
        allowed_extensions: tuple[str, ...],
        max_size_bytes: int,
    ) -> FileExtension:
        try:
            lowered_name = original_name.lower()
            extension = cast(
                FileExtension,
                next(
                    candidate
                    for candidate in allowed_extensions
                    if lowered_name.endswith(candidate)
                ),
            )
            FileRegistrationInput(
                original_name=original_name,
                extension=extension,
            )
        except (StopIteration, ValidationError):
            raise FileUploadValidationError from None

        normalized_mime = (
            declared_content_type.split(";", maxsplit=1)[0].strip().lower()
        )
        if (
            not normalized_mime
            or any(ord(character) < 32 for character in declared_content_type)
            or normalized_mime not in _ALLOWED_DECLARED_MIME_TYPES[extension]
        ):
            raise FileUploadValidationError

        try:
            stream.seek(0, 2)
            size_bytes = stream.tell()
            stream.seek(0)
        except (OSError, ValueError, AttributeError):
            raise FileUploadValidationError from None
        if size_bytes <= 0 or size_bytes > max_size_bytes:
            raise FileUploadValidationError

        try:
            FileService._validate_signature(stream, extension, size_bytes)
            stream.seek(0)
        except FileUploadValidationError:
            raise
        except Exception:  # noqa: BLE001 - malformed streams can fail arbitrarily.
            raise FileUploadValidationError from None
        return extension

    @staticmethod
    def _validate_signature(
        stream: BinaryIO,
        extension: FileExtension,
        size_bytes: int,
    ) -> None:
        head = stream.read(min(size_bytes, 8192))
        detected = filetype.guess(head)

        if extension == ".pdf":
            if detected is None or detected.mime != "application/pdf":
                raise FileUploadValidationError
            stream.seek(max(0, size_bytes - 2048))
            if b"%%EOF" not in stream.read(2048):
                raise FileUploadValidationError
            return

        if extension in {".docx", ".xlsx"}:
            if detected is not None and detected.mime not in {
                "application/zip",
                _CANONICAL_MIME_TYPES[extension],
            }:
                raise FileUploadValidationError
            stream.seek(0)
            try:
                with zipfile.ZipFile(stream) as archive:
                    members = archive.infolist()
                    names = {member.filename for member in members}
                    if (
                        len(members) > _MAX_ARCHIVE_MEMBERS
                        or not _ZIP_REQUIRED_MEMBERS[extension].issubset(names)
                        or any(member.flag_bits & 0x1 for member in members)
                        or sum(member.file_size for member in members)
                        > size_bytes * _MAX_ARCHIVE_EXPANSION
                    ):
                        raise FileUploadValidationError
            except zipfile.BadZipFile:
                raise FileUploadValidationError from None
            return

        if detected is not None or b"\x00" in head:
            raise FileUploadValidationError
        try:
            head.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                head.decode("gb18030")
            except UnicodeDecodeError:
                raise FileUploadValidationError from None

    @staticmethod
    def _validate_stored_object(
        user: CurrentUser,
        file_id: UUID,
        request: FileRegistrationInput,
        stored: StoredObject,
    ) -> None:
        try:
            key = validate_storage_key(stored.key)
            validate_content_type(stored.content_type)
        except StorageError:
            raise FileMetadataError from None
        parts = key.split("/")
        expected_filename = f"{file_id}{request.extension}"
        if (
            parts[0] != str(user.tenant_id)
            or parts[1] != request.category
            or parts[4] != expected_filename
            or stored.size_bytes < 0
            or len(stored.sha256) != 64
            or any(character not in "0123456789abcdef" for character in stored.sha256)
            or re.fullmatch(
                r"[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*",
                stored.content_type,
            )
            is None
        ):
            raise FileMetadataError

    @staticmethod
    def _to_response(row: StoredFile) -> FileResponse:
        try:
            return FileResponse(
                file_id=row.id,
                owner_user_id=row.owner_user_id,
                original_name=row.original_name,
                extension=cast(FileExtension, row.extension),
                mime_type=row.mime_type,
                size_bytes=row.size_bytes,
                sha256=row.sha256,
                category="uploads",
                status=cast(FileStatus, row.status),
                error_message=row.error_message,
                created_at=row.created_at,
                deleted_at=row.deleted_at,
            )
        except ValidationError:
            raise KnowledgeDataContractError from None
