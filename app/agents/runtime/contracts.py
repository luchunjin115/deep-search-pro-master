"""Runtime-only Worker contracts kept outside checkpointable Agent state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.orm import Session

from app.llm.agent_schemas import HandoffDraft
from app.runtime.budget import ChildExecutionBudget
from app.runtime.context import RunContext
from app.runtime.executor import HarnessExecutor
from app.runtime.trace import RunTrace
from app.schemas.agent import AgentHandoff, WorkerResult


@dataclass(frozen=True, slots=True)
class WorkerRunTrace:
    """Program-generated parent/child identifiers for one Worker attempt."""

    run_id: UUID
    parent_run_id: UUID
    root_run_id: UUID
    trace_id: UUID
    budget_ref: UUID
    depth: int

    def __post_init__(self) -> None:
        if self.run_id in {self.parent_run_id, self.root_run_id}:
            raise ValueError("Worker run ID must differ from parent and root")
        if self.depth < 1:
            raise ValueError("Worker run depth must be positive")


@dataclass(frozen=True, slots=True)
class WorkerExecutionContext:
    """Trusted runtime objects passed directly to code, never to Agent state."""

    trusted_context: RunContext
    worker_run: WorkerRunTrace
    budget: ChildExecutionBudget
    harness: HarnessExecutor
    session: Session
    can_delegate: bool = False

    def __post_init__(self) -> None:
        if self.can_delegate:
            raise ValueError("M2-21.5 Workers cannot delegate")


@runtime_checkable
class WorkerHandler(Protocol):
    """One registered Worker implementation behind the generic dispatcher."""

    worker_id: str

    async def run(
        self,
        handoff: AgentHandoff,
        execution: WorkerExecutionContext,
    ) -> WorkerResult: ...


@runtime_checkable
class WorkerHarnessFactory(Protocol):
    """Build a Harness from server-owned identity, Trace, and child budget."""

    def create(
        self,
        trusted_context: RunContext,
        audit_run: RunTrace,
        budget: ChildExecutionBudget,
    ) -> HarnessExecutor: ...


@runtime_checkable
class WorkerInvoker(Protocol):
    """The narrow interface consumed by the existing Supervisor skeleton."""

    async def invoke(self, handoff: HandoffDraft) -> WorkerResult: ...


@runtime_checkable
class WorkerTraceRecorder(Protocol):
    """Persist or observe one child attempt without exposing storage to Workers."""

    def start(
        self,
        *,
        worker_run: WorkerRunTrace,
        tenant_id: UUID,
        task_id: str,
        worker_id: str,
    ) -> RunTrace | None: ...

    def finish(self, worker_run_id: UUID, result: WorkerResult) -> None: ...
