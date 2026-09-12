"""Strict, bounded contracts shared by the engineered multi-Agent runtime."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    Field,
    RootModel,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import AgentProviderOutputStage, ErrorCode, M1Schema

AGENT_CONTRACT_VERSION: Literal["m2-agent-contract-v1"] = "m2-agent-contract-v1"
MAX_TASKS = 24
MAX_EVIDENCE_IDS = 12
MAX_ARTIFACT_IDS = 12
MAX_JSON_KEYS = 32
MAX_JSON_LIST_ITEMS = 32
MAX_JSON_DEPTH = 5
MAX_JSON_BYTES = 16_384
MAX_MEMORY_TURNS = 8
MAX_PROCESSED_REQUEST_IDS = 16
MAX_AGENT_RESUMES = 4
MAX_AGENT_REPLANS = 1

TaskId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
    ),
]
CapabilityId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]{0,63}$",
    ),
]
WorkerId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]{0,63}$",
    ),
]
ShortText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
]
GoalText = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=2000
    ),
]
PublicSummary = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=1, max_length=4000
    ),
]

ExecutionStatus = Literal["waiting", "running", "waiting_user", "completed", "failed"]
BusinessOutcome = Literal[
    "answered",
    "partial",
    "no_evidence",
    "unsupported",
    "denied",
    "timed_out",
    "system_error",
]
EvidenceSourceType = Literal["database", "document", "web", "artifact"]

_SERVER_OWNED_JSON_KEYS = {
    "user",
    "user_id",
    "tenant",
    "tenant_id",
    "role",
    "roles",
    "permissions",
    "permission",
    "market_scopes",
    "run_context",
    "thread_id",
    "trace_id",
    "run_id",
    "root_run_id",
    "agent_run_id",
    "parent_run",
    "parent_run_id",
    "budget",
    "budget_ref",
    "budget_limits",
    "max_model_calls",
    "max_tool_calls",
    "max_repeat_tool_calls",
    "total_timeout_ms",
}
_SENSITIVE_JSON_KEYS = {
    "sql",
    "path",
    "local_path",
    "storage_key",
    "secret",
    "api_key",
    "password",
    "access_token",
    "refresh_token",
    "token",
    "stack",
    "stack_trace",
    "traceback",
    "exception",
    "raw_exception",
}
_UNSAFE_ERROR_PATTERNS = (
    re.compile(r"\btraceback\b", re.IGNORECASE),
    re.compile(r"\b(?:select|insert|update|delete|drop|alter)\s+", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]", re.IGNORECASE
    ),
    re.compile(
        r"(?:[A-Za-z]:[\\/]|\\\\|/(?:home|users|var|etc|tmp|workspace|mnt)/)",
        re.IGNORECASE,
    ),
)
_UNSAFE_MEMORY_PATTERNS = (
    re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|storage[_-]?key)\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(r"\btraceback\b", re.IGNORECASE),
    re.compile(r"\b(?:select|insert|update|delete|drop|alter)\s+", re.IGNORECASE),
    re.compile(
        r"(?:[A-Za-z]:[\\/]|\\\\|/(?:home|users|var|etc|tmp|workspace|mnt)/)",
        re.IGNORECASE,
    ),
)


def _validate_json_value(value: object, *, depth: int) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"JSON nesting depth cannot exceed {MAX_JSON_DEPTH}")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if isinstance(value, str):
        if len(value) > 4000:
            raise ValueError("JSON strings cannot exceed 4000 characters")
        return
    if isinstance(value, list):
        if len(value) > MAX_JSON_LIST_ITEMS:
            raise ValueError(f"JSON lists cannot exceed {MAX_JSON_LIST_ITEMS} items")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_JSON_KEYS:
            raise ValueError(f"JSON objects cannot exceed {MAX_JSON_KEYS} keys")
        for key, item in value.items():
            if not isinstance(key, str) or not 1 <= len(key) <= 64:
                raise ValueError("JSON object keys must be 1-64 character strings")
            normalized_key = re.sub(r"(?<!^)(?=[A-Z])", "_", key)
            normalized_key = normalized_key.replace("-", "_").casefold()
            if normalized_key in _SERVER_OWNED_JSON_KEYS:
                raise ValueError(
                    f"{key} is server-owned and cannot enter JSON payloads"
                )
            if normalized_key in _SENSITIVE_JSON_KEYS:
                raise ValueError(f"{key} is sensitive and cannot enter JSON payloads")
            _validate_json_value(item, depth=depth + 1)
        return
    raise ValueError("value is not JSON serializable")


def _ensure_unique(values: Sequence[object], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


class BoundedJsonObject(RootModel[dict[str, object]]):
    """A small JSON object with recursive bounds and no trusted/sensitive keys."""

    @model_validator(mode="after")
    def validate_bounded_json(self) -> BoundedJsonObject:
        _validate_json_value(self.root, depth=1)
        serialized = json.dumps(
            self.root,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(serialized) > MAX_JSON_BYTES:
            raise ValueError(f"JSON payload cannot exceed {MAX_JSON_BYTES} bytes")
        return self


class AgentMemoryTurn(M1Schema):
    """One untrusted conversation turn reduced to a safe bounded summary."""

    turn_id: UUID
    role: Literal["user", "assistant"]
    content_summary: str = Field(strict=True, min_length=1, max_length=1000)

    @field_validator("content_summary")
    @classmethod
    def reject_sensitive_memory_text(cls, value: str) -> str:
        if any(pattern.search(value) for pattern in _UNSAFE_MEMORY_PATTERNS):
            raise ValueError("conversation memory must not contain sensitive text")
        return value


class AgentConversationMemory(M1Schema):
    """Checkpoint-safe recent turns plus one deterministic older-turn summary."""

    safe_summary: str | None = Field(
        default=None,
        strict=True,
        min_length=1,
        max_length=2000,
    )
    summarized_turn_count: int = Field(default=0, ge=0, le=10_000)
    recent_turns: list[AgentMemoryTurn] = Field(
        default_factory=list,
        max_length=MAX_MEMORY_TURNS,
    )

    @field_validator("safe_summary")
    @classmethod
    def reject_sensitive_summary(cls, value: str | None) -> str | None:
        if value is not None and any(
            pattern.search(value) for pattern in _UNSAFE_MEMORY_PATTERNS
        ):
            raise ValueError("conversation summary must not contain sensitive text")
        return value

    @model_validator(mode="after")
    def validate_memory_shape(self) -> AgentConversationMemory:
        _ensure_unique(
            [turn.turn_id for turn in self.recent_turns],
            "conversation turn IDs",
        )
        if (self.summarized_turn_count == 0) != (self.safe_summary is None):
            raise ValueError("conversation summary count and text must agree")
        return self


class TaskAssignment(M1Schema):
    """An explicit assigned/unassigned state without embedding trusted identity."""

    status: Literal["unassigned", "assigned"]
    worker_id: WorkerId | None = None

    @model_validator(mode="after")
    def validate_assignment(self) -> TaskAssignment:
        if self.status == "unassigned" and self.worker_id is not None:
            raise ValueError("unassigned task cannot name a worker")
        if self.status == "assigned" and self.worker_id is None:
            raise ValueError("assigned task requires a worker")
        return self


class EvidenceRequirement(M1Schema):
    """Bounded evidence expectations for one task."""

    required: bool
    minimum_count: int = Field(ge=0, le=MAX_EVIDENCE_IDS)
    source_types: list[EvidenceSourceType] = Field(
        default_factory=list,
        max_length=4,
    )

    @model_validator(mode="after")
    def validate_requirement(self) -> EvidenceRequirement:
        _ensure_unique(self.source_types, "Evidence source types")
        if self.required and self.minimum_count < 1:
            raise ValueError("required Evidence must have a positive minimum count")
        if not self.required and self.minimum_count != 0:
            raise ValueError("optional Evidence must have a zero minimum count")
        return self


class AgentTask(M1Schema):
    """One bounded task node in a plan DAG."""

    task_id: TaskId
    goal: GoalText
    depends_on: list[TaskId] = Field(default_factory=list, max_length=MAX_TASKS - 1)
    required_capabilities: list[CapabilityId] = Field(
        default_factory=list,
        max_length=5,
    )
    assignment: TaskAssignment
    execution_status: ExecutionStatus = "waiting"
    completion_criteria: list[ShortText] = Field(min_length=1, max_length=8)
    evidence_requirement: EvidenceRequirement
    failure_impact: Literal["blocks_dependents", "allows_partial", "non_blocking"]

    @model_validator(mode="after")
    def validate_task_lists(self) -> AgentTask:
        _ensure_unique(self.depends_on, "task dependencies")
        _ensure_unique(self.required_capabilities, "required capabilities")
        _ensure_unique(self.completion_criteria, "completion criteria")
        return self


class TaskPlan(M1Schema):
    """A bounded directed acyclic task graph."""

    contract_version: Literal["m2-agent-contract-v1"] = AGENT_CONTRACT_VERSION
    plan_id: UUID
    goal: GoalText
    tasks: list[AgentTask] = Field(min_length=1, max_length=MAX_TASKS)

    @model_validator(mode="after")
    def validate_task_dag(self) -> TaskPlan:
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("duplicate task IDs are not allowed")
        known_ids = set(task_ids)
        dependencies = {task.task_id: set(task.depends_on) for task in self.tasks}

        for task_id, task_dependencies in dependencies.items():
            if task_id in task_dependencies:
                raise ValueError(f"task {task_id} cannot depend on itself")
            missing = task_dependencies - known_ids
            if missing:
                raise ValueError(
                    f"task dependency {min(missing)} does not exist in this plan"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("task dependency cycle is not allowed")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in dependencies[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in task_ids:
            visit(task_id)
        return self


class ExecuteCapabilityAction(M1Schema):
    """A model proposal to execute one named capability with business arguments."""

    type: Literal["execute_capability"] = "execute_capability"
    capability_id: CapabilityId
    arguments: BoundedJsonObject


class DelegateTaskAction(M1Schema):
    """A model proposal; trusted parent Run and budget are added later by runtime."""

    type: Literal["delegate_task"] = "delegate_task"
    task_id: TaskId
    target_worker: WorkerId


class AskUserAction(M1Schema):
    """Pause and ask one bounded public clarification question."""

    type: Literal["ask_user"] = "ask_user"
    question: PublicSummary
    requested_fields: list[ShortText] = Field(default_factory=list, max_length=8)


class FinishAction(M1Schema):
    """Finish normally with a business outcome supported by current state."""

    type: Literal["finish"] = "finish"
    public_summary: PublicSummary
    business_outcome: Literal["answered", "partial", "no_evidence"]
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=MAX_ARTIFACT_IDS)

    @model_validator(mode="after")
    def validate_reference_ids(self) -> FinishAction:
        _ensure_unique(self.evidence_ids, "Evidence IDs")
        _ensure_unique(self.artifact_ids, "Artifact IDs")
        return self


class CannotCompleteAction(M1Schema):
    """Stop without claiming a successful answer."""

    type: Literal["cannot_complete"] = "cannot_complete"
    public_summary: PublicSummary
    business_outcome: Literal[
        "no_evidence",
        "unsupported",
        "denied",
        "timed_out",
        "system_error",
    ]


AgentAction: TypeAlias = Annotated[
    ExecuteCapabilityAction
    | DelegateTaskAction
    | AskUserAction
    | FinishAction
    | CannotCompleteAction,
    Field(discriminator="type"),
]


class AgentDecision(M1Schema):
    """Exactly one structured action produced by one decision step."""

    action: AgentAction


class ResourceUsage(M1Schema):
    """Public-safe consumed resources, never authoritative budget limits."""

    model_calls: int = Field(ge=0, le=10_000)
    tool_calls: int = Field(ge=0, le=10_000)
    input_tokens: int = Field(ge=0, le=10_000_000)
    output_tokens: int = Field(ge=0, le=10_000_000)
    duration_ms: int = Field(ge=0, le=86_400_000)


class SafeAgentError(M1Schema):
    """A public error which cannot carry stack, SQL, local paths, or secrets."""

    code: ErrorCode
    message: str = Field(strict=True, min_length=1, max_length=300)
    retryable: bool
    field: str | None = Field(default=None, min_length=1, max_length=100)
    diagnostic_stage: AgentProviderOutputStage | None = None

    @field_validator("message")
    @classmethod
    def validate_public_message(cls, value: str) -> str:
        if any(pattern.search(value) for pattern in _UNSAFE_ERROR_PATTERNS):
            raise ValueError("error message must be public-safe")
        return value


class WorkerObservation(M1Schema):
    """One bounded, public-safe result observed after an attempted action."""

    observation_id: UUID
    status: Literal["success", "partial", "error", "rejected", "timeout"]
    public_summary: PublicSummary
    structured_result: BoundedJsonObject | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=MAX_ARTIFACT_IDS)
    unknowns: list[ShortText] = Field(default_factory=list, max_length=12)
    safe_error: SafeAgentError | None = None
    resource_usage: ResourceUsage

    @model_validator(mode="after")
    def validate_observation(self) -> WorkerObservation:
        _ensure_unique(self.evidence_ids, "Evidence IDs")
        _ensure_unique(self.artifact_ids, "Artifact IDs")
        _ensure_unique(self.unknowns, "unknown items")
        if self.status == "success" and self.safe_error is not None:
            raise ValueError("successful observation cannot include a safe error")
        if self.status in {"error", "rejected", "timeout"}:
            if self.safe_error is None:
                raise ValueError("failed observation requires a safe error")
            if (
                self.structured_result is not None
                or self.evidence_ids
                or self.artifact_ids
            ):
                raise ValueError(
                    "failed observation cannot include result, Evidence, or Artifact"
                )
        return self


class AgentHandoff(M1Schema):
    """A runtime-built handoff containing only public context and opaque IDs."""

    contract_version: Literal["m2-agent-contract-v1"] = AGENT_CONTRACT_VERSION
    handoff_id: UUID
    task_id: TaskId
    goal: GoalText
    target_worker: WorkerId
    public_context: BoundedJsonObject
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=MAX_ARTIFACT_IDS)
    constraints: list[ShortText] = Field(default_factory=list, max_length=12)
    expected_output: GoalText
    completion_criteria: list[ShortText] = Field(min_length=1, max_length=8)
    allocated_budget_ref: UUID

    @model_validator(mode="after")
    def validate_handoff_lists(self) -> AgentHandoff:
        _ensure_unique(self.evidence_ids, "Evidence IDs")
        _ensure_unique(self.artifact_ids, "Artifact IDs")
        _ensure_unique(self.constraints, "handoff constraints")
        _ensure_unique(self.completion_criteria, "completion criteria")
        return self


_ACTIVE_EXECUTION_STATUSES = {"waiting", "running", "waiting_user"}
_COMPLETED_OUTCOMES = {
    "answered",
    "partial",
    "no_evidence",
    "unsupported",
    "denied",
}
_FAILED_OUTCOMES = {"timed_out", "system_error"}


def validate_status_pair(
    execution_status: ExecutionStatus,
    business_outcome: BusinessOutcome | None,
) -> None:
    if execution_status in _ACTIVE_EXECUTION_STATUSES and business_outcome is not None:
        raise ValueError("active execution status cannot have a business outcome")
    if execution_status == "completed" and business_outcome not in _COMPLETED_OUTCOMES:
        raise ValueError(
            "completed execution status has an incompatible business outcome"
        )
    if execution_status == "failed" and business_outcome not in _FAILED_OUTCOMES:
        raise ValueError("failed execution status has an incompatible business outcome")


class WorkerResult(M1Schema):
    """One Worker's business result, observations, references, and safe failure data."""

    contract_version: Literal["m2-agent-contract-v1"] = AGENT_CONTRACT_VERSION
    task_id: TaskId
    worker_id: WorkerId
    execution_status: ExecutionStatus
    business_outcome: BusinessOutcome | None = None
    business_result: BoundedJsonObject | None = None
    public_summary: PublicSummary
    observations: list[WorkerObservation] = Field(default_factory=list, max_length=16)
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=MAX_EVIDENCE_IDS)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=MAX_ARTIFACT_IDS)
    unknowns: list[ShortText] = Field(default_factory=list, max_length=12)
    safe_errors: list[SafeAgentError] = Field(default_factory=list, max_length=8)
    resource_usage: ResourceUsage

    @model_validator(mode="after")
    def validate_worker_result(self) -> WorkerResult:
        validate_status_pair(self.execution_status, self.business_outcome)
        _ensure_unique(self.evidence_ids, "Evidence IDs")
        _ensure_unique(self.artifact_ids, "Artifact IDs")
        _ensure_unique(self.unknowns, "unknown items")
        if self.execution_status == "failed" and not self.safe_errors:
            raise ValueError("failed Worker result requires at least one safe error")
        if (
            self.execution_status != "failed"
            and self.business_outcome not in {"partial", "denied"}
            and self.safe_errors
        ):
            raise ValueError(
                "non-failed, non-partial Worker result cannot include safe errors"
            )
        return self
