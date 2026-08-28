"""Deterministic per-run model, Tool, repetition, and elapsed-time budgets."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

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


def _tool_signature(tool_name: str, arguments: Mapping[str, object]) -> str:
    canonical = json.dumps(
        {"tool": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
