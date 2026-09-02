"""Durable, sanitized AgentRun and ToolCall audit recording for M1."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    ApplicationError,
    BudgetExceededError,
    ToolExecutionError,
    TracePersistenceError,
)
from app.models.runtime import AgentRun, ToolCall
from app.runtime.context import RunContext

RunRoute = Literal[
    "inventory_query",
    "product_spec",
    "knowledge_query",
    "unsupported",
]
RunStatus = Literal["completed", "failed", "denied", "timed_out"]
ToolStatus = Literal["success", "error", "denied", "timeout"]
PermissionResult = Literal["allowed", "denied"]

_SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "connection",
    "database_url",
    "sql",
)


@dataclass(frozen=True, slots=True)
class RunTrace:
    """Stable identifiers and clock origin for one persisted AgentRun."""

    id: UUID
    tenant_id: UUID
    trace_id: UUID
    started_monotonic: float


@dataclass(frozen=True, slots=True)
class ToolCallTrace:
    """Stable identifiers and clock origin for one persisted ToolCall."""

    id: UUID
    tenant_id: UUID
    agent_run_id: UUID
    started_monotonic: float


class TraceRecorder:
    """Persist audit state in short transactions independent of business rollback."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._monotonic = monotonic
        self._now = now or (lambda: datetime.now(UTC))

    def start_run(self, context: RunContext, route: RunRoute) -> RunTrace:
        """Create and commit one running AgentRun before downstream work."""

        run_id = uuid4()
        started_at = self._now()
        try:
            with self._session_factory.begin() as session:
                session.add(
                    AgentRun(
                        id=run_id,
                        tenant_id=context.tenant_id,
                        thread_id=context.thread_id,
                        user_id=context.user_id,
                        trace_id=context.trace_id,
                        route=route,
                        status="running",
                        model_call_count=0,
                        tool_call_count=0,
                        started_at=started_at,
                    )
                )
        except SQLAlchemyError:
            raise TracePersistenceError from None
        return RunTrace(
            id=run_id,
            tenant_id=context.tenant_id,
            trace_id=context.trace_id,
            started_monotonic=self._monotonic(),
        )

    @contextmanager
    def run_scope(
        self,
        context: RunContext,
        route: RunRoute,
    ) -> Generator[RunTrace, None, None]:
        """Finish every started AgentRun as completed, denied, timed out, or failed."""

        run = self.start_run(context, route)
        try:
            yield run
        except ApplicationError as error:
            self.finish_run(run, _run_status_for_error(error), error)
            raise
        except Exception:
            safe_error = ToolExecutionError()
            self.finish_run(run, "failed", safe_error)
            raise
        else:
            self.finish_run(run, "completed")

    def increment_model_call(self, run: RunTrace) -> None:
        """Increment only after ExecutionBudget reserves a model call."""

        try:
            with self._session_factory.begin() as session:
                row = _load_run(session, run)
                row.model_call_count += 1
        except SQLAlchemyError:
            raise TracePersistenceError from None

    def start_tool_call(
        self,
        run: RunTrace,
        *,
        tool_name: str,
        tool_version: str,
        arguments_summary: Mapping[str, object],
    ) -> ToolCallTrace:
        """Commit an allowed running ToolCall before invoking business code."""

        return self._create_tool_call(
            run,
            tool_name=tool_name,
            tool_version=tool_version,
            arguments_summary=arguments_summary,
            permission_result="allowed",
            status="running",
        )

    def record_denied_tool(
        self,
        run: RunTrace,
        *,
        tool_name: str,
        tool_version: str,
        arguments_summary: Mapping[str, object],
        error: ApplicationError,
        status: Literal["denied", "timeout"] = "denied",
    ) -> ToolCallTrace:
        """Commit a blocked attempt without calling downstream business code."""

        trace = self._create_tool_call(
            run,
            tool_name=tool_name,
            tool_version=tool_version,
            arguments_summary=arguments_summary,
            permission_result="denied",
            status=status,
            error=error,
        )
        return trace

    def finish_tool_call(
        self,
        trace: ToolCallTrace,
        status: ToolStatus,
        error: ApplicationError | None = None,
    ) -> None:
        """Commit the safe final status and duration of an allowed ToolCall."""

        finished_at = self._now()
        duration_ms = max(
            round((self._monotonic() - trace.started_monotonic) * 1000),
            0,
        )
        try:
            with self._session_factory.begin() as session:
                row = session.get(ToolCall, trace.id)
                if (
                    row is None
                    or row.tenant_id != trace.tenant_id
                    or row.agent_run_id != trace.agent_run_id
                ):
                    raise TracePersistenceError
                row.status = status
                row.duration_ms = duration_ms
                row.finished_at = finished_at
                _apply_safe_error(row, error)
        except SQLAlchemyError:
            raise TracePersistenceError from None

    def finish_run(
        self,
        run: RunTrace,
        status: RunStatus,
        error: ApplicationError | None = None,
    ) -> None:
        """Commit one terminal AgentRun status and frontend-safe error summary."""

        finished_at = self._now()
        duration_ms = max(
            round((self._monotonic() - run.started_monotonic) * 1000),
            0,
        )
        try:
            with self._session_factory.begin() as session:
                row = _load_run(session, run)
                row.status = status
                row.duration_ms = duration_ms
                row.finished_at = finished_at
                row.error_code = error.code if error is not None else None
                row.error_message = _safe_message(error)
        except SQLAlchemyError:
            raise TracePersistenceError from None

    def _create_tool_call(
        self,
        run: RunTrace,
        *,
        tool_name: str,
        tool_version: str,
        arguments_summary: Mapping[str, object],
        permission_result: PermissionResult,
        status: Literal["running", "denied", "timeout"],
        error: ApplicationError | None = None,
    ) -> ToolCallTrace:
        tool_call_id = uuid4()
        started_at = self._now()
        started_monotonic = self._monotonic()
        safe_arguments = summarize_arguments(arguments_summary)
        try:
            with self._session_factory.begin() as session:
                run_row = _load_run(session, run)
                run_row.tool_call_count += 1
                session.add(
                    ToolCall(
                        id=tool_call_id,
                        tenant_id=run.tenant_id,
                        agent_run_id=run.id,
                        sequence_no=run_row.tool_call_count,
                        tool_name=_bounded_text(tool_name, 100),
                        tool_version=_bounded_text(tool_version, 32),
                        arguments_summary=safe_arguments,
                        permission_result=permission_result,
                        status=status,
                        duration_ms=0 if status != "running" else None,
                        error_code=error.code if error is not None else None,
                        error_message=_safe_message(error),
                        started_at=started_at,
                        finished_at=started_at if status != "running" else None,
                    )
                )
        except SQLAlchemyError:
            raise TracePersistenceError from None
        return ToolCallTrace(
            id=tool_call_id,
            tenant_id=run.tenant_id,
            agent_run_id=run.id,
            started_monotonic=started_monotonic,
        )


