"""Controlled, tenant-scoped data access used by M1 services."""

from app.repositories.common import apply_statement_timeout
from app.repositories.document_indexes import DocumentIndexRepository
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.repositories.identity import IdentityRecord, IdentityRepository
from app.repositories.inventory import InventoryRecord, InventoryRepository
from app.repositories.product import (
    ProductCandidate,
    ProductRepository,
    ProductSpecRecord,
)

__all__ = [
    "DocumentIndexRepository",
    "DocumentRepository",
    "FileRepository",
    "IdentityRecord",
    "IdentityRepository",
    "InventoryRecord",
    "InventoryRepository",
    "ProductCandidate",
    "ProductRepository",
    "ProductSpecRecord",
    "apply_statement_timeout",
]
