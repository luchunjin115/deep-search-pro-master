"""Trusted persistence boundary for engineered multi-Agent runtime data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.agents.engineered_state import EngineeredAgentState
from app.agents.runtime.contracts import WorkerRunTrace
from app.core.errors import (
    AgentCheckpointConflictError,
    AgentCheckpointNotFoundError,
    AgentRequestConflictError,
    AgentRuntimePersistenceError,
    AgentTaskConflictError,
    CitationValidationError,
    ThreadNotFoundError,
)
from app.models.runtime import (
    AgentAnswerEvidence,
    AgentCheckpoint,
    AgentRun,
    AgentTaskDependency,
    AgentTaskRecord,
)
from app.repositories.agent_runtime import AgentRuntimeRepository
from app.runtime.budget import AgentBudgetRestore
from app.schemas.agent import (
    MAX_AGENT_RESUMES,
    AgentConversationMemory,
    BoundedJsonObject,
    BusinessOutcome,
    ExecutionStatus,
    TaskPlan,
    WorkerResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.evidence import AnswerEvidenceMapping, AnswerEvidenceReference

MAX_AGENT_CHECKPOINT_BYTES = 262_144


@dataclass(frozen=True, slots=True)
class SerializedAgentCheckpoint:
    """Canonical JSON payload plus integrity metadata ready for persistence."""

    payload: dict[str, object]
    sha256: str
    size_bytes: int
    execution_status: ExecutionStatus
    business_outcome: BusinessOutcome | None


@dataclass(frozen=True, slots=True)
class LoadedAgentCheckpoint:
    """A verified checkpoint plus its immutable database version."""

    checkpoint_id: UUID
    checkpoint_version: int
    trace_id: UUID
    state: EngineeredAgentState


@dataclass(frozen=True, slots=True)
class StartedWorkerRun:
    """A child audit row plus the claimed task version used on completion."""

    run: AgentRun
    task_version: int


def serialize_checkpoint_state(
    state: EngineeredAgentState,
) -> SerializedAgentCheckpoint:
    """Revalidate and canonically serialize only the strict checkpoint state shell."""

    validated = EngineeredAgentState.model_validate(
        state.model_dump(mode="json", round_trip=True)
    )
    payload = validated.model_dump(mode="json", round_trip=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_AGENT_CHECKPOINT_BYTES:
        raise ValueError(
            f"Agent checkpoint cannot exceed {MAX_AGENT_CHECKPOINT_BYTES} bytes"
        )
    return SerializedAgentCheckpoint(
        payload=payload,
        sha256=hashlib.sha256(encoded).hexdigest(),
        size_bytes=len(encoded),
        execution_status=validated.execution_status,
        business_outcome=validated.business_outcome,
    )


def _canonical_json(value: dict[str, object]) -> tuple[dict[str, object], str, int]:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_AGENT_CHECKPOINT_BYTES:
        raise ValueError(
            f"Persisted Agent payload cannot exceed {MAX_AGENT_CHECKPOINT_BYTES} bytes"
        )
    return value, hashlib.sha256(encoded).hexdigest(), len(encoded)


class AgentRuntimePersistenceService:
    """Apply trusted ownership, version, and integrity rules around Agent storage."""

    def __init__(self, repository: AgentRuntimeRepository) -> None:
        self._repository = repository

    def start_root_run(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        run_id: UUID,
        trace_id: UUID,
        plan: TaskPlan,
    ) -> AgentRun:
        """Create a supervisor root and its normalized task board atomically."""

        root = self.begin_root_run(
            user,
            thread_id=thread_id,
            run_id=run_id,
            trace_id=trace_id,
        )
        self.save_task_plan(
            user,
            thread_id=thread_id,
            root_run_id=run_id,
            plan=plan,
        )
        return root

    def begin_root_run(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        run_id: UUID,
        trace_id: UUID,
    ) -> AgentRun:
        """Persist the gateway root before the first fallible provider call."""

        try:
            thread = self._repository.find_owned_active_thread(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                for_update=True,
            )
            if thread is None:
                raise ThreadNotFoundError
            if (
                self._repository.find_owned_active_root(
                    tenant_id=user.tenant_id,
                    user_id=user.user_id,
                    thread_id=thread_id,
                )
                is not None
            ):
                raise AgentRequestConflictError
            root = self._repository.add_root_run(
                AgentRun(
                    id=run_id,
                    tenant_id=user.tenant_id,
                    thread_id=thread_id,
                    user_id=user.user_id,
                    trace_id=trace_id,
                    route="agent_gateway",
                    run_kind="supervisor",
                    root_run_id=run_id,
                    agent_id="supervisor",
                    depth=0,
                    status="running",
                )
            )
            return root
        except ThreadNotFoundError:
            raise
        except AgentRequestConflictError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def save_task_plan(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
        plan: TaskPlan,
    ) -> None:
        """Persist the validated initial task board before any Worker starts."""

        if any(task.execution_status != "waiting" for task in plan.tasks):
            raise AgentRuntimePersistenceError from None
        try:
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=root_run_id,
            )
            if self._repository.list_tasks(
                tenant_id=user.tenant_id,
                root_run_id=root.id,
            ):
                raise AgentRuntimePersistenceError
            task_rows = [
                AgentTaskRecord(
                    tenant_id=user.tenant_id,
                    root_run_id=root.id,
                    plan_id=plan.plan_id,
                    sequence_no=sequence_no,
                    task_id=task.task_id,
                    goal=task.goal,
                    required_capabilities=list(task.required_capabilities),
                    assignment_status=task.assignment.status,
                    worker_id=task.assignment.worker_id,
                    execution_status=task.execution_status,
                    completion_criteria=list(task.completion_criteria),
                    evidence_requirement=task.evidence_requirement.model_dump(
                        mode="json",
                        round_trip=True,
                    ),
                    failure_impact=task.failure_impact,
                )
                for sequence_no, task in enumerate(plan.tasks, start=1)
            ]
            dependencies = [
                AgentTaskDependency(
                    tenant_id=user.tenant_id,
                    root_run_id=root.id,
                    task_id=task.task_id,
                    depends_on_task_id=dependency,
                )
                for task in plan.tasks
                for dependency in task.depends_on
            ]
            self._repository.add_tasks(task_rows, dependencies)
        except AgentRuntimePersistenceError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def replace_waiting_task_plan(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
        plan: TaskPlan,
    ) -> None:
        """Replace only an unexecuted clarification plan during the single re-plan."""

        try:
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=root_run_id,
                for_update=True,
            )
            rows = self._repository.list_tasks(
                tenant_id=user.tenant_id,
                root_run_id=root.id,
            )
            if (
                root.status != "running"
                or not rows
                or any(
                    row.execution_status not in {"waiting", "waiting_user"}
                    or row.result_json is not None
                    for row in rows
                )
                or self._repository.count_worker_runs(
                    tenant_id=user.tenant_id,
                    root_run_id=root.id,
                )
                != 0
            ):
                raise AgentRuntimePersistenceError
            self._repository.delete_task_board(
                tenant_id=user.tenant_id,
                root_run_id=root.id,
            )
            self.save_task_plan(
                user,
                thread_id=thread_id,
                root_run_id=root.id,
                plan=plan,
            )
        except AgentRuntimePersistenceError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def synchronize_task_board(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        state: EngineeredAgentState,
    ) -> None:
        """Copy final control status to rows without replacing Worker results."""

        if state.plan is None:
            return
        try:
            self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=state.run_id,
            )
            rows = self._repository.list_tasks(
                tenant_id=user.tenant_id,
                root_run_id=state.run_id,
            )
            if [row.task_id for row in rows] != [
                task.task_id for task in state.plan.tasks
            ]:
                raise AgentRuntimePersistenceError
            results = {result.task_id: result for result in state.worker_results}
            for row, task in zip(rows, state.plan.tasks, strict=True):
                result = results.get(task.task_id)
                outcome = result.business_outcome if result is not None else None
                if outcome is None and task.execution_status in {"completed", "failed"}:
                    outcome = state.business_outcome
                if (
                    row.execution_status != task.execution_status
                    or row.business_outcome != outcome
                ):
                    row.execution_status = task.execution_status
                    row.business_outcome = outcome
                    row.row_version += 1
            self._repository.flush()
        except AgentRuntimePersistenceError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def list_tool_names(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
    ) -> list[str]:
        """Return stable unique Tool names from the exact owned run tree."""

        try:
            self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=root_run_id,
            )
            return self._repository.list_tool_names(
                tenant_id=user.tenant_id,
                root_run_id=root_run_id,
            )
        except AgentRuntimePersistenceError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def start_worker_run(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        worker_run: WorkerRunTrace,
        task_id: str,
        worker_id: str,
    ) -> StartedWorkerRun:
        """Persist one program-generated child run and claim its assigned task."""

        try:
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=worker_run.root_run_id,
            )
            task = self._repository.find_task(
                tenant_id=user.tenant_id,
                root_run_id=root.id,
                task_id=task_id,
                for_update=True,
            )
            valid_trace = (
                worker_run.parent_run_id == root.id
                and worker_run.trace_id == root.trace_id
                and worker_run.depth == 1
            )
            valid_task = (
                task is not None
                and task.assignment_status == "assigned"
                and task.worker_id == worker_id
                and task.execution_status == "waiting"
            )
            if not valid_trace or not valid_task:
                raise AgentRuntimePersistenceError
            child = self._repository.add_worker_run(
                AgentRun(
                    id=worker_run.run_id,
                    tenant_id=user.tenant_id,
                    thread_id=thread_id,
                    user_id=user.user_id,
                    trace_id=worker_run.trace_id,
                    route=f"worker:{worker_id}",
                    run_kind="worker",
                    root_run_id=root.id,
                    parent_run_id=worker_run.parent_run_id,
                    agent_id=worker_id,
                    task_id=task_id,
                    budget_ref=worker_run.budget_ref,
                    depth=worker_run.depth,
                    status="running",
                )
            )
            assert task is not None
            task.execution_status = "running"
            task.row_version += 1
            self._repository.flush()
            return StartedWorkerRun(run=child, task_version=task.row_version)
        except AgentRuntimePersistenceError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def record_worker_result(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
        worker_run_id: UUID,
        result: WorkerResult,
        expected_task_version: int,
    ) -> AgentRun:
        """Store one strict public-safe Worker result without raw runtime objects."""

        try:
            child = self._repository.find_owned_worker_run(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                root_run_id=root_run_id,
                worker_run_id=worker_run_id,
            )
            task = self._repository.find_task(
                tenant_id=user.tenant_id,
                root_run_id=root_run_id,
                task_id=result.task_id,
                for_update=True,
            )
            if (
                child is None
                or task is None
                or child.task_id != result.task_id
                or child.agent_id != result.worker_id
            ):
                raise AgentRuntimePersistenceError
            if task.row_version != expected_task_version:
                raise AgentTaskConflictError

            payload = result.model_dump(mode="json", round_trip=True)
            payload, payload_hash, _ = _canonical_json(payload)
            now = datetime.now(UTC)
            child.status = result.execution_status
            child.business_outcome = result.business_outcome
            child.model_call_count = result.resource_usage.model_calls
            child.tool_call_count = result.resource_usage.tool_calls
            child.duration_ms = result.resource_usage.duration_ms
            child.finished_at = (
                now if result.execution_status in {"completed", "failed"} else None
            )
            child.error_code = (
                result.safe_errors[0].code if result.safe_errors else None
            )
            child.error_message = (
                result.safe_errors[0].message if result.safe_errors else None
            )
            task.execution_status = result.execution_status
            task.business_outcome = result.business_outcome
            task.result_json = payload
            task.result_sha256 = payload_hash
            task.row_version += 1
            self._repository.flush()
            return child
        except (AgentRuntimePersistenceError, AgentTaskConflictError):
            raise
        except (SQLAlchemyError, TypeError, ValueError):
            raise AgentRuntimePersistenceError from None

    def save_checkpoint(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        state: EngineeredAgentState,
        expected_version: int,
    ) -> LoadedAgentCheckpoint:
        """Append an immutable checkpoint using optimistic version comparison."""

        try:
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=state.run_id,
                for_update=True,
            )
            serialized = serialize_checkpoint_state(state)
            self._validate_checkpoint_task_board(user, root.id, state)
            latest = self._repository.latest_checkpoint(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                root_run_id=root.id,
            )
            current_version = latest.checkpoint_version if latest is not None else 0
            if expected_version < 0 or expected_version != current_version:
                raise AgentCheckpointConflictError
            checkpoint = self._repository.add_checkpoint(
                AgentCheckpoint(
                    tenant_id=user.tenant_id,
                    root_run_id=root.id,
                    thread_id=thread_id,
                    user_id=user.user_id,
                    checkpoint_version=current_version + 1,
                    state_contract_version=state.contract_version,
                    state_json=serialized.payload,
                    state_sha256=serialized.sha256,
                    execution_status=state.execution_status,
                    business_outcome=state.business_outcome,
                )
            )
            root.status = state.execution_status
            root.business_outcome = state.business_outcome
            root.model_call_count = state.resource_usage.model_calls
            root.tool_call_count = state.resource_usage.tool_calls
            root.duration_ms = state.resource_usage.duration_ms
            root.finished_at = (
                datetime.now(UTC)
                if state.execution_status in {"completed", "failed"}
                else None
            )
            self._repository.flush()
            return LoadedAgentCheckpoint(
                checkpoint_id=checkpoint.id,
                checkpoint_version=checkpoint.checkpoint_version,
                trace_id=root.trace_id,
                state=state,
            )
        except AgentCheckpointConflictError:
            raise
        except AgentRuntimePersistenceError:
            raise
        except (SQLAlchemyError, ValidationError, TypeError, ValueError):
            raise AgentRuntimePersistenceError from None

    def load_latest_checkpoint(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
    ) -> LoadedAgentCheckpoint:
        """Restore only inside the exact tenant/user/thread/root boundary."""

        try:
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=root_run_id,
            )
            checkpoint = self._repository.latest_checkpoint(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                root_run_id=root_run_id,
            )
            if checkpoint is None:
                raise AgentCheckpointNotFoundError
            state = EngineeredAgentState.model_validate(checkpoint.state_json)
            serialized = serialize_checkpoint_state(state)
            if (
                state.run_id != root_run_id
                or serialized.sha256 != checkpoint.state_sha256
                or state.execution_status != checkpoint.execution_status
                or state.business_outcome != checkpoint.business_outcome
            ):
                raise AgentRuntimePersistenceError
            return LoadedAgentCheckpoint(
                checkpoint_id=checkpoint.id,
                checkpoint_version=checkpoint.checkpoint_version,
                trace_id=root.trace_id,
                state=state,
            )
        except AgentCheckpointNotFoundError:
            raise
        except AgentRuntimePersistenceError:
            raise
        except (SQLAlchemyError, ValidationError, TypeError, ValueError):
            raise AgentRuntimePersistenceError from None

    def load_checkpoint_for_request(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        request_id: UUID,
    ) -> LoadedAgentCheckpoint | None:
        """Load an already processed request for safe idempotent replay."""

        try:
            checkpoint = self._repository.find_checkpoint_by_request_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                request_id=request_id,
            )
            if checkpoint is None:
                return None
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=checkpoint.root_run_id,
            )
            return self._validated_checkpoint(root, checkpoint)
        except AgentRuntimePersistenceError:
            raise
        except (SQLAlchemyError, ValidationError, TypeError, ValueError):
            raise AgentRuntimePersistenceError from None

    def claim_latest_waiting_checkpoint(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        request_id: UUID,
        memory: AgentConversationMemory,
        public_context: BoundedJsonObject,
    ) -> LoadedAgentCheckpoint | None:
        """Atomically claim one waiting root and checkpoint the accepted request."""

        try:
            thread = self._repository.find_owned_active_thread(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                for_update=True,
            )
            if thread is None:
                raise ThreadNotFoundError
            root = self._repository.find_latest_owned_waiting_root(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                for_update=True,
            )
            if root is None:
                return None
            checkpoint = self._repository.latest_checkpoint(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
                root_run_id=root.id,
            )
            if checkpoint is None:
                raise AgentRuntimePersistenceError
            loaded = self._validated_checkpoint(root, checkpoint)
            state = loaded.state
            if (
                state.execution_status != "waiting_user"
                or state.plan is None
                or state.current_task_id is None
                or state.resume_count >= MAX_AGENT_RESUMES
                or request_id in state.processed_request_ids
            ):
                raise AgentRuntimePersistenceError
            claimed_plan = state.plan.model_copy(
                update={
                    "tasks": [
                        task.model_copy(update={"execution_status": "waiting"})
                        if task.task_id == state.current_task_id
                        else task.model_copy(deep=True)
                        for task in state.plan.tasks
                    ]
                },
                deep=True,
            )
            claimed = EngineeredAgentState.model_validate(
                state.model_dump(mode="json", round_trip=True)
                | {
                    "public_context": public_context.model_dump(
                        mode="json", round_trip=True
                    ),
                    "memory": memory.model_dump(mode="json", round_trip=True),
                    "processed_request_ids": [
                        *state.processed_request_ids,
                        request_id,
                    ],
                    "active_request_id": request_id,
                    "resume_count": state.resume_count + 1,
                    "plan": claimed_plan.model_dump(mode="json", round_trip=True),
                    "execution_status": "running",
                    "business_outcome": None,
                    "pending_action": None,
                    "public_summary": None,
                    "stop_reason": None,
                }
            )
            self.synchronize_task_board(
                user,
                thread_id=thread_id,
                state=claimed,
            )
            return self.save_checkpoint(
                user,
                thread_id=thread_id,
                state=claimed,
                expected_version=loaded.checkpoint_version,
            )
        except (ThreadNotFoundError, AgentRuntimePersistenceError):
            raise
        except (SQLAlchemyError, ValidationError, TypeError, ValueError):
            raise AgentRuntimePersistenceError from None

    def load_budget_restore(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        state: EngineeredAgentState,
    ) -> AgentBudgetRestore:
        """Reconstruct trusted cumulative usage and Tool signatures for resume."""

        try:
            self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=state.run_id,
            )
            tool_calls = self._repository.list_tool_calls(
                tenant_id=user.tenant_id,
                root_run_id=state.run_id,
            )
            task_ids = (
                tuple(task.task_id for task in state.plan.tasks)
                if state.plan is not None
                else ()
            )
            return AgentBudgetRestore(
                model_calls=state.resource_usage.model_calls,
                tool_calls=len(tool_calls),
                input_tokens=state.resource_usage.input_tokens,
                output_tokens=state.resource_usage.output_tokens,
                duration_ms=state.resource_usage.duration_ms,
                evidence_ids=tuple(state.evidence_ids),
                task_ids=task_ids,
                delegations=self._repository.count_worker_runs(
                    tenant_id=user.tenant_id,
                    root_run_id=state.run_id,
                ),
                tool_calls_by_signature=tuple(
                    (row.tool_name, row.arguments_summary) for row in tool_calls
                ),
            )
        except AgentRuntimePersistenceError:
            raise
        except (SQLAlchemyError, TypeError, ValueError):
            raise AgentRuntimePersistenceError from None

    def save_answer_evidence(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        mapping: AnswerEvidenceMapping,
    ) -> AnswerEvidenceMapping:
        """Persist a final ordered allow-list, rejecting missing or changed Evidence."""

        try:
            root = self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=mapping.root_run_id,
            )
            if root.status != "completed":
                raise CitationValidationError
            evidence_ids = [reference.evidence_id for reference in mapping.references]
            found_ids = self._repository.find_evidence_ids(
                tenant_id=user.tenant_id,
                evidence_ids=evidence_ids,
            )
            if found_ids != set(evidence_ids):
                raise CitationValidationError
            existing = self._repository.list_answer_evidence(
                tenant_id=user.tenant_id,
                root_run_id=root.id,
            )
            existing_ids = [row.evidence_id for row in existing]
            if existing:
                if existing_ids != evidence_ids:
                    raise CitationValidationError
                return mapping
            self._repository.add_answer_evidence(
                [
                    AgentAnswerEvidence(
                        tenant_id=user.tenant_id,
                        root_run_id=root.id,
                        evidence_id=reference.evidence_id,
                        citation_ordinal=ordinal,
                    )
                    for ordinal, reference in enumerate(mapping.references, start=1)
                ]
            )
            return mapping
        except CitationValidationError:
            raise
        except AgentRuntimePersistenceError:
            raise
        except SQLAlchemyError:
            raise AgentRuntimePersistenceError from None

    def load_answer_evidence(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
    ) -> AnswerEvidenceMapping:
        """Load the stable final label mapping inside the trusted run boundary."""

        try:
            self._require_root(
                user,
                thread_id=thread_id,
                root_run_id=root_run_id,
            )
            rows = self._repository.list_answer_evidence(
                tenant_id=user.tenant_id,
                root_run_id=root_run_id,
            )
            return AnswerEvidenceMapping(
                root_run_id=root_run_id,
                references=[
                    AnswerEvidenceReference(
                        citation_label=f"[E{row.citation_ordinal}]",
                        evidence_id=row.evidence_id,
                    )
                    for row in rows
                ],
            )
        except AgentRuntimePersistenceError:
            raise
        except (SQLAlchemyError, ValidationError):
            raise AgentRuntimePersistenceError from None

    def _require_root(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        root_run_id: UUID,
        for_update: bool = False,
    ) -> AgentRun:
        root = self._repository.find_owned_root_run(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            thread_id=thread_id,
            root_run_id=root_run_id,
            for_update=for_update,
        )
        if root is None:
            raise AgentCheckpointNotFoundError
        return root

    @staticmethod
    def _validated_checkpoint(
        root: AgentRun,
        checkpoint: AgentCheckpoint,
    ) -> LoadedAgentCheckpoint:
        state = EngineeredAgentState.model_validate(checkpoint.state_json)
        serialized = serialize_checkpoint_state(state)
        if (
            state.run_id != root.id
            or serialized.sha256 != checkpoint.state_sha256
            or state.execution_status != checkpoint.execution_status
            or state.business_outcome != checkpoint.business_outcome
        ):
            raise AgentRuntimePersistenceError
        return LoadedAgentCheckpoint(
            checkpoint_id=checkpoint.id,
            checkpoint_version=checkpoint.checkpoint_version,
            trace_id=root.trace_id,
            state=state,
        )

    def _validate_checkpoint_task_board(
        self,
        user: CurrentUser,
        root_run_id: UUID,
        state: EngineeredAgentState,
    ) -> None:
        if state.plan is None:
            return
        rows = self._repository.list_tasks(
            tenant_id=user.tenant_id,
            root_run_id=root_run_id,
        )
        persisted_identity = [
            (row.plan_id, row.sequence_no, row.task_id) for row in rows
        ]
        checkpoint_identity = [
            (state.plan.plan_id, sequence_no, task.task_id)
            for sequence_no, task in enumerate(state.plan.tasks, start=1)
        ]
        if persisted_identity != checkpoint_identity:
            raise AgentRuntimePersistenceError
