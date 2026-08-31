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
    SkippedTableBlock,
    build_chunk_artifact,
    build_document_chunk,
)
from app.services.documents.chunking.normalization import (
    NormalizedSourceText,
    SourceCharacter,
    normalize_source_text,
)
from app.services.documents.chunking.service import DocumentChunkService
from app.services.documents.chunking.tables import (
    DocumentChunkingResult,
    StructureAwareDocumentChunker,
    StructureAwareTableChunker,
    TableChunkingResult,
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
    "DocumentChunkService",
    "DocumentChunkingError",
    "DocumentChunkingResult",
    "NormalizedSourceText",
    "SkippedTableBlock",
    "SourceCharacter",
    "StructureAwareDocumentChunker",
    "StructureAwareTableChunker",
    "StructureAwareTextChunker",
    "TableChunkingResult",
    "TextChunkingResult",
    "TokenCounter",
    "TokenSpan",
    "UnicodeMixedTokenCounter",
    "build_chunk_artifact",
    "build_document_chunk",
    "normalize_source_text",
]
