"""Strict file metadata, lifecycle, and public response contracts for M2."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import M1Schema

FileExtension = Literal[".pdf", ".docx", ".xlsx", ".csv"]
FileStatus = Literal[
    "uploaded",
    "validating",
    "parsing",
    "indexing",
    "ready",
    "failed",
    "soft_deleted",
]
Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]


class FileRegistrationInput(M1Schema):
    """Safe metadata accepted after Storage has produced trusted object facts."""

    original_name: str = Field(min_length=1, max_length=255)
    extension: FileExtension
    category: Literal["uploads"] = "uploads"

    @field_validator("original_name")
    @classmethod
    def reject_path_like_original_name(cls, value: str) -> str:
        if (
            value != value.strip()
            or "/" in value
            or "\\" in value
            or value in {".", ".."}
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("original_name must be a base filename")
        return value

    @model_validator(mode="after")
    def require_matching_extension(self) -> FileRegistrationInput:
        if not self.original_name.lower().endswith(self.extension):
            raise ValueError("original_name extension does not match extension")
        return self


class FileStateUpdate(M1Schema):
    """One requested transition; failure details are bounded and optional elsewhere."""

    status: FileStatus
    error_message: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("error_message")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("error_message must not contain control characters")
        return value

    @model_validator(mode="after")
    def validate_error_for_target_state(self) -> FileStateUpdate:
        if self.status == "failed" and self.error_message is None:
            raise ValueError("failed status requires error_message")
        if self.status not in {"failed", "soft_deleted"} and self.error_message:
            raise ValueError("error_message is only valid for failed or soft_deleted")
        return self


class FileResponse(M1Schema):
    """Authorized file metadata without Storage keys or filesystem paths."""

    file_id: UUID
    owner_user_id: UUID
    original_name: str = Field(min_length=1, max_length=255)
    extension: FileExtension
    mime_type: str = Field(min_length=3, max_length=127)
    size_bytes: int = Field(ge=0)
    sha256: Sha256
    category: Literal["uploads"]
    status: FileStatus
    error_message: str | None = Field(default=None, min_length=1, max_length=1000)
    created_at: AwareDatetime
    deleted_at: AwareDatetime | None = None


class FileListResponse(M1Schema):
    """A bounded file list prepared for the later HTTP endpoint."""

    items: list[FileResponse] = Field(max_length=100)


class FileUploadResponse(M1Schema):
    """Atomic multipart upload result for a bounded batch."""

    items: list[FileResponse] = Field(min_length=1, max_length=10)
