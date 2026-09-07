"""Deterministic per-run model, Tool, repetition, and elapsed-time budgets."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.errors import BudgetExceededError, ToolTimeoutError


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Small M1 limits copied from validated application settings."""

    max_model_calls: int
    max_tool_calls: int
    max_repeat_tool_calls: int
    total_timeout_ms: int

    def __post_init__(self) -> None:
        if not (0 <= self.max_model_calls <= 10):
            raise ValueError("max_model_calls must be 0-10")
        if not (0 <= self.max_tool_calls <= 10):
            raise ValueError("max_tool_calls must be 0-10")
        if not (0 <= self.max_repeat_tool_calls <= 3):
            raise ValueError("max_repeat_tool_calls must be 0-3")
        if not (1 <= self.total_timeout_ms <= 60_000):
            raise ValueError("total_timeout_ms must be 1-60000")

    @classmethod
    def from_settings(cls, settings: Settings) -> BudgetLimits:
        """Copy centralized runtime configuration into one immutable run limit."""

        return cls(
            max_model_calls=settings.execution_max_model_calls,
            max_tool_calls=settings.execution_max_tool_calls,
            max_repeat_tool_calls=settings.execution_max_repeat_tool_calls,
            total_timeout_ms=settings.execution_total_timeout_ms,
        )


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Frontend-safe counters useful to Trace and deterministic tests."""

    model_calls: int
    tool_calls: int
    elapsed_ms: int
    remaining_ms: int


class ExecutionBudgetProtocol(Protocol):
    """The small budget surface consumed by the existing Harness executor."""

    def current_time(self) -> float: ...

    def reserve_model_call(self) -> BudgetSnapshot: ...

    def reserve_tool_call(
        self,
        tool_name: str,
        arguments_summary: Mapping[str, object],
    ) -> BudgetSnapshot: ...

    def ensure_total_time(self) -> None: ...

    def ensure_tool_duration(self, started_at: float, timeout_ms: int) -> None: ...

    def snapshot(self) -> BudgetSnapshot: ...


class ExecutionBudget:
    """Reserve bounded operations and reject loops before downstream execution."""

    def __init__(
        self,
        limits: BudgetLimits,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits = limits
        self._monotonic = monotonic
        self._started_at = monotonic()
        self._model_calls = 0
        self._tool_calls = 0
        self._tool_signatures: dict[str, int] = {}

    @property
    def limits(self) -> BudgetLimits:
        return self._limits

    def current_time(self) -> float:
        """Expose the injected monotonic clock to the synchronous executor."""

        return self._monotonic()

    def reserve_model_call(self) -> BudgetSnapshot:
        """Reserve one model call before invoking a Provider."""

        self.ensure_total_time()
        if self._model_calls >= self._limits.max_model_calls:
            raise BudgetExceededError(
                "model_call_limit",
                "模型调用次数已达到M1上限",
            )
        self._model_calls += 1
        return self.snapshot()

    def reserve_tool_call(
        self,
        tool_name: str,
        arguments_summary: Mapping[str, object],
    ) -> BudgetSnapshot:
        """Reserve one Tool attempt and reject repeated argument loops."""

        self.ensure_total_time()
        if self._tool_calls >= self._limits.max_tool_calls:
            raise BudgetExceededError(
                "tool_call_limit",
                "Tool调用次数已达到M1上限",
            )

        signature = _tool_signature(tool_name, arguments_summary)
        repeat_count = self._tool_signatures.get(signature, 0)
        if repeat_count >= self._limits.max_repeat_tool_calls:
            raise BudgetExceededError(
                "repeated_tool_call",
                "检测到重复Tool调用，已停止本次执行",
            )

        self._tool_calls += 1
        self._tool_signatures[signature] = repeat_count + 1
        return self.snapshot()

    def ensure_total_time(self) -> None:
        """Reject new work once the total run deadline has been reached."""

        if self.elapsed_ms() >= self._limits.total_timeout_ms:
            raise BudgetExceededError(
                "total_timeout",
                "本次执行已超过M1总时间预算",
            )

    def ensure_tool_duration(self, started_at: float, timeout_ms: int) -> None:
        """Reject a completed callback whose own registered duration was exceeded."""

        duration_ms = max(round((self._monotonic() - started_at) * 1000), 0)
        if duration_ms > timeout_ms:
            raise ToolTimeoutError
        self.ensure_total_time()

    def elapsed_ms(self) -> int:
        return max(round((self._monotonic() - self._started_at) * 1000), 0)

    def snapshot(self) -> BudgetSnapshot:
        elapsed_ms = self.elapsed_ms()
        return BudgetSnapshot(
            model_calls=self._model_calls,
            tool_calls=self._tool_calls,
            elapsed_ms=elapsed_ms,
            remaining_ms=max(self._limits.total_timeout_ms - elapsed_ms, 0),
        )


@dataclass(frozen=True, slots=True)
class AgentBudgetLimits:
    """Trusted root limits for one engineered Agent run."""

    max_model_calls: int
    max_tool_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_tasks: int
    max_evidence: int
    max_delegations: int
    max_depth: int
    total_timeout_ms: int

    def __post_init__(self) -> None:
        _ensure_between("max_model_calls", self.max_model_calls, 0, 10_000)
        _ensure_between("max_tool_calls", self.max_tool_calls, 0, 10_000)
        _ensure_between("max_input_tokens", self.max_input_tokens, 0, 10_000_000)
        _ensure_between("max_output_tokens", self.max_output_tokens, 0, 10_000_000)
        _ensure_between("max_tasks", self.max_tasks, 1, 24)
        _ensure_between("max_evidence", self.max_evidence, 0, 12)
        _ensure_between("max_delegations", self.max_delegations, 0, 24)
        _ensure_between("max_depth", self.max_depth, 0, 8)
        _ensure_between("total_timeout_ms", self.total_timeout_ms, 1, 86_400_000)


@dataclass(frozen=True, slots=True)
class WorkerBudgetLimits:
    """Program-assigned child limits; these never come from model output."""

    max_model_calls: int
    max_tool_calls: int
    max_repeat_tool_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_evidence: int
    timeout_ms: int

    def __post_init__(self) -> None:
        _ensure_between("max_model_calls", self.max_model_calls, 0, 10_000)
        _ensure_between("max_tool_calls", self.max_tool_calls, 0, 10_000)
        _ensure_between("max_repeat_tool_calls", self.max_repeat_tool_calls, 0, 3)
        _ensure_between("max_input_tokens", self.max_input_tokens, 0, 10_000_000)
        _ensure_between("max_output_tokens", self.max_output_tokens, 0, 10_000_000)
        _ensure_between("max_evidence", self.max_evidence, 0, 12)
        _ensure_between("timeout_ms", self.timeout_ms, 1, 86_400_000)


@dataclass(frozen=True, slots=True)
class AgentBudgetRestore:
    """Trusted usage reconstructed from one verified root checkpoint and audit tree."""

    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    evidence_ids: tuple[UUID, ...] = ()
    task_ids: tuple[str, ...] = ()
    delegations: int = 0
    tool_calls_by_signature: tuple[tuple[str, Mapping[str, object]], ...] = ()

    def __post_init__(self) -> None:
        _ensure_between("model_calls", self.model_calls, 0, 10_000)
        _ensure_between("tool_calls", self.tool_calls, 0, 10_000)
        _ensure_between("input_tokens", self.input_tokens, 0, 10_000_000)
        _ensure_between("output_tokens", self.output_tokens, 0, 10_000_000)
        _ensure_between("duration_ms", self.duration_ms, 0, 86_400_000)
        _ensure_between("delegations", self.delegations, 0, 24)
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("restored Evidence IDs must be unique")
        if len(self.task_ids) != len(set(self.task_ids)):
            raise ValueError("restored task IDs must be unique")
        if self.tool_calls < len(self.tool_calls_by_signature):
            raise ValueError("restored Tool audit cannot exceed the Tool count")


@dataclass(frozen=True, slots=True)
class AgentBudgetSnapshot:
    """Safe aggregate usage and topology counters for one budget tree."""

    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    evidence_count: int
    tasks: int
    delegations: int
    open_children: int
    elapsed_ms: int
    remaining_ms: int


@dataclass(frozen=True, slots=True)
class ChildBudgetUsage:
    """Measured child consumption used to replace untrusted Worker claims."""

    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    duration_ms: int


@dataclass(slots=True)
class _ChildState:
    parent_run_id: UUID
    child_run_id: UUID
    budget_ref: UUID
    task_id: str
    depth: int
    limits: WorkerBudgetLimits
    started_at: float
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    evidence_count: int = 0
    tool_signatures: dict[str, int] = field(default_factory=dict)
    closed: bool = False


class AgentBudgetTree:
    """Atomically reserve and account bounded parent/child Agent resources."""

    def __init__(
        self,
        *,
        root_run_id: UUID,
        limits: AgentBudgetLimits,
        monotonic: Callable[[], float] = time.monotonic,
        id_factory: Callable[[], UUID] = uuid4,
        restore: AgentBudgetRestore | None = None,
    ) -> None:
        restored = restore or AgentBudgetRestore()
        if (
            restored.model_calls > limits.max_model_calls
            or restored.tool_calls > limits.max_tool_calls
            or restored.input_tokens > limits.max_input_tokens
            or restored.output_tokens > limits.max_output_tokens
            or len(restored.evidence_ids) > limits.max_evidence
            or len(restored.task_ids) > limits.max_tasks
            or restored.delegations > limits.max_delegations
            or restored.duration_ms > limits.total_timeout_ms
        ):
            raise ValueError("restored usage exceeds the trusted root budget")
        self._root_run_id = root_run_id
        self._limits = limits
        self._monotonic = monotonic
        self._id_factory = id_factory
        self._started_at = monotonic()
        self._restored_duration_ms = restored.duration_ms
        self._lock = RLock()
        self._model_calls = restored.model_calls
        self._tool_calls = restored.tool_calls
        self._input_tokens = restored.input_tokens
        self._output_tokens = restored.output_tokens
        self._evidence_ids: set[UUID] = set(restored.evidence_ids)
        self._task_ids: set[str] = set(restored.task_ids)
        self._delegations = restored.delegations
        self._restored_tool_signatures = Counter(
            _tool_signature(tool_name, arguments)
            for tool_name, arguments in restored.tool_calls_by_signature
        )
        self._children: dict[UUID, _ChildState] = {}
        self._budget_refs: set[UUID] = set()

    @property
    def root_run_id(self) -> UUID:
        return self._root_run_id

    def allocate_child(
        self,
        *,
        parent_run_id: UUID,
        child_run_id: UUID,
        task_id: str,
        limits: WorkerBudgetLimits,
    ) -> ChildExecutionBudget:
        """Reserve all child capacity as one atomic operation."""

        with self._lock:
            self._ensure_root_time()
            parent_depth = self._parent_depth(parent_run_id)
            depth = parent_depth + 1
            if depth > self._limits.max_depth:
                raise _agent_budget_error(
                    "delegation_depth_limit",
                    "Agent委派深度已达到上限。",
                )
            if self._delegations >= self._limits.max_delegations:
                raise _agent_budget_error(
                    "delegation_limit",
                    "Agent委派次数已达到上限。",
                )
            is_new_task = task_id not in self._task_ids
            if is_new_task and len(self._task_ids) >= self._limits.max_tasks:
                raise _agent_budget_error("task_limit", "Agent任务数量已达到上限。")
            if child_run_id == self._root_run_id or child_run_id in self._children:
                raise ValueError("child run ID must be unique")
            if limits.timeout_ms > self._remaining_root_ms():
                raise _agent_budget_error(
                    "child_budget_overbooked",
                    "Worker预算超过父运行剩余容量。",
                )
            requested = (
                limits.max_model_calls,
                limits.max_tool_calls,
                limits.max_input_tokens,
                limits.max_output_tokens,
                limits.max_evidence,
            )
            available = self._available_capacity()
            if any(
                wanted > remaining for wanted, remaining in zip(requested, available)
            ):
                raise _agent_budget_error(
                    "child_budget_overbooked",
                    "Worker预算超过父运行剩余容量。",
                )

            budget_ref = self._id_factory()
            if budget_ref in self._budget_refs:
                raise ValueError("budget reference must be unique")
            state = _ChildState(
                parent_run_id=parent_run_id,
                child_run_id=child_run_id,
                budget_ref=budget_ref,
                task_id=task_id,
                depth=depth,
                limits=limits,
                started_at=self._monotonic(),
                tool_signatures=dict(self._restored_tool_signatures),
            )
            self._children[child_run_id] = state
            self._budget_refs.add(budget_ref)
            self._task_ids.add(task_id)
            self._delegations += 1
            return ChildExecutionBudget(self, child_run_id)

    def reserve_root_model_call(self) -> AgentBudgetSnapshot:
        """Reserve a Supervisor model call without stealing child capacity."""

        with self._lock:
            self._ensure_root_time()
            if self._available_capacity()[0] <= 0:
                raise _agent_budget_error(
                    "model_call_limit",
                    "Agent模型调用次数已达到上限。",
                )
            self._model_calls += 1
            return self.snapshot()

    def record_root_tokens(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> AgentBudgetSnapshot:
        with self._lock:
            self._ensure_root_time()
            _ensure_nonnegative_tokens(input_tokens, output_tokens)
            capacity = self._available_capacity()
            if input_tokens > capacity[2] or output_tokens > capacity[3]:
                raise _agent_budget_error("token_limit", "Agent Token预算已达到上限。")
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            return self.snapshot()

    def ensure_total_time(self) -> None:
        with self._lock:
            self._ensure_root_time()

    def snapshot(self) -> AgentBudgetSnapshot:
        with self._lock:
            elapsed_ms = self._root_elapsed_ms()
            return AgentBudgetSnapshot(
                model_calls=self._model_calls,
                tool_calls=self._tool_calls,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                evidence_count=len(self._evidence_ids),
                tasks=len(self._task_ids),
                delegations=self._delegations,
                open_children=sum(
                    not child.closed for child in self._children.values()
                ),
                elapsed_ms=elapsed_ms,
                remaining_ms=max(self._limits.total_timeout_ms - elapsed_ms, 0),
            )

    def _parent_depth(self, parent_run_id: UUID) -> int:
        if parent_run_id == self._root_run_id:
            return 0
        parent = self._children.get(parent_run_id)
        if parent is None or parent.closed:
            raise ValueError("parent run is unknown or closed")
        return parent.depth

    def _open_children(self) -> tuple[_ChildState, ...]:
        return tuple(child for child in self._children.values() if not child.closed)

    def _available_capacity(self) -> tuple[int, int, int, int, int]:
        children = self._open_children()
        reserved_model = sum(c.limits.max_model_calls - c.model_calls for c in children)
        reserved_tool = sum(c.limits.max_tool_calls - c.tool_calls for c in children)
        reserved_input = sum(
            c.limits.max_input_tokens - c.input_tokens for c in children
        )
        reserved_output = sum(
            c.limits.max_output_tokens - c.output_tokens for c in children
        )
        reserved_evidence = sum(
            c.limits.max_evidence - c.evidence_count for c in children
        )
        return (
            self._limits.max_model_calls - self._model_calls - reserved_model,
            self._limits.max_tool_calls - self._tool_calls - reserved_tool,
            self._limits.max_input_tokens - self._input_tokens - reserved_input,
            self._limits.max_output_tokens - self._output_tokens - reserved_output,
            self._limits.max_evidence - len(self._evidence_ids) - reserved_evidence,
        )

    def _child(self, child_run_id: UUID) -> _ChildState:
        child = self._children.get(child_run_id)
        if child is None:
            raise ValueError("child run is unknown")
        return child

    def _ensure_child_open_and_time(self, child: _ChildState) -> None:
        if child.closed:
            raise _agent_budget_error("child_budget_closed", "Worker预算已经关闭。")
        self._ensure_root_time()
        if self._elapsed_ms(child.started_at) >= child.limits.timeout_ms:
            raise _agent_budget_error("child_timeout", "Worker执行超过分配时间。")

    def _root_elapsed_ms(self) -> int:
        return self._restored_duration_ms + self._elapsed_ms(self._started_at)

    def _elapsed_ms(self, started_at: float) -> int:
        return max(round((self._monotonic() - started_at) * 1000), 0)

    def _remaining_root_ms(self) -> int:
        return max(self._limits.total_timeout_ms - self._root_elapsed_ms(), 0)

    def _ensure_root_time(self) -> None:
        if self._root_elapsed_ms() >= self._limits.total_timeout_ms:
            raise _agent_budget_error("total_timeout", "Agent总执行时间已达到上限。")


class ChildExecutionBudget:
    """Harness-compatible child view backed by an atomic root budget tree."""

    def __init__(self, tree: AgentBudgetTree, child_run_id: UUID) -> None:
        self._tree = tree
        self._child_run_id = child_run_id

    @property
    def budget_ref(self) -> UUID:
        with self._tree._lock:
            return self._tree._child(self._child_run_id).budget_ref

    @property
    def parent_run_id(self) -> UUID:
        with self._tree._lock:
            return self._tree._child(self._child_run_id).parent_run_id

    @property
    def depth(self) -> int:
        with self._tree._lock:
            return self._tree._child(self._child_run_id).depth

    def current_time(self) -> float:
        return self._tree._monotonic()

    def reserve_model_call(self) -> BudgetSnapshot:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)
            if child.model_calls >= child.limits.max_model_calls:
                raise _agent_budget_error(
                    "child_model_call_limit",
                    "Worker模型调用次数已达到上限。",
                )
            child.model_calls += 1
            self._tree._model_calls += 1
            return self.snapshot()

    def reserve_tool_call(
        self,
        tool_name: str,
        arguments_summary: Mapping[str, object],
    ) -> BudgetSnapshot:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)
            signature = _tool_signature(tool_name, arguments_summary)
            repeat_count = child.tool_signatures.get(signature, 0)
            if repeat_count >= child.limits.max_repeat_tool_calls:
                raise _agent_budget_error(
                    "repeated_tool_call",
                    "检测到重复Tool调用，已停止Worker执行。",
                )
            if child.tool_calls >= child.limits.max_tool_calls:
                raise _agent_budget_error(
                    "child_tool_call_limit",
                    "Worker Tool调用次数已达到上限。",
                )
            child.tool_calls += 1
            child.tool_signatures[signature] = repeat_count + 1
            self._tree._tool_calls += 1
            return self.snapshot()

    def record_tokens(self, *, input_tokens: int, output_tokens: int) -> BudgetSnapshot:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)
            _ensure_nonnegative_tokens(input_tokens, output_tokens)
            if (
                child.input_tokens + input_tokens > child.limits.max_input_tokens
                or child.output_tokens + output_tokens > child.limits.max_output_tokens
            ):
                raise _agent_budget_error(
                    "child_token_limit",
                    "Worker Token预算已达到上限。",
                )
            child.input_tokens += input_tokens
            child.output_tokens += output_tokens
            self._tree._input_tokens += input_tokens
            self._tree._output_tokens += output_tokens
            return self.snapshot()

    def record_evidence(self, evidence_ids: Sequence[UUID]) -> BudgetSnapshot:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)
            if len(evidence_ids) != len(set(evidence_ids)):
                raise ValueError("Evidence IDs must be unique")
            child_new = len(evidence_ids)
            root_new = len(set(evidence_ids) - self._tree._evidence_ids)
            if child.evidence_count + child_new > child.limits.max_evidence:
                raise _agent_budget_error(
                    "child_evidence_limit",
                    "Worker Evidence数量已达到上限。",
                )
            if (
                len(self._tree._evidence_ids) + root_new
                > self._tree._limits.max_evidence
            ):
                raise _agent_budget_error(
                    "evidence_limit",
                    "Agent Evidence数量已达到上限。",
                )
            child.evidence_count += child_new
            self._tree._evidence_ids.update(evidence_ids)
            return self.snapshot()

    def ensure_total_time(self) -> None:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)

    def ensure_tool_duration(self, started_at: float, timeout_ms: int) -> None:
        with self._tree._lock:
            duration_ms = self._tree._elapsed_ms(started_at)
            if duration_ms > timeout_ms:
                raise ToolTimeoutError
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)

    def remaining_ms(self) -> int:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            self._tree._ensure_child_open_and_time(child)
            child_remaining = child.limits.timeout_ms - self._tree._elapsed_ms(
                child.started_at
            )
            return max(min(child_remaining, self._tree._remaining_root_ms()), 0)

    def snapshot(self) -> BudgetSnapshot:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            elapsed_ms = self._tree._elapsed_ms(child.started_at)
            remaining_ms = max(
                min(
                    child.limits.timeout_ms - elapsed_ms,
                    self._tree._remaining_root_ms(),
                ),
                0,
            )
            return BudgetSnapshot(
                model_calls=child.model_calls,
                tool_calls=child.tool_calls,
                elapsed_ms=elapsed_ms,
                remaining_ms=remaining_ms,
            )

    def usage(self) -> ChildBudgetUsage:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            return ChildBudgetUsage(
                model_calls=child.model_calls,
                tool_calls=child.tool_calls,
                input_tokens=child.input_tokens,
                output_tokens=child.output_tokens,
                duration_ms=min(
                    self._tree._elapsed_ms(child.started_at),
                    86_400_000,
                ),
            )

    def close(self) -> None:
        with self._tree._lock:
            child = self._tree._child(self._child_run_id)
            child.closed = True


def _ensure_between(name: str, value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}-{maximum}")


def _ensure_nonnegative_tokens(input_tokens: int, output_tokens: int) -> None:
    _ensure_between("input_tokens", input_tokens, 0, 10_000_000)
    _ensure_between("output_tokens", output_tokens, 0, 10_000_000)


def _agent_budget_error(reason: str, message: str) -> BudgetExceededError:
    return BudgetExceededError(reason, message)


def _tool_signature(tool_name: str, arguments: Mapping[str, object]) -> str:
    canonical = json.dumps(
        {"tool": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
