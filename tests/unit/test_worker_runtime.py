from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.runtime import (
    InMemoryWorkerTraceRecorder,
    TerminationPolicy,
    WorkerDispatcher,
    WorkerExecutionContext,
    WorkerHarnessFactory,
    WorkerRuntime,
    WorkerTerminationManager,
)
from app.llm.agent_schemas import HandoffDraft
from app.runtime.budget import AgentBudgetLimits, AgentBudgetTree, WorkerBudgetLimits
from app.runtime.context import (
    MissingRunContextError,
    RunContext,
    get_current_run_context,
)
from app.runtime.executor import HarnessExecutor
from app.runtime.trace import RunTrace
from app.schemas.agent import (
    AgentHandoff,
    BoundedJsonObject,
    ResourceUsage,
    WorkerResult,
)

ROOT_RUN_ID = UUID("00000000-0000-0000-0000-000000000511")
WORKER_RUN_ID = UUID("00000000-0000-0000-0000-000000000512")
HANDOFF_ID = UUID("00000000-0000-0000-0000-000000000513")
BUDGET_REF = UUID("00000000-0000-0000-0000-000000000514")
TRACE_ID = UUID("00000000-0000-0000-0000-000000000515")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000516")
USER_ID = UUID("00000000-0000-0000-0000-000000000517")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000518")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000519")


def usage(**overrides: int) -> ResourceUsage:
    values = {
        "model_calls": 0,
        "tool_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "duration_ms": 0,
    }
    values.update(overrides)
    return ResourceUsage(**values)


def context() -> RunContext:
    return RunContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=("amazon_operator",),
        market_scopes=("DE",),
        thread_id=THREAD_ID,
        trace_id=TRACE_ID,
    )


def root_trace() -> RunTrace:
    return RunTrace(
        id=ROOT_RUN_ID,
        tenant_id=TENANT_ID,
        trace_id=TRACE_ID,
        started_monotonic=100.0,
    )


def root_limits(**overrides: int) -> AgentBudgetLimits:
    values = {
        "max_model_calls": 8,
        "max_tool_calls": 8,
        "max_input_tokens": 4_000,
        "max_output_tokens": 2_000,
        "max_tasks": 4,
        "max_evidence": 12,
        "max_delegations": 4,
        "max_depth": 1,
        "total_timeout_ms": 5_000,
    }
    values.update(overrides)
    return AgentBudgetLimits(**values)


def worker_limits(**overrides: int) -> WorkerBudgetLimits:
    values = {
        "max_model_calls": 2,
        "max_tool_calls": 2,
        "max_repeat_tool_calls": 1,
        "max_input_tokens": 1_000,
        "max_output_tokens": 500,
        "max_evidence": 4,
        "timeout_ms": 1_000,
    }
    values.update(overrides)
    return WorkerBudgetLimits(**values)


def draft(**overrides: object) -> HandoffDraft:
    values: dict[str, object] = {
        "task_id": "inventory",
        "goal": "查询德国库存",
        "target_worker": "business_data",
        "public_context": BoundedJsonObject({"market": "DE"}),
        "constraints": ("只读",),
        "expected_output": "返回库存事实或明确未知",
        "completion_criteria": ("返回库存事实或明确未知",),
    }
    values.update(overrides)
    return HandoffDraft.model_validate(values)


def completed_result() -> WorkerResult:
    return WorkerResult(
        task_id="inventory",
        worker_id="business_data",
        execution_status="completed",
        business_outcome="answered",
        business_result=BoundedJsonObject({"available": 125}),
        public_summary="德国仓可售库存为125件。",
        evidence_ids=[EVIDENCE_ID],
        resource_usage=usage(model_calls=999, tool_calls=999),
    )


@dataclass
class CapturingHarnessFactory:
    harness: HarnessExecutor = field(
        default_factory=lambda: cast(HarnessExecutor, MagicMock(spec=HarnessExecutor))
    )
    calls: list[tuple[RunContext, RunTrace, object]] = field(default_factory=list)

    def create(
        self,
        trusted_context: RunContext,
        audit_run: RunTrace,
        budget: object,
    ) -> HarnessExecutor:
        self.calls.append((trusted_context, audit_run, budget))
        return self.harness


