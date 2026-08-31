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

__all__ = [
    "BgeM3EmbeddingProvider",
    "EmbeddingBatch",
    "EmbeddingIdentity",
    "EmbeddingProvider",
    "EmbeddingPurpose",
    "FakeEmbeddingProvider",
    "create_embedding_provider",
]
