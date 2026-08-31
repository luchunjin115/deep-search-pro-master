"""Common strict types, errors, and tool envelopes for M1."""

from __future__ import annotations

from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "UNAUTHENTICATED",
    "FORBIDDEN",
    "THREAD_NOT_FOUND",
    "EVIDENCE_NOT_FOUND",
    "FILE_NOT_FOUND",
    "DOCUMENT_NOT_FOUND",
    "FILE_STATE_CONFLICT",
    "DOCUMENT_STATE_CONFLICT",
    "DOCUMENT_VERSION_CONFLICT",
    "DOCUMENT_ACL_CONFLICT",
    "PRODUCT_NOT_FOUND",
    "AMBIGUOUS_PRODUCT",
    "INVENTORY_NOT_FOUND",
    "DATABASE_UNAVAILABLE",
    "DATABASE_TIMEOUT",
    "BUDGET_EXCEEDED",
    "PROVIDER_ERROR",
    "INTERNAL_ERROR",
]
MarketCode = Literal["DE", "FR"]
RoleName = Literal["company_owner", "product_scout", "amazon_operator"]
ToolName = Literal["get_product_spec", "search_inventory"]
ProductStatus = Literal["candidate", "active", "inactive", "discontinued"]
VerificationStatus = Literal["demo_declared", "unverified", "verified"]

SKU = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=3,
        max_length=64,
        pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$",
    ),
]
WarehouseCode = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=6,
        max_length=16,
        pattern=r"^[A-Z]{2}-[A-Z0-9]{3,8}$",
    ),
]
ProductQuery = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]


class M1Schema(BaseModel):
    """Base contract: reject unknown fields instead of silently ignoring them."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ErrorDetail(M1Schema):
    """Safe public error information without stack, SQL, token, or secret fields."""

    code: ErrorCode
    message: str = Field(min_length=1, max_length=300)
    retryable: bool
    field: str | None = Field(default=None, min_length=1, max_length=100)


class ApiErrorResponse(M1Schema):
    """The stable body used when an M1 API request fails."""

    status: Literal["error"] = "error"
    error: ErrorDetail
    trace_id: UUID | None = None


class ToolMeta(M1Schema):
    """Safe execution facts returned with every M1 Agent Tool result."""

    tool: ToolName
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)
    duration_ms: int = Field(ge=0)
    source_time: AwareDatetime | None = None
    trace_id: UUID
    synthetic_data: Literal[True] = True


DataT = TypeVar("DataT")


class ToolEnvelope(M1Schema, Generic[DataT]):
    """A success/error wrapper whose fields cannot contradict its status."""

    status: Literal["success", "error"]
    data: DataT | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=10)
    error: ErrorDetail | None = None
    meta: ToolMeta

    @model_validator(mode="after")
    def validate_status_payload(self) -> ToolEnvelope[DataT]:
        if self.status == "success":
            if self.data is None:
                raise ValueError("success ToolEnvelope must include data")
            if self.error is not None:
                raise ValueError("success ToolEnvelope cannot include error")
            return self

        if self.data is not None:
            raise ValueError("error ToolEnvelope cannot include data")
        if self.error is None:
            raise ValueError("error ToolEnvelope must include error")
        if self.evidence_ids:
            raise ValueError("error ToolEnvelope cannot expose evidence IDs")
        return self
