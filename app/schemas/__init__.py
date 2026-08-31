"""Strict data contracts shared by the M1 API, services, tools, and frontend."""

from app.schemas.auth import CurrentUser, LoginRequest, LoginResponse
from app.schemas.chat import (
    ChatMessageRequest,
    ChatSuccessResponse,
    CreateThreadRequest,
    ExecutionSummary,
    ThreadResponse,
)
from app.schemas.common import (
    ApiErrorResponse,
    ErrorDetail,
    M1Schema,
    ToolEnvelope,
    ToolMeta,
)
from app.schemas.evidence import EvidenceDetail, EvidenceSummary
from app.schemas.files import (
    FileListResponse,
    FileRegistrationInput,
    FileResponse,
    FileStateUpdate,
    FileUploadResponse,
)
from app.schemas.inventory import (
    InventoryIntent,
    InventoryResult,
    SearchInventoryInput,
)
from app.schemas.knowledge import (
    DocumentAclGrantInput,
    DocumentAclResponse,
    DocumentChunkSetPublication,
    DocumentCreateInput,
    DocumentDetailResponse,
    DocumentIndexResponse,
    DocumentIndexStateUpdate,
    DocumentParseStateUpdate,
    DocumentResponse,
    DocumentVersionCreateInput,
    DocumentVersionResponse,
)
from app.schemas.product import (
    GetProductSpecInput,
    ProductSpecItem,
    ProductSpecResult,
)

__all__ = [
    "ApiErrorResponse",
    "ChatMessageRequest",
    "ChatSuccessResponse",
    "CreateThreadRequest",
    "CurrentUser",
    "DocumentAclGrantInput",
    "DocumentAclResponse",
    "DocumentChunkSetPublication",
    "DocumentCreateInput",
    "DocumentDetailResponse",
    "DocumentIndexResponse",
    "DocumentIndexStateUpdate",
    "DocumentParseStateUpdate",
    "DocumentResponse",
    "DocumentVersionCreateInput",
    "DocumentVersionResponse",
    "ErrorDetail",
    "EvidenceDetail",
    "EvidenceSummary",
    "ExecutionSummary",
    "FileListResponse",
    "FileRegistrationInput",
    "FileResponse",
    "FileStateUpdate",
    "FileUploadResponse",
    "GetProductSpecInput",
    "InventoryIntent",
    "InventoryResult",
    "LoginRequest",
    "LoginResponse",
    "M1Schema",
    "ProductSpecItem",
    "ProductSpecResult",
    "SearchInventoryInput",
    "ThreadResponse",
    "ToolEnvelope",
    "ToolMeta",
]
