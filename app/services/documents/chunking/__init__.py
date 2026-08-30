"""Public contracts for M2 structure-aware chunking."""

from app.services.documents.chunking.chunker import (
    DocumentChunkingError,
    StructureAwareTextChunker,
    TextChunkingResult,
)
from app.services.documents.chunking.contracts import (
    CanonicalChunkArtifact,
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    DocumentChunk,
    build_chunk_artifact,
    build_document_chunk,
)
from app.services.documents.chunking.normalization import (
    NormalizedSourceText,
    SourceCharacter,
    normalize_source_text,
)
from app.services.documents.chunking.token_counting import (
    TokenCounter,
    TokenSpan,
    UnicodeMixedTokenCounter,
)

__all__ = [
    "CanonicalChunkArtifact",
    "ChunkInputProvenance",
    "ChunkerIdentity",
    "ChunkingConfig",
    "DocumentChunk",
    "DocumentChunkingError",
    "NormalizedSourceText",
    "SourceCharacter",
    "StructureAwareTextChunker",
    "TextChunkingResult",
    "TokenCounter",
    "TokenSpan",
    "UnicodeMixedTokenCounter",
    "build_chunk_artifact",
    "build_document_chunk",
    "normalize_source_text",
]
