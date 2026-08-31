"""Retrieval primitives implemented independently from HTTP and persistence."""

from app.services.retrieval.embedding import (
    BgeM3EmbeddingProvider,
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingProvider,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
    create_embedding_provider,
)
from app.services.retrieval.errors import (
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalEmbeddingIdentityMismatchError,
    RetrievalEmbeddingProviderUnavailableError,
    RetrievalInputError,
    RetrievalInternalError,
)
from app.services.retrieval.lexical_text import (
    FTS_BUILDER_VERSION,
    FTS_TEXT_BUILDER_CONTRACT_VERSION,
    BuiltFtsText,
    FtsTextBuilderError,
    FtsTextBuilderIdentity,
    FtsTextPurpose,
    JiebaFtsTextBuilder,
    build_fts_text,
    get_fts_text_builder,
)

__all__ = [
    "FTS_BUILDER_VERSION",
    "FTS_TEXT_BUILDER_CONTRACT_VERSION",
    "BgeM3EmbeddingProvider",
    "BuiltFtsText",
    "EmbeddingBatch",
    "EmbeddingIdentity",
    "EmbeddingProvider",
    "EmbeddingPurpose",
    "FakeEmbeddingProvider",
    "FtsTextBuilderError",
    "FtsTextBuilderIdentity",
    "FtsTextPurpose",
    "JiebaFtsTextBuilder",
    "RetrievalDatabaseTimeoutError",
    "RetrievalDatabaseUnavailableError",
    "RetrievalEmbeddingIdentityMismatchError",
    "RetrievalEmbeddingProviderUnavailableError",
    "RetrievalInputError",
    "RetrievalInternalError",
    "build_fts_text",
    "create_embedding_provider",
    "get_fts_text_builder",
]
