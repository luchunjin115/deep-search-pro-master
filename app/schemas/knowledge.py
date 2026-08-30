"""Strict logical-document, version, and ACL contracts for M2."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.common import M1Schema, MarketCode, RoleName
from app.schemas.files import Sha256

AccessLevel = Literal["private", "tenant", "restricted"]
ParseStatus = Literal["pending", "parsing", "ready", "failed"]
IndexStatus = Literal["pending", "indexing", "ready", "failed"]
AclSubjectType = Literal["role", "user", "market"]


class DocumentCreateInput(M1Schema):
    """Create one logical document around an already registered owned file."""

    file_id: UUID
    title: str = Field(min_length=1, max_length=300)
    document_type: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
    )
    language: str | None = Field(
        default=None,
        max_length=8,
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
    )
    market: MarketCode | None = None
    product_id: UUID | None = None
    access_level: AccessLevel = "private"


class DocumentVersionCreateInput(M1Schema):
    """Add a new owned physical file as the next version of one document."""

    file_id: UUID


class DocumentAclGrantInput(M1Schema):
    """One mutually exclusive role, user, or market read grant."""

    subject_type: AclSubjectType
    role_name: RoleName | None = None
    user_id: UUID | None = None
    market_code: MarketCode | None = None

    @model_validator(mode="after")
    def validate_subject_shape(self) -> DocumentAclGrantInput:
        expected = {
            "role": self.role_name is not None
            and self.user_id is None
            and self.market_code is None,
            "user": self.role_name is None
            and self.user_id is not None
            and self.market_code is None,
            "market": self.role_name is None
            and self.user_id is None
            and self.market_code is not None,
        }
        if not expected[self.subject_type]:
            raise ValueError("ACL subject fields do not match subject_type")
        return self


class DocumentParseStateUpdate(M1Schema):
    """Internal parser transition; parsed Storage key never enters public output."""

    status: ParseStatus
    parser_name: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]{0,63}$",
    )
    parser_version: str | None = Field(default=None, min_length=1, max_length=64)
    parsed_storage_key: str | None = Field(default=None, min_length=1, max_length=512)

    @model_validator(mode="after")
    def require_ready_artifact(self) -> DocumentParseStateUpdate:
        facts = (self.parser_name, self.parser_version, self.parsed_storage_key)
        if self.status == "ready" and any(value is None for value in facts):
            raise ValueError("ready parse requires parser and artifact metadata")
        if self.status == "parsing" and any(value is not None for value in facts):
            raise ValueError("parsing transition cannot publish artifact metadata")
        return self


class DocumentIndexStateUpdate(M1Schema):
    """Internal index-state transition used before active-version switching."""

    status: IndexStatus


class DocumentVersionResponse(M1Schema):
    """Safe version status without parsed Storage keys."""

    version_id: UUID
    file_id: UUID
    version_no: int = Field(ge=1)
    content_hash: Sha256
    parser_name: str | None = Field(default=None, max_length=64)
    parser_version: str | None = Field(default=None, max_length=64)
    parse_status: ParseStatus
    index_status: IndexStatus
    created_at: AwareDatetime


class ParsedDocumentPublication(M1Schema):
    """Safe result of one internal parse publication without its Storage key."""

    version_id: UUID
    parse_status: Literal["ready"] = "ready"
    route: Literal["native", "docling", "hybrid"]
    parser_provider: Literal["native", "docling"]
    parser_name: str = Field(min_length=1, max_length=64)
    parser_version: str = Field(min_length=1, max_length=64)
    artifact_content_sha256: Sha256
    published_sha256: Sha256
    warning_count: int = Field(ge=0, le=6000)


class DocumentAclResponse(M1Schema):
    """Safe explicit authorization entry."""

    acl_id: UUID
    subject_type: AclSubjectType
    role_name: RoleName | None = None
    user_id: UUID | None = None
    market_code: MarketCode | None = None
    permission: Literal["read"] = "read"
    created_at: AwareDatetime


class DocumentResponse(M1Schema):
    """Authorized logical-document metadata without tenant or internal paths."""

    document_id: UUID
    owner_user_id: UUID
    title: str = Field(min_length=1, max_length=300)
    document_type: str = Field(min_length=1, max_length=32)
    language: str | None = Field(default=None, max_length=8)
    market: MarketCode | None = None
    product_id: UUID | None = None
    access_level: AccessLevel
    active_version_id: UUID | None = None
    created_at: AwareDatetime


class DocumentDetailResponse(DocumentResponse):
    """Document plus bounded versions and ACLs for an authorized caller."""

    versions: list[DocumentVersionResponse] = Field(max_length=100)
    acl: list[DocumentAclResponse] = Field(max_length=100)
