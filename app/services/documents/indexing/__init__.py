"""Public deterministic identity and mapping contracts for document indexing."""

from app.services.documents.indexing.contracts import (
    FTS_BUILDER_VERSION,
    INDEX_EMBEDDING_PURPOSE,
    INDEX_SCHEMA_VERSION,
    DocumentChunkWriteFacts,
    DocumentIndexSetIdentity,
    EmbeddingIdentityFacts,
    derive_document_index_set_id,
)
from app.services.documents.indexing.mapping import (
    DocumentIndexMappingError,
    build_document_index_set_identity,
    map_document_chunk_rows,
)

__all__ = [
    "FTS_BUILDER_VERSION",
    "INDEX_EMBEDDING_PURPOSE",
    "INDEX_SCHEMA_VERSION",
    "DocumentChunkWriteFacts",
    "DocumentIndexMappingError",
    "DocumentIndexSetIdentity",
    "EmbeddingIdentityFacts",
    "build_document_index_set_identity",
    "derive_document_index_set_id",
    "map_document_chunk_rows",
]
