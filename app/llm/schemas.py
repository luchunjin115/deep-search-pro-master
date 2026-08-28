"""Strict model-facing contracts for controlled M1 Tool suggestions."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, TypeAdapter, field_validator, model_validator

from app.schemas.common import SKU, M1Schema, ToolName
from app.schemas.inventory import SearchInventoryInput
from app.schemas.product import GetProductSpecInput


class ModelToolSpec(M1Schema):
    """Safe Registry projection shown to a model; it contains no executable object."""

    name: ToolName
    description: str = Field(min_length=1, max_length=300)
    parameters: dict[str, Any]

    @field_validator("parameters")
    @classmethod
    def validate_strict_object_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if (
            value.get("type") != "object"
            or value.get("additionalProperties") is not False
        ):
            raise ValueError("Tool parameters must be a strict object JSON Schema")
        if not isinstance(value.get("properties"), dict):
            raise TypeError("Tool parameters must declare properties")
        return value


class ToolDecisionRequest(M1Schema):
    """One question plus only the Tool specs authorized for the current graph state."""

    question: str = Field(
        min_length=1,
        max_length=4000,
        description="用户原始问题；Provider只能提出Tool调用，不能执行Tool或SQL",
    )
    available_tools: tuple[ModelToolSpec, ...] = Field(min_length=1, max_length=2)
    resolved_sku: SKU | None = Field(
        default=None,
        description="由后端Tool确认的可信SKU；不是从模型输出直接继承的身份或权限数据",
    )

    @model_validator(mode="after")
    def validate_unique_tools(self) -> ToolDecisionRequest:
        names = [tool.name for tool in self.available_tools]
        if len(names) != len(set(names)):
            raise ValueError("available_tools cannot contain duplicate names")
        return self

    @property
    def allowed_tool_names(self) -> frozenset[ToolName]:
        """Return the exact allowlist supplied by the future LangGraph state."""

        return frozenset(tool.name for tool in self.available_tools)


class GetProductSpecToolCall(M1Schema):
    """A model proposal to resolve a product name or alias to one exact SKU."""

    name: Literal["get_product_spec"]
    arguments: GetProductSpecInput


class SearchInventoryToolCall(M1Schema):
    """A model proposal to query inventory for one already known exact SKU."""

    name: Literal["search_inventory"]
    arguments: SearchInventoryInput


ToolCallProposal: TypeAlias = Annotated[
    GetProductSpecToolCall | SearchInventoryToolCall,
    Field(discriminator="name"),
]
_TOOL_CALL_ADAPTER: TypeAdapter[ToolCallProposal] = TypeAdapter(ToolCallProposal)


def validate_tool_call_proposal(
    *,
    name: object,
    arguments: object,
    allowed_tool_names: frozenset[ToolName],
    resolved_sku: SKU | None = None,
) -> ToolCallProposal:
    """Validate model output locally and reject calls outside the current allowlist."""

    proposal = _TOOL_CALL_ADAPTER.validate_python(
        {"name": name, "arguments": arguments}
    )
    if proposal.name not in allowed_tool_names:
        raise ValueError("Model proposed a Tool outside the current allowlist")
    if (
        resolved_sku is not None
        and isinstance(proposal, SearchInventoryToolCall)
        and proposal.arguments.sku != resolved_sku
    ):
        raise ValueError("Model changed the backend-resolved SKU")
    return proposal
