"""SQLAlchemy models that belong to the new M1 runtime."""

from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.identity import Role, Tenant, User, UserRole
from app.models.inventory import InventorySnapshot, Warehouse
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.models.runtime import (
    AgentRun,
    ContextArtifact,
    Evidence,
    Message,
    Thread,
    ToolCall,
    ToolContextLink,
)

__all__ = [
    "AgentRun",
    "ContextArtifact",
    "Document",
    "DocumentAcl",
    "DocumentChunk",
    "DocumentChunkSet",
    "DocumentIndexSet",
    "DocumentVersion",
    "Evidence",
    "InventorySnapshot",
    "Message",
    "Product",
    "ProductSpec",
    "ProductVariant",
    "Role",
    "StoredFile",
    "Tenant",
    "Thread",
    "ToolCall",
    "ToolContextLink",
    "User",
    "UserRole",
    "Warehouse",
]