@dataclass
class RecordingWorker:
    worker_id: str = "business_data"
    calls: int = 0
    contexts: list[WorkerExecutionContext] = field(default_factory=list)
    received_handoffs: list[AgentHandoff] = field(default_factory=list)
    result: WorkerResult = field(default_factory=completed_result)
    exception: Exception | None = None
    delay_seconds: float = 0

    async def run(
        self,
        handoff: AgentHandoff,
        execution: WorkerExecutionContext,
    ) -> WorkerResult:
        self.calls += 1
        self.received_handoffs.append(handoff)
        self.contexts.append(execution)
        assert get_current_run_context() == context()
        execution.session.execute(
            text("INSERT INTO worker_writes(value) VALUES ('temporary')")
        )
        execution.budget.reserve_model_call()
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.exception is not None:
            raise self.exception
        return self.result.model_copy(deep=True)


@dataclass
class NoProgressWorker:
    worker_id: str = "business_data"
    calls: int = 0

    async def run(
        self,
        _handoff: AgentHandoff,
        _execution: WorkerExecutionContext,
    ) -> WorkerResult:
        self.calls += 1
        return WorkerResult(
            task_id="inventory",
            worker_id="business_data",
            execution_status="running",
            public_summary="尚未产生新结果。",
            resource_usage=usage(),
        )


@pytest.fixture
def sessions() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE worker_writes "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT NOT NULL)"
            )
        )
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


def runtime(
    sessions: sessionmaker[Session],
    worker: object,
    *,
    child_limits: WorkerBudgetLimits | None = None,
    termination_policy: TerminationPolicy | None = None,
) -> tuple[
    WorkerRuntime,
    AgentBudgetTree,
    CapturingHarnessFactory,
    InMemoryWorkerTraceRecorder,
]:
    budget_refs = iter(
        (
            BUDGET_REF,
            UUID("00000000-0000-0000-0000-000000000524"),
            UUID("00000000-0000-0000-0000-000000000525"),
            UUID("00000000-0000-0000-0000-000000000526"),
        )
    )
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(),
        id_factory=lambda: next(budget_refs),
    )
    harnesses = CapturingHarnessFactory()
    traces = InMemoryWorkerTraceRecorder()
    ids = iter(
        (
            WORKER_RUN_ID,
            HANDOFF_ID,
            UUID("00000000-0000-0000-0000-000000000522"),
            UUID("00000000-0000-0000-0000-000000000523"),
        )
    )
    dispatcher = WorkerDispatcher((worker,))  # type: ignore[arg-type]
    item = WorkerRuntime(
        trusted_context=context(),
        parent_run=root_trace(),
        budget_tree=tree,
        child_budget_limits=child_limits or worker_limits(),
        dispatcher=dispatcher,
        harness_factory=cast(WorkerHarnessFactory, harnesses),
        session_factory=sessions,
        trace_recorder=traces,
        termination=WorkerTerminationManager(
            termination_policy
            or TerminationPolicy(
                max_repeat_handoffs=1,
                max_no_progress_results=1,
            )
        ),
        id_factory=lambda: next(ids),
    )
    return item, tree, harnesses, traces


def persisted_write_count(sessions: sessionmaker[Session]) -> int:
    with sessions() as session:
        return (
            session.scalar(select(func.count()).select_from(text("worker_writes"))) or 0
        )


@pytest.mark.asyncio
async def test_runtime_builds_trusted_handoff_budget_harness_and_child_trace(
    sessions: sessionmaker[Session],
) -> None:
    worker = RecordingWorker()
    item, tree, harnesses, traces = runtime(sessions, worker)

    result = await item.invoke(draft())

    assert result.execution_status == "completed"
    assert result.business_outcome == "answered"
    assert result.resource_usage.model_calls == 1
    assert result.resource_usage.tool_calls == 0
    assert persisted_write_count(sessions) == 1
    assert worker.calls == 1
    handoff = worker.received_handoffs[0]
    assert handoff.handoff_id == HANDOFF_ID
    assert handoff.allocated_budget_ref == BUDGET_REF
    assert handoff.public_context == BoundedJsonObject({"market": "DE"})
    assert harnesses.calls[0][0] == context()
    assert harnesses.calls[0][1] == root_trace()
    assert worker.contexts[0].trusted_context == context()
    assert worker.contexts[0].can_delegate is False
    assert worker.contexts[0].worker_run.run_id == WORKER_RUN_ID
    assert worker.contexts[0].worker_run.parent_run_id == ROOT_RUN_ID
    assert worker.contexts[0].worker_run.root_run_id == ROOT_RUN_ID
    assert worker.contexts[0].worker_run.trace_id == TRACE_ID
    assert worker.contexts[0].worker_run.budget_ref == BUDGET_REF
    assert tree.snapshot().open_children == 0
    assert tree.snapshot().model_calls == 1
    assert tree.snapshot().evidence_count == 1

    records = traces.records()
    assert len(records) == 1
    assert records[0].execution_status == "completed"
    assert records[0].worker_run_id == WORKER_RUN_ID
    assert records[0].parent_run_id == ROOT_RUN_ID
    assert records[0].root_run_id == ROOT_RUN_ID
    assert records[0].safe_error is None
    with pytest.raises(MissingRunContextError):
        get_current_run_context()


