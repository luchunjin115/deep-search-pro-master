"""Controlled, tenant-scoped data access used by M1 services."""

from app.repositories.common import apply_statement_timeout
from app.repositories.document_indexes import DocumentIndexRepository
from app.repositories.documents import DocumentRepository
from app.repositories.evidence import (
    AuthorizedCitationContext,
    AuthorizedDocumentEvidence,
    KnowledgeEvidenceRepository,
)
from app.repositories.files import FileRepository, ReadableParsedFile
from app.repositories.identity import IdentityRecord, IdentityRepository
from app.repositories.inventory import InventoryRecord, InventoryRepository
from app.repositories.product import (
    ProductCandidate,
    ProductRepository,
    ProductSpecRecord,
)
from app.repositories.retrieval import (
    ContextChunkRecord,
    ContextChunkRehydrationError,
    ContextChunkWindowRecord,
    DenseCandidateRecord,
    LexicalCandidateRecord,
    RetrievalRepository,
)

__all__ = [
    "AuthorizedCitationContext",
    "AuthorizedDocumentEvidence",
    "ContextChunkRecord",
    "ContextChunkRehydrationError",
    "ContextChunkWindowRecord",
    "DenseCandidateRecord",
    "DocumentIndexRepository",
    "DocumentRepository",
    "FileRepository",
    "IdentityRecord",
    "IdentityRepository",
    "InventoryRecord",
    "InventoryRepository",
    "KnowledgeEvidenceRepository",
    "LexicalCandidateRecord",
    "ProductCandidate",
    "ProductRepository",
    "ProductSpecRecord",
    "ReadableParsedFile",
    "RetrievalRepository",
    "apply_statement_timeout",
]
