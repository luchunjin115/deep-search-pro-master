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
from app.schemas.inventory import (
    InventoryIntent,
    InventoryResult,
    SearchInventoryInput,
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
    "ErrorDetail",
    "EvidenceDetail",
    "EvidenceSummary",
    "ExecutionSummary",
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