@pytest.mark.asyncio
async def test_unknown_worker_has_no_fallback_and_starts_no_resources(
    sessions: sessionmaker[Session],
) -> None:
    worker = RecordingWorker()
    item, tree, harnesses, traces = runtime(sessions, worker)

    result = await item.invoke(draft(target_worker="knowledge"))

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.safe_errors[0].code == "INTERNAL_ERROR"
    assert worker.calls == 0
    assert harnesses.calls == []
    assert traces.records() == ()
    assert tree.snapshot().delegations == 0
    assert persisted_write_count(sessions) == 0


@pytest.mark.asyncio
async def test_worker_exception_rolls_back_savepoint_and_is_sanitized(
    sessions: sessionmaker[Session],
) -> None:
    worker = RecordingWorker(
        exception=RuntimeError(r"SELECT secret at C:\\private\\worker.py")
    )
    item, tree, _harnesses, traces = runtime(sessions, worker)

    result = await item.invoke(draft())

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.public_summary == "Worker执行失败。"
    assert result.safe_errors[0].message == "Worker执行失败。"
    assert "select secret" not in result.model_dump_json().casefold()
    assert "private" not in result.model_dump_json().casefold()
    assert persisted_write_count(sessions) == 0
    assert tree.snapshot().open_children == 0
    assert traces.records()[0].execution_status == "failed"


@pytest.mark.asyncio
async def test_worker_timeout_rolls_back_and_returns_timed_out(
    sessions: sessionmaker[Session],
) -> None:
    worker = RecordingWorker(delay_seconds=0.05)
    item, tree, _harnesses, traces = runtime(
        sessions,
        worker,
        child_limits=worker_limits(timeout_ms=10),
    )

    result = await item.invoke(draft())

    assert result.execution_status == "failed"
    assert result.business_outcome == "timed_out"
    assert result.safe_errors[0].code == "BUDGET_EXCEEDED"
    assert persisted_write_count(sessions) == 0
    assert tree.snapshot().open_children == 0
    assert traces.records()[0].business_outcome == "timed_out"


@pytest.mark.asyncio
async def test_repeated_handoff_stops_before_second_worker_call(
    sessions: sessionmaker[Session],
) -> None:
    worker = NoProgressWorker()
    item, tree, _harnesses, _traces = runtime(sessions, worker)

    first = await item.invoke(draft())
    second = await item.invoke(draft())

    assert first.execution_status == "running"
    assert second.execution_status == "failed"
    assert second.business_outcome == "system_error"
    assert second.safe_errors[0].code == "BUDGET_EXCEEDED"
    assert worker.calls == 1
    assert tree.snapshot().delegations == 1


@pytest.mark.asyncio
async def test_changed_handoff_cannot_evade_no_progress_limit(
    sessions: sessionmaker[Session],
) -> None:
    worker = NoProgressWorker()
    item, tree, _harnesses, traces = runtime(sessions, worker)

    first = await item.invoke(draft(public_context={"attempt": 1}))
    second = await item.invoke(draft(public_context={"attempt": 2}))

    assert first.execution_status == "running"
    assert second.execution_status == "failed"
    assert second.business_outcome == "system_error"
    assert worker.calls == 2
    assert tree.snapshot().delegations == 2
    assert traces.records()[-1].execution_status == "failed"


def test_dispatcher_rejects_duplicate_ids_and_runtime_contracts_are_not_state() -> None:
    first = RecordingWorker()
    second = RecordingWorker()
    with pytest.raises(ValueError, match="duplicate"):
        WorkerDispatcher((first, second))

    fields = set(WorkerExecutionContext.__dataclass_fields__)
    assert {"session", "harness", "budget", "trusted_context"} <= fields
    assert "chain_of_thought" not in fields
    assert "prompt" not in fields
    assert "messages" not in fields
