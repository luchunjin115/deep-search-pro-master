"""Pure mapping from validated Chunk and Embedding artifacts to write facts."""

from __future__ import annotations

import math
from numbers import Real
from uuid import UUID, uuid5

from pydantic import ValidationError

from app.services.documents.chunking import CanonicalChunkArtifact
from app.services.documents.chunking.contracts import canonical_sha256
from app.services.documents.indexing.contracts import (
    DocumentChunkWriteFacts,
    DocumentIndexSetIdentity,
    EmbeddingIdentityFacts,
    derive_document_index_set_id,
)
from app.services.retrieval import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingPurpose,
)
from app.services.retrieval.embedding import build_embedding_cache_key


class DocumentIndexMappingError(ValueError):
    """Validated indexing inputs disagree and cannot be safely paired."""


def build_document_index_set_identity(
    artifact: CanonicalChunkArtifact,
    embedding_identity: EmbeddingIdentity,
) -> DocumentIndexSetIdentity:
    """Build the stable identity needed before expensive Embedding starts."""

    validated_artifact = _revalidate_artifact(artifact)
    identity_facts = EmbeddingIdentityFacts.from_embedding_identity(embedding_identity)
    identity_hash = canonical_sha256(identity_facts.model_dump(mode="json"))
    index_set_id = derive_document_index_set_id(
        document_chunk_set_id=validated_artifact.chunk_set_id,
        embedding_identity_sha256=identity_hash,
    )
    return DocumentIndexSetIdentity(
        index_set_id=index_set_id,
        document_id=validated_artifact.input.document_id,
        document_version_id=validated_artifact.input.document_version_id,
        document_chunk_set_id=validated_artifact.chunk_set_id,
        embedding_identity_json=identity_facts,
        embedding_identity_sha256=identity_hash,
        embedding_model=identity_facts.model_id,
        embedding_version=identity_facts.revision,
    )


def map_document_chunk_rows(
    *,
    tenant_id: UUID,
    artifact: CanonicalChunkArtifact,
    index_identity: DocumentIndexSetIdentity,
    embeddings: EmbeddingBatch,
) -> tuple[DocumentChunkWriteFacts, ...]:
    """Reject mismatches before pairing each ordered Chunk with one vector."""

    validated_artifact = _revalidate_artifact(artifact)
    validated_identity = _revalidate_index_identity(index_identity)
    _validate_boundaries(validated_artifact, validated_identity)
    if embeddings.purpose is not EmbeddingPurpose.DOCUMENT:
        raise DocumentIndexMappingError("embedding purpose is not document")

    batch_identity = _batch_identity_facts(embeddings)
    if batch_identity != validated_identity.embedding_identity_json:
        raise DocumentIndexMappingError("embedding identity does not match Index Set")

    chunks = validated_artifact.chunks
    if not (len(chunks) == len(embeddings.vectors) == len(embeddings.cache_keys)):
        raise DocumentIndexMappingError("embedding count does not match Chunk count")

    rows: list[DocumentChunkWriteFacts] = []
    for chunk, vector, cache_key in zip(
        chunks,
        embeddings.vectors,
        embeddings.cache_keys,
        strict=True,
    ):
        _validate_vector(vector, dimensions=batch_identity.dimensions)
        expected_cache_key = build_embedding_cache_key(
            embeddings.identity,
            EmbeddingPurpose.DOCUMENT,
            chunk.retrieval_text,
        )
        if cache_key != expected_cache_key:
            raise DocumentIndexMappingError(
                "embedding cache key does not match Chunk order"
            )
        chunk_json = chunk.model_dump(mode="json")
        rows.append(
            DocumentChunkWriteFacts(
                id=uuid5(validated_identity.index_set_id, chunk.chunk_id),
                tenant_id=tenant_id,
                document_id=validated_artifact.input.document_id,
                document_version_id=validated_artifact.input.document_version_id,
                document_chunk_set_id=validated_artifact.chunk_set_id,
                document_index_set_id=validated_identity.index_set_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                kind=chunk.kind,
                body_text=chunk.body_text,
                retrieval_text=chunk.retrieval_text,
                fts_text=chunk.retrieval_text,
                token_count=chunk.token_count,
                content_sha256=chunk.content_sha256,
                heading_path=chunk.heading_path,
                page_numbers=chunk.page_numbers,
                source_block_ids=chunk.source_block_ids,
                source_spans=chunk_json["source_spans"],
                bounding_boxes=chunk_json["bounding_boxes"],
                overlap_json=chunk_json["overlap"],
                table_json=chunk_json["table"],
                warnings=chunk.warnings,
                embedding=list(vector),
                embedding_model=validated_identity.embedding_model,
                embedding_version=validated_identity.embedding_version,
                embedding_cache_key=cache_key,
            )
        )
    return tuple(rows)


def _revalidate_artifact(
    artifact: CanonicalChunkArtifact,
) -> CanonicalChunkArtifact:
    try:
        return CanonicalChunkArtifact.model_validate(artifact.model_dump(mode="json"))
    except (AttributeError, ValidationError):
        raise DocumentIndexMappingError(
            "artifact integrity validation failed"
        ) from None


def _revalidate_index_identity(
    identity: DocumentIndexSetIdentity,
) -> DocumentIndexSetIdentity:
    try:
        return DocumentIndexSetIdentity.model_validate(identity.model_dump(mode="json"))
    except (AttributeError, ValidationError):
        raise DocumentIndexMappingError("index identity validation failed") from None


def _batch_identity_facts(embeddings: EmbeddingBatch) -> EmbeddingIdentityFacts:
    try:
        return EmbeddingIdentityFacts.from_embedding_identity(embeddings.identity)
    except (TypeError, ValidationError):
        raise DocumentIndexMappingError(
            "embedding identity validation failed"
        ) from None


def _validate_boundaries(
    artifact: CanonicalChunkArtifact,
    identity: DocumentIndexSetIdentity,
) -> None:
    if (
        identity.document_id != artifact.input.document_id
        or identity.document_version_id != artifact.input.document_version_id
        or identity.document_chunk_set_id != artifact.chunk_set_id
    ):
        raise DocumentIndexMappingError(
            "index identity does not match document boundaries"
        )


def _validate_vector(vector: tuple[float, ...], *, dimensions: int) -> None:
    if len(vector) != dimensions or any(
        not isinstance(value, Real) or isinstance(value, bool) for value in vector
    ):
        raise DocumentIndexMappingError("embedding vector shape is invalid")
    values = tuple(float(value) for value in vector)
    if not all(math.isfinite(value) for value in values):
        raise DocumentIndexMappingError("embedding vector contains non-finite values")
    norm = math.sqrt(sum(value * value for value in values))
    if not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
        raise DocumentIndexMappingError("embedding vector is not normalized")
