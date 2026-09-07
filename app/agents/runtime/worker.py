"""Reusable bounded Worker Runtime for one exact dispatched handoff."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from types import MappingProxyType
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.agents.runtime.contracts import (
    WorkerExecutionContext,
    WorkerHandler,
    WorkerHarnessFactory,
    WorkerRunTrace,
    WorkerTraceRecorder,
)
from app.agents.runtime.dispatcher import WorkerDispatcher
from app.agents.runtime.termination import WorkerTerminationManager
from app.core.errors import ApplicationError, BudgetExceededError
from app.llm.agent_schemas import HandoffDraft
from app.runtime.budget import (
    AgentBudgetTree,
    ChildBudgetUsage,
    ChildExecutionBudget,
    WorkerBudgetLimits,
)
from app.runtime.context import RunContext, bind_run_context
from app.runtime.trace import RunTrace
from app.schemas.agent import (
    AgentHandoff,
    ResourceUsage,
    SafeAgentError,
    WorkerResult,
)


class WorkerRuntime:
    """Allocate, execute, isolate, measure, and safely finish one Worker attempt."""

    def __init__(
        self,
        *,
        trusted_context: RunContext,
        parent_run: RunTrace,
        budget_tree: AgentBudgetTree,
        child_budget_limits: WorkerBudgetLimits | Mapping[str, WorkerBudgetLimits],
        dispatcher: WorkerDispatcher,
        harness_factory: WorkerHarnessFactory,
        session_factory: sessionmaker[Session],
        trace_recorder: WorkerTraceRecorder,
        termination: WorkerTerminationManager,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if trusted_context.tenant_id != parent_run.tenant_id:
            raise ValueError("trusted context and parent run tenant mismatch")
        if trusted_context.trace_id != parent_run.trace_id:
            raise ValueError("trusted context and parent run trace mismatch")
        if budget_tree.root_run_id != parent_run.id:
            raise ValueError("budget tree and parent run mismatch")
        self._trusted_context = trusted_context
        self._parent_run = parent_run
        self._budget_tree = budget_tree
        self._child_budget_limits = (
            child_budget_limits
            if isinstance(child_budget_limits, WorkerBudgetLimits)
            else MappingProxyType(dict(child_budget_limits))
        )
        self._dispatcher = dispatcher
        self._harness_factory = harness_factory
        self._session_factory = session_factory
        self._trace_recorder = trace_recorder
        self._termination = termination
        self._id_factory = id_factory

    async def invoke(self, draft: HandoffDraft) -> WorkerResult:
        """Execute a model-safe draft using only server-owned runtime authority."""

        try:
            worker = self._dispatcher.resolve(draft.target_worker)
            self._termination.before_handoff(draft)
        except LookupError:
            return _failure_result(draft, _worker_runtime_error())
        except ApplicationError as error:
            return _failure_result(draft, error)

        worker_run_id = self._id_factory()
        try:
            limits = self._limits_for_worker(draft.target_worker)
            budget = self._budget_tree.allocate_child(
                parent_run_id=self._parent_run.id,
                child_run_id=worker_run_id,
                task_id=draft.task_id,
                limits=limits,
            )
        except ApplicationError as error:
            return _failure_result(draft, error)
        except Exception:  # noqa: BLE001 - allocation IDs are a runtime trust boundary
            return _failure_result(draft, _worker_runtime_error())

        handoff = AgentHandoff(
            handoff_id=self._id_factory(),
            task_id=draft.task_id,
            goal=draft.goal,
            target_worker=draft.target_worker,
            public_context=draft.public_context,
            evidence_ids=list(draft.evidence_ids),
            artifact_ids=list(draft.artifact_ids),
            constraints=list(draft.constraints),
            expected_output=draft.expected_output,
            completion_criteria=list(draft.completion_criteria),
            allocated_budget_ref=budget.budget_ref,
        )
        worker_run = WorkerRunTrace(
            run_id=worker_run_id,
            parent_run_id=self._parent_run.id,
            root_run_id=self._budget_tree.root_run_id,
            trace_id=self._trusted_context.trace_id,
            budget_ref=budget.budget_ref,
            depth=budget.depth,
        )
        trace_started = False
        try:
            audit_run = self._trace_recorder.start(
                worker_run=worker_run,
                tenant_id=self._trusted_context.tenant_id,
                task_id=draft.task_id,
                worker_id=draft.target_worker,
            )
            trace_started = True
            result = await self._execute(
                worker,
                handoff,
                worker_run,
                budget,
                audit_run or self._parent_run,
            )
        except Exception:  # noqa: BLE001 - Trace/runtime internals must be sanitized
            result = _failure_result(draft, _worker_runtime_error(), budget.usage())
        finally:
            budget.close()

        if trace_started:
            self._trace_recorder.finish(worker_run_id, result)
        return result

    def _limits_for_worker(self, worker_id: str) -> WorkerBudgetLimits:
        configured = self._child_budget_limits
        if isinstance(configured, WorkerBudgetLimits):
            return configured
        try:
            return configured[worker_id]
        except KeyError:
            raise ValueError("Worker budget limits are not configured") from None

    async def _execute(
        self,
        worker: WorkerHandler,
        handoff: AgentHandoff,
        worker_run: WorkerRunTrace,
        budget: ChildExecutionBudget,
        audit_run: RunTrace,
    ) -> WorkerResult:
        session = self._session_factory()
        outer = session.begin()
        savepoint = session.begin_nested()
        try:
            harness = self._harness_factory.create(
                self._trusted_context,
                audit_run,
                budget,
            )
            execution = WorkerExecutionContext(
                trusted_context=self._trusted_context,
                worker_run=worker_run,
                budget=budget,
                harness=harness,
                session=session,
            )
            timeout_seconds = budget.remaining_ms() / 1000
            with bind_run_context(self._trusted_context):
                result = await asyncio.wait_for(
                    worker.run(handoff, execution),
                    timeout=timeout_seconds,
                )
            if (
                result.task_id != handoff.task_id
                or result.worker_id != handoff.target_worker
            ):
                raise ValueError("Worker result identity mismatch")
            budget.record_evidence(result.evidence_ids)
            measured = _replace_usage(result, budget.usage())
            self._termination.observe(measured)
            if measured.execution_status == "completed":
                savepoint.commit()
                outer.commit()
            else:
                savepoint.rollback()
                outer.rollback()
            return measured
        except TimeoutError:
            _rollback(savepoint, outer)
            return _failure_result(
                handoff,
                BudgetExceededError("worker_timeout", "Worker执行超过分配时间。"),
                budget.usage(),
            )
        except ApplicationError as error:
            _rollback(savepoint, outer)
            return _failure_result(handoff, error, budget.usage())
        except Exception:  # noqa: BLE001 - Worker code is an untrusted boundary
            _rollback(savepoint, outer)
            return _failure_result(handoff, _worker_runtime_error(), budget.usage())
        finally:
            session.close()


def _rollback(
    savepoint: SessionTransaction,
    outer: SessionTransaction,
) -> None:
    if savepoint.is_active:
        savepoint.rollback()
    if outer.is_active:
        outer.rollback()


def _replace_usage(result: WorkerResult, usage: ChildBudgetUsage) -> WorkerResult:
    return result.model_copy(update={"resource_usage": _resource_usage(usage)})


def _resource_usage(usage: ChildBudgetUsage | None = None) -> ResourceUsage:
    usage = usage or ChildBudgetUsage(0, 0, 0, 0, 0)
    return ResourceUsage(
        model_calls=usage.model_calls,
        tool_calls=usage.tool_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        duration_ms=usage.duration_ms,
    )


def _worker_runtime_error() -> ApplicationError:
    return ApplicationError(
        "INTERNAL_ERROR",
        "Worker执行失败。",
        retryable=False,
    )


def _failure_result(
    source: HandoffDraft | AgentHandoff,
    error: ApplicationError,
    usage: ChildBudgetUsage | None = None,
) -> WorkerResult:
    timed_out = isinstance(error, BudgetExceededError) and error.reason in {
        "total_timeout",
        "child_timeout",
        "worker_timeout",
        "tool_timeout",
    }
    return WorkerResult(
        task_id=source.task_id,
        worker_id=source.target_worker,
        execution_status="failed",
        business_outcome="timed_out" if timed_out else "system_error",
        business_result=None,
        public_summary=error.message,
        observations=[],
        evidence_ids=[],
        artifact_ids=[],
        unknowns=[],
        safe_errors=[
            SafeAgentError(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                field=error.field,
            )
        ],
        resource_usage=_resource_usage(usage),
    )
