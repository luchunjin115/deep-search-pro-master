"""Public-safe bounded outputs for parsed uploaded-file reads."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.common import M1Schema
from app.schemas.files import FileReadSourceType
from app.schemas.retrieval import RetrievalSourceLocator

FILE_READ_MAX_CHARACTERS = 8_000


class FileReadSection(M1Schema):
    """One server-selected public-safe excerpt from a validated parsed artifact."""

    kind: Literal["text", "table"]
    locator: RetrievalSourceLocator
    content: str = Field(
        strict=True,
        min_length=1,
        max_length=FILE_READ_MAX_CHARACTERS,
    )
    truncated: bool


class ReadUploadedFileResult(M1Schema):
    """Bounded parsed-file preview without Storage, tenant, ACL, or path fields."""

    file_id: UUID
    document_id: UUID
    version_id: UUID
    version_no: int = Field(strict=True, ge=1)
    original_name: str = Field(strict=True, min_length=1, max_length=255)
    source_type: FileReadSourceType
    is_active_version: bool
    sections: list[FileReadSection] = Field(min_length=1, max_length=12)
    total_characters: int = Field(
        strict=True,
        ge=1,
        le=FILE_READ_MAX_CHARACTERS,
    )
    truncated: bool
    synthetic_data: Literal[True] = True

    @field_validator("original_name")
    @classmethod
    def reject_private_path_shape(cls, value: str) -> str:
        if (
            value != value.strip()
            or "/" in value
            or "\\" in value
            or value in {".", ".."}
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("original_name must be a safe base filename")
        return value

    @model_validator(mode="after")
    def validate_public_result(self) -> ReadUploadedFileResult:
        if sum(len(section.content) for section in self.sections) != (
            self.total_characters
        ):
            raise ValueError("file read character total must match its sections")
        if any(
            section.locator.source_type != self.source_type for section in self.sections
        ):
            raise ValueError("file read section locator must match the source type")
        if any(section.truncated for section in self.sections) and not self.truncated:
            raise ValueError("truncated section requires a truncated result")
        return self