def summarize_arguments(arguments: Mapping[str, object]) -> dict[str, object]:
    """Create bounded JSON-safe arguments with field-name based secret redaction."""

    summarized: dict[str, object] = {}
    for index, key in enumerate(sorted(arguments)):
        if index >= 20:
            summarized["_truncated_fields"] = len(arguments) - 20
            break
        safe_key = _bounded_text(str(key), 100)
        if _is_sensitive_key(safe_key):
            summarized[safe_key] = "[REDACTED]"
        else:
            summarized[safe_key] = _summarize_value(arguments[key], depth=0)
    return summarized


def arguments_from_input(value: BaseModel | Mapping[str, object]) -> dict[str, object]:
    """Normalize strict Tool Schema objects or test mappings into safe summaries."""

    if isinstance(value, BaseModel):
        raw = value.model_dump(mode="json")
    else:
        raw = dict(value)
    return summarize_arguments(raw)


def _summarize_value(value: object, depth: int) -> object:
    if depth >= 2:
        return "[TRUNCATED]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _bounded_text(value, 200)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        nested: dict[str, object] = {}
        for index, key in enumerate(sorted(str(item) for item in value)):
            if index >= 10:
                nested["_truncated_fields"] = len(value) - 10
                break
            if _is_sensitive_key(key):
                nested[_bounded_text(key, 100)] = "[REDACTED]"
            else:
                nested[_bounded_text(key, 100)] = _summarize_value(
                    value.get(key),
                    depth + 1,
                )
        return nested
    if isinstance(value, list | tuple):
        items = [_summarize_value(item, depth + 1) for item in value[:10]]
        if len(value) > 10:
            items.append("[TRUNCATED]")
        return items
    return _bounded_text(type(value).__name__, 80)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _bounded_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _load_run(session: Session, run: RunTrace) -> AgentRun:
    row = session.get(AgentRun, run.id)
    if row is None or row.tenant_id != run.tenant_id or row.trace_id != run.trace_id:
        raise TracePersistenceError
    return row


def _safe_message(error: ApplicationError | None) -> str | None:
    return _bounded_text(error.message, 300) if error is not None else None


def _apply_safe_error(row: ToolCall, error: ApplicationError | None) -> None:
    row.error_code = error.code if error is not None else None
    row.error_message = _safe_message(error)


def _run_status_for_error(error: ApplicationError) -> RunStatus:
    if error.code == "FORBIDDEN":
        return "denied"
    if isinstance(error, BudgetExceededError) and error.reason in (
        "total_timeout",
        "tool_timeout",
    ):
        return "timed_out"
    if error.code == "DATABASE_TIMEOUT":
        return "timed_out"
    return "failed"
