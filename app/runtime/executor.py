"""Synchronous M1 Harness shell around permission, budget, Trace, and callbacks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel

from app.core.errors import (
    ApplicationError,
    BudgetExceededError,
    ToolExecutionError,
    ToolNotAllowedError,
    ToolTimeoutError,
)
from app.runtime.budget import ExecutionBudget
from app.runtime.context import RunContext
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import (
    RunTrace,
    TraceRecorder,
    arguments_from_input,
)
from app.schemas.common import MarketCode
from app.tools.registry import ToolDefinition, ToolNotRegisteredError, ToolRegistry

ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """Committed audit identifiers available to an allowed business callback."""

    tenant_id: UUID
    agent_run_id: UUID
    tool_call_id: UUID
    trace_id: UUID


@dataclass(frozen=True, slots=True)
class ToolExecutionResult(Generic[ResultT]):
    """One successful callback result plus the ToolCall needed for Evidence."""

    data: ResultT
    context: ToolExecutionContext


class HarnessExecutor:
    """Ensure budget, permission, and Trace surround every M1 external call."""

    def __init__(
        self,
        *,
        context: RunContext,
        run: RunTrace,
        budget: ExecutionBudget,
        registry: ToolRegistry,
        permission_guard: PermissionGuard,
        trace_recorder: TraceRecorder,
    ) -> None:
        self._context = context
        self._run = run
        self._budget = budget
        self._registry = registry
        self._permission_guard = permission_guard
        self._trace_recorder = trace_recorder

    @property
    def tenant_id(self) -> UUID:
        """Return the trusted tenant bound to this run, never a model argument."""

        return self._context.tenant_id

    @property
    def trace_id(self) -> UUID:
        """Return the request trace identifier used by Tool response metadata."""

        return self._context.trace_id

    def get_tool_definition(self, tool_name: str) -> ToolDefinition:
        """Expose the same registered metadata used by permission enforcement."""

        return self._registry.get(tool_name)

    def reserve_model_call(self) -> None:
        """Reserve and trace one future Provider call before invoking it."""

        self._budget.reserve_model_call()
        self._trace_recorder.increment_model_call(self._run)

    def execute_tool(
        self,
        tool_name: str,
        arguments: BaseModel | Mapping[str, object],
        *,
        target_tenant_id: UUID,
        operation: Callable[[ToolExecutionContext], ResultT],
    ) -> ToolExecutionResult[ResultT]:
        """Run one callback only after budget and permission, with durable audit."""

        arguments_summary = arguments_from_input(arguments)
        market_code = _market_code_from_arguments(arguments_summary)
        try:
            definition = self._registry.get(tool_name)
        except ToolNotRegisteredError:
            error = ToolNotAllowedError()
            self._trace_recorder.record_denied_tool(
                self._run,
                tool_name=tool_name,
                tool_version="0.0.0",
                arguments_summary=arguments_summary,
                error=error,
            )
            raise error from None

        try:
            self._budget.reserve_tool_call(tool_name, arguments_summary)
        except BudgetExceededError as error:
            self._trace_recorder.record_denied_tool(
                self._run,
                tool_name=definition.name,
                tool_version=definition.version,
                arguments_summary=arguments_summary,
                error=error,
                status=("timeout" if error.reason == "total_timeout" else "denied"),
            )
            raise

        try:
            self._permission_guard.authorize(
                self._context,
                tool_name,
                target_tenant_id=target_tenant_id,
                market_code=market_code,
            )
        except ApplicationError as error:
            self._trace_recorder.record_denied_tool(
                self._run,
                tool_name=definition.name,
                tool_version=definition.version,
                arguments_summary=arguments_summary,
                error=error,
            )
            raise

        tool_trace = self._trace_recorder.start_tool_call(
            self._run,
            tool_name=definition.name,
            tool_version=definition.version,
            arguments_summary=arguments_summary,
        )
        execution_context = ToolExecutionContext(
            tenant_id=self._context.tenant_id,
            agent_run_id=self._run.id,
            tool_call_id=tool_trace.id,
            trace_id=self._context.trace_id,
        )
        operation_started_at = self._budget.current_time()
        try:
            result = operation(execution_context)
            self._budget.ensure_tool_duration(
                operation_started_at,
                definition.timeout_ms,
            )
        except ToolTimeoutError as error:
            self._trace_recorder.finish_tool_call(tool_trace, "timeout", error)
            raise
        except BudgetExceededError as error:
            self._trace_recorder.finish_tool_call(tool_trace, "timeout", error)
            raise
        except ApplicationError as error:
            if error.code == "DATABASE_TIMEOUT":
                self._trace_recorder.finish_tool_call(tool_trace, "timeout", error)
            else:
                self._trace_recorder.finish_tool_call(tool_trace, "error", error)
            raise
        except Exception:  # noqa: BLE001 - Tool trust boundary must sanitize failures
            safe_error = ToolExecutionError()
            self._trace_recorder.finish_tool_call(tool_trace, "error", safe_error)
            raise safe_error from None

        self._trace_recorder.finish_tool_call(tool_trace, "success")
        return ToolExecutionResult(data=result, context=execution_context)


def _market_code_from_arguments(
    arguments_summary: Mapping[str, object],
) -> MarketCode | None:
    value = arguments_summary.get("market_code")
    if value in ("DE", "FR"):
        return cast(MarketCode, value)
    return None
