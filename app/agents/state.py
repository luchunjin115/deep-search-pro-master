"""Strict public result and internal LangGraph state for M1 inventory queries."""

from __future__ import annotations

from typing import Literal, TypedDict
from uuid import UUID

from pydantic import Field, model_validator

from app.llm.schemas import ToolCallProposal
from app.schemas.common import ErrorDetail, M1Schema, ToolName
from app.schemas.inventory import InventoryResult
from app.schemas.product import ProductSpecResult

AgentTerminalStatus = Literal["completed", "failed", "denied", "timed_out"]
InventoryNodeName = Literal[
    "propose_next_tool",
    "validate_proposal",
    "execute_tool",
    "compose_answer",
    "compose_error",
]


class InventoryQueryInput(M1Schema):
    """One bounded question entering the internal M1 inventory graph."""

    question: str = Field(min_length=1, max_length=4000)


class InventoryAgentResult(M1Schema):
    """API-ready outcome of one graph run without exposing internal objects."""

    status: AgentTerminalStatus
    route: Literal["inventory_query"] = "inventory_query"
    answer: str = Field(min_length=1, max_length=4000)
    trace_id: UUID
    agent_run_id: UUID
    duration_ms: int = Field(ge=0)
    tool_names: list[ToolName] = Field(default_factory=list, max_length=2)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=10)
    inventory: InventoryResult | None = None
    error: ErrorDetail | None = None
    node_history: list[InventoryNodeName] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> InventoryAgentResult:
        if len(self.tool_names) != len(set(self.tool_names)):
            raise ValueError("tool_names cannot contain duplicates")
        if self.status == "completed":
            if self.inventory is None or self.error is not None:
                raise ValueError("completed result requires inventory and no error")
            if not self.evidence_ids:
                raise ValueError("completed result requires database Evidence")
            return self
        if self.inventory is not None or self.evidence_ids:
            raise ValueError("failed result cannot expose inventory or Evidence")
        if self.error is None:
            raise ValueError("failed result requires a safe error")
        return self


class InventoryGraphState(TypedDict, total=False):
    """Mutable values passed only between the five bounded LangGraph nodes."""

    question: str
    proposal: ToolCallProposal
    resolved_sku: str
    product: ProductSpecResult
    inventory: InventoryResult
    evidence_ids: list[UUID]
    tool_names: list[ToolName]
    error: ErrorDetail
    terminal_status: AgentTerminalStatus
    answer: str
    node_history: list[InventoryNodeName]
