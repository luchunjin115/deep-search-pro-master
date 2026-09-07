"""Strict, bounded requests and outputs for engineered Agent model providers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.capabilities.contracts import CapabilityResolution, ResolvedCapability
from app.schemas.agent import (
    MAX_ARTIFACT_IDS,
    MAX_EVIDENCE_IDS,
    MAX_TASKS,
    AgentTask,
    BoundedJsonObject,
    CannotCompleteAction,
    DelegateTaskAction,
    FinishAction,
    GoalText,
    ShortText,
    TaskId,
    TaskPlan,
    WorkerId,
    WorkerObservation,
    WorkerResult,
)
from app.schemas.common import M1Schema

AGENT_PROVIDER_CONTRACT_VERSION: Literal["m2-agent-provider-contract-v1"] = (
    "m2-agent-provider-contract-v1"
)
MAX_PROVIDER_REQUEST_BYTES = 65_536
MAX_PROVIDER_OBSERVATIONS = 16
MAX_PROVIDER_WORKERS = 8


def _empty_public_context() -> BoundedJsonObject:
    return BoundedJsonObject({})


def _ensure_unique(values: Sequence[object], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _reference_ids(
    observations: Sequence[WorkerObservation],
    worker_results: Sequence[WorkerResult],
) -> tuple[frozenset[UUID], frozenset[UUID]]:
    evidence_ids: set[UUID] = set()
    artifact_ids: set[UUID] = set()
    for observation in observations:
        evidence_ids.update(observation.evidence_ids)
        artifact_ids.update(observation.artifact_ids)
    for result in worker_results:
        evidence_ids.update(result.evidence_ids)
        artifact_ids.update(result.artifact_ids)
    return frozenset(evidence_ids), frozenset(artifact_ids)


class _BoundedProviderRequest(M1Schema):
    """Base for server-built, model-safe requests with one total byte ceiling."""

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_total_size(self) -> _BoundedProviderRequest:
        serialized = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(serialized) > MAX_PROVIDER_REQUEST_BYTES:
            raise ValueError(
                f"provider request cannot exceed {MAX_PROVIDER_REQUEST_BYTES} bytes"
            )
        return self


class WorkerCapabilityProfile(M1Schema):
    """One public Worker summary paired with its Resolver-approved capabilities."""

    model_config = ConfigDict(frozen=True)

    worker: ResolvedCapability
    capabilities: CapabilityResolution

    @model_validator(mode="after")
    def validate_worker_mapping(self) -> WorkerCapabilityProfile:
        if self.worker.kind != "agent":
            raise ValueError("worker profile requires an Agent capability")
        if self.capabilities.requesting_agent_id != self.worker.capability_id:
            raise ValueError("capabilities must name the same requesting Agent")
        if not 1 <= len(self.capabilities.capabilities) <= 5:
            raise ValueError("worker profile must contain 1-5 capabilities")
        if any(item.kind == "agent" for item in self.capabilities.capabilities):
            raise ValueError("worker profile may contain only non-Agent capabilities")
        return self


class PlannerRequest(_BoundedProviderRequest):
    """A goal plus only the safe capabilities and public context a planner may see."""

    contract_version: Literal["m2-agent-provider-contract-v1"] = (
        AGENT_PROVIDER_CONTRACT_VERSION
    )
    goal: GoalText
    available_workers: tuple[WorkerCapabilityProfile, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PROVIDER_WORKERS,
    )
    public_context: BoundedJsonObject = Field(default_factory=_empty_public_context)

    @model_validator(mode="after")
    def validate_unique_workers(self) -> PlannerRequest:
        _ensure_unique(
            [item.worker.capability_id for item in self.available_workers],
            "available Worker IDs",
        )
        return self


class DecisionRequest(_BoundedProviderRequest):
    """One active task with bounded public observations and safe candidates."""

    contract_version: Literal["m2-agent-provider-contract-v1"] = (
        AGENT_PROVIDER_CONTRACT_VERSION
    )
    plan: TaskPlan
    active_task_id: TaskId
    available_capabilities: CapabilityResolution
    public_context: BoundedJsonObject = Field(default_factory=_empty_public_context)
    observations: tuple[WorkerObservation, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PROVIDER_OBSERVATIONS,
    )
    worker_results: tuple[WorkerResult, ...] = Field(
        default_factory=tuple,
        max_length=MAX_TASKS,
    )

    @model_validator(mode="after")
    def validate_state_references(self) -> DecisionRequest:
        tasks = {task.task_id: task for task in self.plan.tasks}
        if self.active_task_id not in tasks:
            raise ValueError("active task does not exist in the current plan")
        requesting_agent_id = self.available_capabilities.requesting_agent_id
        if (
            requesting_agent_id is not None
            and tasks[self.active_task_id].assignment.worker_id != requesting_agent_id
        ):
            raise ValueError(
                "capability resolution does not match the active task Worker"
            )
        _ensure_unique(
            [item.observation_id for item in self.observations],
            "observation IDs",
        )
        result_keys = [(item.task_id, item.worker_id) for item in self.worker_results]
        _ensure_unique(result_keys, "Worker result task/Worker pairs")
        if any(item.task_id not in tasks for item in self.worker_results):
            raise ValueError("Worker result task does not exist in the current plan")
        return self

    @property
    def reference_ids(self) -> tuple[frozenset[UUID], frozenset[UUID]]:
        return _reference_ids(self.observations, self.worker_results)

    @property
    def active_task(self) -> AgentTask:
        return next(
            task for task in self.plan.tasks if task.task_id == self.active_task_id
        )


class HandoffRequest(_BoundedProviderRequest):
    """Inputs for a model-authored public draft, without trusted Run or budget data."""

    contract_version: Literal["m2-agent-provider-contract-v1"] = (
        AGENT_PROVIDER_CONTRACT_VERSION
    )
    plan: TaskPlan
    delegation: DelegateTaskAction
    available_workers: CapabilityResolution
    public_context: BoundedJsonObject = Field(default_factory=_empty_public_context)
    observations: tuple[WorkerObservation, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PROVIDER_OBSERVATIONS,
    )
    worker_results: tuple[WorkerResult, ...] = Field(
        default_factory=tuple,
        max_length=MAX_TASKS,
    )

    @model_validator(mode="after")
    def validate_delegation(self) -> HandoffRequest:
        task_ids = {task.task_id for task in self.plan.tasks}
        if self.delegation.task_id not in task_ids:
            raise ValueError("delegated task does not exist in the current plan")
        if any(item.kind != "agent" for item in self.available_workers.capabilities):
            raise ValueError("available_workers may contain only Agent capabilities")
        worker_ids = {
            item.capability_id for item in self.available_workers.capabilities
        }
        if self.delegation.target_worker not in worker_ids:
            raise ValueError("delegation target is not an available Worker")
        _ensure_unique(
            [item.observation_id for item in self.observations],
            "observation IDs",
        )
        result_keys = [(item.task_id, item.worker_id) for item in self.worker_results]
        _ensure_unique(result_keys, "Worker result task/Worker pairs")
        if any(item.task_id not in task_ids for item in self.worker_results):
            raise ValueError("Worker result task does not exist in the current plan")
        return self

    @property
    def delegated_task(self) -> AgentTask:
        return next(
            task for task in self.plan.tasks if task.task_id == self.delegation.task_id
        )

    @property
    def reference_ids(self) -> tuple[frozenset[UUID], frozenset[UUID]]:
        return _reference_ids(self.observations, self.worker_results)


class HandoffDraft(M1Schema):
    """Model-safe Handoff content; Runtime adds handoff and budget references later."""

    model_config = ConfigDict(frozen=True)

    contract_version: Literal["m2-agent-provider-contract-v1"] = (
        AGENT_PROVIDER_CONTRACT_VERSION
    )
    task_id: TaskId
    goal: GoalText
    target_worker: WorkerId
    public_context: BoundedJsonObject
    evidence_ids: tuple[UUID, ...] = Field(
        default_factory=tuple,
        max_length=MAX_EVIDENCE_IDS,
    )
    artifact_ids: tuple[UUID, ...] = Field(
        default_factory=tuple,
        max_length=MAX_ARTIFACT_IDS,
    )
    constraints: tuple[ShortText, ...] = Field(default_factory=tuple, max_length=12)
    expected_output: GoalText
    completion_criteria: tuple[ShortText, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_unique_lists(self) -> HandoffDraft:
        _ensure_unique(self.evidence_ids, "Evidence IDs")
        _ensure_unique(self.artifact_ids, "Artifact IDs")
        _ensure_unique(self.constraints, "handoff constraints")
        _ensure_unique(self.completion_criteria, "completion criteria")
        return self


TerminalAnswerAction: TypeAlias = Annotated[
    FinishAction | CannotCompleteAction,
    Field(discriminator="type"),
]


class AgentAnswer(M1Schema):
    """A final answer can only finish or explicitly report that it cannot complete."""

    model_config = ConfigDict(frozen=True)

    contract_version: Literal["m2-agent-provider-contract-v1"] = (
        AGENT_PROVIDER_CONTRACT_VERSION
    )
    action: TerminalAnswerAction


class AnswerRequest(_BoundedProviderRequest):
    """Public worker results used to produce one terminal, reference-checked answer."""

    contract_version: Literal["m2-agent-provider-contract-v1"] = (
        AGENT_PROVIDER_CONTRACT_VERSION
    )
    goal: GoalText
    public_context: BoundedJsonObject = Field(default_factory=_empty_public_context)
    worker_results: tuple[WorkerResult, ...] = Field(
        default_factory=tuple,
        max_length=MAX_TASKS,
    )

    @model_validator(mode="after")
    def validate_worker_results(self) -> AnswerRequest:
        result_keys = [(item.task_id, item.worker_id) for item in self.worker_results]
        _ensure_unique(result_keys, "Worker result task/Worker pairs")
        return self

    @property
    def reference_ids(self) -> tuple[frozenset[UUID], frozenset[UUID]]:
        return _reference_ids((), self.worker_results)
