"""Exact Worker lookup without legacy fallback routing."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from app.agents.runtime.contracts import WorkerHandler


class WorkerDispatcher:
    """Freeze a unique Worker registry and resolve only exact IDs."""

    def __init__(self, workers: Iterable[WorkerHandler]) -> None:
        registry: dict[str, WorkerHandler] = {}
        for worker in workers:
            if worker.worker_id in registry:
                raise ValueError(f"duplicate Worker ID: {worker.worker_id}")
            registry[worker.worker_id] = worker
        self._workers = MappingProxyType(registry)

    def resolve(self, worker_id: str) -> WorkerHandler:
        try:
            return self._workers[worker_id]
        except KeyError:
            raise LookupError("Worker is not registered") from None

    @property
    def worker_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._workers))
