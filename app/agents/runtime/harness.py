"""Adapter that reuses the existing Harness with a trusted child budget."""

from __future__ import annotations

from app.runtime.budget import ChildExecutionBudget
from app.runtime.context import RunContext
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import RunTrace, TraceRecorder
from app.tools.registry import ToolRegistry


class WorkerHarnessAdapter:
    """Create a Harness without accepting identity or permissions from a model."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        permission_guard: PermissionGuard,
        trace_recorder: TraceRecorder,
    ) -> None:
        self._registry = registry
        self._permission_guard = permission_guard
        self._trace_recorder = trace_recorder

    def create(
        self,
        trusted_context: RunContext,
        audit_run: RunTrace,
        budget: ChildExecutionBudget,
    ) -> HarnessExecutor:
        if trusted_context.tenant_id != audit_run.tenant_id:
            raise ValueError("trusted context and audit run tenant mismatch")
        if trusted_context.trace_id != audit_run.trace_id:
            raise ValueError("trusted context and audit run trace mismatch")
        return HarnessExecutor(
            context=trusted_context,
            run=audit_run,
            budget=budget,
            registry=self._registry,
            permission_guard=self._permission_guard,
            trace_recorder=self._trace_recorder,
        )
