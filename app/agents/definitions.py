"""Strict role definitions for the first two engineered Agent Workers."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.capabilities.contracts import (
    AgentId,
    CapabilityDescription,
    CapabilityImplementationStatus,
    SemanticVersion,
)
from app.schemas.agent import CapabilityId, EvidenceSourceType, ShortText
from app.schemas.common import M1Schema


class AgentDefinition(M1Schema):
    """A server-owned Worker role; it is not an executable Worker instance."""

    model_config = ConfigDict(frozen=True)

    agent_id: AgentId
    version: SemanticVersion
    description: CapabilityDescription
    allowed_capability_ids: tuple[CapabilityId, ...] = Field(
        min_length=1,
        max_length=5,
    )
    evidence_source_types: tuple[EvidenceSourceType, ...] = Field(max_length=4)
    completion_criteria: ShortText
    input_contract: Literal["AgentHandoff"] = "AgentHandoff"
    output_contract: Literal["WorkerResult"] = "WorkerResult"
    can_delegate: Literal[False] = False
    implementation_status: CapabilityImplementationStatus

    @model_validator(mode="after")
    def validate_unique_lists(self) -> AgentDefinition:
        if len(self.allowed_capability_ids) != len(set(self.allowed_capability_ids)):
            raise ValueError("Agent capability IDs must be unique")
        if len(self.evidence_source_types) != len(set(self.evidence_source_types)):
            raise ValueError("Agent Evidence source types must be unique")
        return self


def create_m2_agent_definitions() -> tuple[AgentDefinition, AgentDefinition]:
    """Return the two implemented M2 Worker roles."""

    return (
        AgentDefinition(
            agent_id="business_data",
            version="1.0.0",
            description="负责只读查询商品规格和库存事实。",
            allowed_capability_ids=("get_product_spec", "search_inventory"),
            evidence_source_types=("database",),
            completion_criteria="返回获权业务事实、Evidence ID或明确未知与拒绝。",
            can_delegate=False,
            implementation_status="available",
        ),
        AgentDefinition(
            agent_id="knowledge",
            version="1.0.0",
            description="负责只读检索知识、查看上传文件和展开已有证据。",
            allowed_capability_ids=(
                "get_evidence_detail",
                "read_uploaded_file",
                "search_knowledge",
            ),
            evidence_source_types=("document", "artifact"),
            completion_criteria="返回获权文档事实、Evidence或Artifact ID及明确未知项。",
            can_delegate=False,
            implementation_status="available",
        ),
    )
