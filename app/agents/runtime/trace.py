"""Bounded in-memory child Trace seam until M2-21.9 persistence lands."""

from __future__ import annotations

from threading import RLock
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.agents.runtime.contracts import WorkerRunTrace
from app.schemas.agent import (
    BusinessOutcome,
    ExecutionStatus,
    ResourceUsage,
    SafeAgentError,
    TaskId,
    WorkerId,
    WorkerResult,
    validate_status_pair,
)
from app.schemas.common import M1Schema


class WorkerRunRecord(M1Schema):
    """Public-safe child attempt record; it contains no runtime objects."""

    model_config = ConfigDict(frozen=True)

    worker_run_id: UUID
    parent_run_id: UUID
    root_run_id: UUID
    trace_id: UUID
    tenant_id: UUID
    budget_ref: UUID
    task_id: TaskId
    worker_id: WorkerId
    depth: int = Field(ge=1, le=8)
    execution_status: ExecutionStatus
    business_outcome: BusinessOutcome | None = None
    public_summary: str = Field(min_length=1, max_length=4000)
    safe_error: SafeAgentError | None = None
    resource_usage: ResourceUsage

    @model_validator(mode="after")
    def validate_status(self) -> WorkerRunRecord:
        validate_status_pair(self.execution_status, self.business_outcome)
        return self


class InMemoryWorkerTraceRecorder:
    """Thread-safe child Trace contract with no database schema expansion."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[UUID, WorkerRunRecord] = {}
        self._order: list[UUID] = []

    def start(
        self,
        *,
        worker_run: WorkerRunTrace,
        tenant_id: UUID,
        task_id: str,
        worker_id: str,
    ) -> None:
        with self._lock:
            if worker_run.run_id in self._records:
                raise ValueError("duplicate Worker run ID")
            record = WorkerRunRecord(
                worker_run_id=worker_run.run_id,
                parent_run_id=worker_run.parent_run_id,
                root_run_id=worker_run.root_run_id,
                trace_id=worker_run.trace_id,
                tenant_id=tenant_id,
                budget_ref=worker_run.budget_ref,
                task_id=task_id,
                worker_id=worker_id,
                depth=worker_run.depth,
                execution_status="running",
                public_summary="Worker执行中。",
                resource_usage=_zero_usage(),
            )
            self._records[worker_run.run_id] = record
            self._order.append(worker_run.run_id)

    def finish(self, worker_run_id: UUID, result: WorkerResult) -> None:
        with self._lock:
            current = self._records.get(worker_run_id)
            if current is None:
                raise ValueError("Worker run was not started")
            self._records[worker_run_id] = current.model_copy(
                update={
                    "execution_status": result.execution_status,
                    "business_outcome": result.business_outcome,
                    "public_summary": result.public_summary,
                    "safe_error": result.safe_errors[0] if result.safe_errors else None,
                    "resource_usage": result.resource_usage,
                }
            )

    def records(self) -> tuple[WorkerRunRecord, ...]:
        with self._lock:
            return tuple(
                self._records[item].model_copy(deep=True) for item in self._order
            )


def _zero_usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
    )
