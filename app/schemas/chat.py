"""Thread and synchronous chat response contracts for M1."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.agent import BusinessOutcome
from app.schemas.common import M1Schema, ToolName
from app.schemas.evidence import DocumentEvidenceSummary, EvidenceSummary

ChatEvidenceSummary: TypeAlias = Annotated[
    EvidenceSummary | DocumentEvidenceSummary,
    Field(discriminator="source_type"),
]


class CreateThreadRequest(M1Schema):
    """Optional human-readable title for a new M1 chat thread."""

    title: str | None = Field(default=None, min_length=1, max_length=200)


class ThreadResponse(M1Schema):
    """A thread identity safe to expose through the API."""

    thread_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "archived"]
    created_at: AwareDatetime


class ChatMessageRequest(M1Schema):
    """One bounded natural-language question sent to an existing thread."""

    request_id: UUID = Field(default_factory=uuid4)
    message: str = Field(min_length=1, max_length=4000)


class ExecutionSummary(M1Schema):
    """Frontend-safe execution state associated with one chat answer."""

    trace_id: UUID
    route: Literal[
        "agent_gateway",
        "inventory_query",
        "product_spec",
        "unsupported",
    ]
    tool_names: list[ToolName] = Field(default_factory=list, max_length=5)
    duration_ms: int = Field(ge=0)
    status: Literal["waiting_user", "completed", "failed", "denied", "timed_out"]
    business_outcome: BusinessOutcome | None = None

    @field_validator("tool_names")
    @classmethod
    def reject_duplicate_tools(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate tool names are not allowed")
        return value


class ChatSuccessResponse(M1Schema):
    """Complete synchronous response returned after one successful M1 question."""

    status: Literal["waiting_user", "completed"] = "completed"
    request_id: UUID
    thread_id: UUID
    message_id: UUID
    answer: str = Field(min_length=1, max_length=4000)
    evidence: list[ChatEvidenceSummary] = Field(default_factory=list, max_length=12)
    execution: ExecutionSummary
