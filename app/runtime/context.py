"""Strong, immutable, task-isolated execution identity for M1."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.schemas.auth import CurrentUser
from app.schemas.common import MarketCode, RoleName


@dataclass(frozen=True, slots=True)
class RunContext:
    """Trusted identity, chat session, data scope, and trace for one execution."""

    user_id: UUID
    tenant_id: UUID
    roles: tuple[RoleName, ...]
    market_scopes: tuple[MarketCode, ...]
    thread_id: UUID
    trace_id: UUID


class MissingRunContextError(RuntimeError):
    """No RunContext has been bound to the current request/task."""


_current_run_context: ContextVar[RunContext | None] = ContextVar(
    "m1_run_context",
    default=None,
)


def build_run_context(
    user: CurrentUser,
    thread_id: UUID,
    *,
    trace_id: UUID | None = None,
) -> RunContext:
    """Copy a database-refreshed CurrentUser into an immutable execution context."""

    return RunContext(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        roles=tuple(user.roles),
        market_scopes=tuple(user.market_scopes),
        thread_id=thread_id,
        trace_id=trace_id or uuid4(),
    )


@contextmanager
def bind_run_context(context: RunContext) -> Generator[RunContext, None, None]:
    """Bind one context and reliably restore the previous task-local value."""

    token = _current_run_context.set(context)
    try:
        yield context
    finally:
        _current_run_context.reset(token)


def get_current_run_context() -> RunContext:
    """Return only the context bound to the current asynchronous task."""

    context = _current_run_context.get()
    if context is None:
        raise MissingRunContextError("No RunContext is bound to this execution")
    return context
