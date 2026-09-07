"""Checkpoint-safe state shell for the future engineered multi-Agent graph."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.agent import (
    AGENT_CONTRACT_VERSION,
    MAX_AGENT_REPLANS,
    MAX_AGENT_RESUMES,
    MAX_ARTIFACT_IDS,
    MAX_EVIDENCE_IDS,
    MAX_PROCESSED_REQUEST_IDS,
    AgentAction,
    AgentConversationMemory,
    BoundedJsonObject,
    BusinessOutcome,
    ExecutionStatus,
    PublicSummary,
    ResourceUsage,
    ShortText,
    TaskId,
    TaskPlan,
    WorkerObservation,
    WorkerResult,
    validate_status_pair,
)
from app.schemas.common import M1Schema


class EngineeredAgentState(M1Schema):
    """Only serializable, public-safe data required to resume future execution."""

    contract_version: Literal["m2-agent-contract-v1"] = AGENT_CONTRACT_VERSION
    run_id: UUID
    goal: str = Field(strict=True, min_length=1, max_length=2000)
    public_context: BoundedJsonObject = Field(
        default_factory=lambda: BoundedJsonObject({})
    )
    memory: AgentConversationMemory = Field(default_factory=AgentConversationMemory)
    processed_request_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_PROCESSED_REQUEST_IDS,
    )
    active_request_id: UUID | None = None
    resume_count: int = Field(default=0, ge=0, le=MAX_AGENT_RESUMES)
    replan_count: int = Field(default=0, ge=0, le=MAX_AGENT_REPLANS)
    plan: TaskPlan | None = None
    execution_status: ExecutionStatus
    business_outcome: BusinessOutcome | None = None
    current_task_id: TaskId | None = None
    pending_action: AgentAction | None = None
    observations: list[WorkerObservation] = Field(default_factory=list, max_length=48)
    worker_results: list[WorkerResult] = Field(default_factory=list, max_length=24)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=MAX_ARTIFACT_IDS)
    unknowns: list[ShortText] = Field(default_factory=list, max_length=12)
    public_summary: PublicSummary | None = None
    stop_reason: ShortText | None = None
    resource_usage: ResourceUsage

    @model_validator(mode="after")
    def validate_checkpoint_state(self) -> EngineeredAgentState:
        validate_status_pair(self.execution_status, self.business_outcome)
        task_ids = (
            {task.task_id for task in self.plan.tasks}
            if self.plan is not None
            else set()
        )
        if self.current_task_id is not None and self.current_task_id not in task_ids:
            raise ValueError("current task must exist in the plan")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("Evidence IDs must be unique")
        if len(self.artifact_ids) != len(set(self.artifact_ids)):
            raise ValueError("Artifact IDs must be unique")
        if len(self.unknowns) != len(set(self.unknowns)):
            raise ValueError("unknown items must be unique")
        if len(self.processed_request_ids) != len(set(self.processed_request_ids)):
            raise ValueError("processed request IDs must be unique")
        if self.active_request_id is not None and (
            self.active_request_id not in self.processed_request_ids
        ):
            raise ValueError("active request ID must be an accepted request")
        if self.replan_count > self.resume_count:
            raise ValueError("re-planning requires a resumed request")
        if self.execution_status in {"completed", "failed"}:
            if self.stop_reason is None or self.public_summary is None:
                raise ValueError(
                    "terminal state requires a public summary and stop reason"
                )
            if self.pending_action is not None or self.current_task_id is not None:
                raise ValueError("terminal state cannot retain pending work")
        if self.pending_action is not None and self.execution_status != "running":
            raise ValueError("only running state can retain a pending action")
        return self
