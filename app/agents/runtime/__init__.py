"""Reusable M2 engineered Agent Worker Runtime surface."""

from app.agents.runtime.contracts import (
    WorkerExecutionContext,
    WorkerHandler,
    WorkerHarnessFactory,
    WorkerInvoker,
    WorkerRunTrace,
    WorkerTraceRecorder,
)
from app.agents.runtime.dispatcher import WorkerDispatcher
from app.agents.runtime.harness import WorkerHarnessAdapter
from app.agents.runtime.provider import BudgetedAgentProvider
from app.agents.runtime.termination import TerminationPolicy, WorkerTerminationManager
from app.agents.runtime.trace import InMemoryWorkerTraceRecorder, WorkerRunRecord
from app.agents.runtime.worker import WorkerRuntime

__all__ = [
    "BudgetedAgentProvider",
    "InMemoryWorkerTraceRecorder",
    "TerminationPolicy",
    "WorkerDispatcher",
    "WorkerExecutionContext",
    "WorkerHandler",
    "WorkerHarnessAdapter",
    "WorkerHarnessFactory",
    "WorkerInvoker",
    "WorkerRunRecord",
    "WorkerRunTrace",
    "WorkerRuntime",
    "WorkerTerminationManager",
    "WorkerTraceRecorder",
]
