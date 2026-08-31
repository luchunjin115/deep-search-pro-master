"""Strict write facts for one deterministic document Index Set."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.chunking.contracts import canonical_sha256
from app.services.retrieval import EmbeddingIdentity
from app.services.retrieval.lexical_text import (
    FTS_BUILDER_VERSION,
    FtsTextPurpose,
    build_fts_text,
)

INDEX_SCHEMA_VERSION: Literal["m2-document-index-set-v1"] = "m2-document-index-set-v1"
INDEX_EMBEDDING_PURPOSE: Literal["document"] = "document"
_INDEX_SET_NAMESPACE = uuid5(
    NAMESPACE_URL,
    "deep-search-pro/m2/document-index-set/v1",
)


class EmbeddingIdentityFacts(M1Schema):
    """Hardware-independent Embedding settings that can change vector values."""

    contract_version: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=100)
    pooling: str = Field(min_length=1, max_length=100)
    max_length: int = Field(ge=1)
    normalize: bool
    precision: str = Field(min_length=1, max_length=50)
    dimensions: Literal[1024]

    @classmethod
    def from_embedding_identity(
        cls,
        identity: EmbeddingIdentity,
    ) -> EmbeddingIdentityFacts:
        return cls.model_validate(asdict(identity))


def derive_document_index_set_id(
    *,
    document_chunk_set_id: UUID,
    embedding_identity_sha256: str,
) -> UUID:
    """Derive an Index Set ID without timestamps, runtime tuning, or hardware."""

    identity = {
        "document_chunk_set_id": str(document_chunk_set_id),
        "index_schema_version": INDEX_SCHEMA_VERSION,
        "embedding_identity_sha256": embedding_identity_sha256,
        "embedding_purpose": INDEX_EMBEDDING_PURPOSE,
        "fts_builder_version": FTS_BUILDER_VERSION,
    }
    return uuid5(_INDEX_SET_NAMESPACE, canonical_sha256(identity))


class DocumentIndexSetIdentity(M1Schema):
    """Self-validating logical identity used to claim one Index Set."""

    index_set_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_chunk_set_id: UUID
    index_schema_version: Literal["m2-document-index-set-v1"] = INDEX_SCHEMA_VERSION
    embedding_identity_json: EmbeddingIdentityFacts
    embedding_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_version: str = Field(min_length=1, max_length=100)
    embedding_purpose: Literal["document"] = INDEX_EMBEDDING_PURPOSE
    fts_builder_version: Literal["m2-fts-jieba-search-v1"] = FTS_BUILDER_VERSION

    @model_validator(mode="after")
    def validate_hash_id_and_audit_fields(self) -> DocumentIndexSetIdentity:
        identity_json = self.embedding_identity_json.model_dump(mode="json")
        expected_hash = canonical_sha256(identity_json)
        if self.embedding_identity_sha256 != expected_hash:
            raise ValueError("embedding identity hash does not match its JSON")
        if self.embedding_model != self.embedding_identity_json.model_id:
            raise ValueError("embedding model does not match its identity")
        if self.embedding_version != self.embedding_identity_json.revision:
            raise ValueError("embedding version does not match its identity")
        expected_id = derive_document_index_set_id(
            document_chunk_set_id=self.document_chunk_set_id,
            embedding_identity_sha256=self.embedding_identity_sha256,
        )
        if self.index_set_id != expected_id:
            raise ValueError("index set ID does not match its deterministic identity")
        return self


class DocumentChunkWriteFacts(M1Schema):
    """One fully paired Chunk and vector, ready for a later Repository write."""

    id: UUID
    tenant_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_chunk_set_id: UUID
    document_index_set_id: UUID
    chunk_id: str = Field(pattern=r"^c[0-9]{6}$")
    chunk_index: int = Field(ge=1)
    kind: Literal["text", "table"]
    body_text: str = Field(min_length=1, max_length=2_000_000)
    retrieval_text: str = Field(min_length=1, max_length=2_000_000)
    fts_text: str = Field(min_length=1, max_length=2_000_000)
    token_count: int = Field(ge=1, le=1_000_000)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    heading_path: list[str] = Field(max_length=9)
    page_numbers: list[int] = Field(max_length=2000)
    source_block_ids: list[str] = Field(min_length=1, max_length=1000)
    source_spans: list[dict[str, object]] = Field(min_length=1, max_length=1000)
    bounding_boxes: list[dict[str, object]]
    overlap_json: dict[str, object] | None = None
    table_json: dict[str, object] | None = None
    warnings: list[str] = Field(max_length=100)
    embedding: list[float] = Field(min_length=1024, max_length=1024)
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_version: str = Field(min_length=1, max_length=100)
    embedding_cache_key: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_derived_fields(self) -> DocumentChunkWriteFacts:
        if self.id != uuid5(self.document_index_set_id, self.chunk_id):
            raise ValueError("chunk row ID does not match its deterministic identity")
        expected_fts_text = build_fts_text(
            self.retrieval_text,
            purpose=FtsTextPurpose.DOCUMENT,
        ).text
        if self.fts_text != expected_fts_text:
            raise ValueError("FTS text does not match the versioned builder")
        if (self.kind == "table") != (self.table_json is not None):
            raise ValueError("table JSON must match the Chunk kind")
        return self
