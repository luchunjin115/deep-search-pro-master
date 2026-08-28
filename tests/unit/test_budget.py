from collections.abc import Mapping

import pytest

from app.core.config import Settings
from app.core.errors import BudgetExceededError, ToolTimeoutError
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.trace import summarize_arguments


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, milliseconds: int) -> None:
        self.value += milliseconds / 1000


def limits(**changes: int) -> BudgetLimits:
    values = {
        "max_model_calls": 1,
        "max_tool_calls": 2,
        "max_repeat_tool_calls": 1,
        "total_timeout_ms": 1_000,
    }
    values.update(changes)
    return BudgetLimits(**values)


def test_settings_build_expected_m1_budget_limits() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert BudgetLimits.from_settings(settings) == BudgetLimits(
        max_model_calls=2,
        max_tool_calls=2,
        max_repeat_tool_calls=1,
        total_timeout_ms=8_000,
    )


def test_model_and_tool_call_limits_stop_before_extra_work() -> None:
    clock = ManualClock()
    budget = ExecutionBudget(limits(), clock)

    assert budget.reserve_model_call().model_calls == 1
    with pytest.raises(BudgetExceededError) as model_error:
        budget.reserve_model_call()
    assert model_error.value.reason == "model_call_limit"

    assert budget.reserve_tool_call("first", {"value": 1}).tool_calls == 1
    assert budget.reserve_tool_call("second", {"value": 2}).tool_calls == 2
    with pytest.raises(BudgetExceededError) as tool_error:
        budget.reserve_tool_call("third", {"value": 3})
    assert tool_error.value.reason == "tool_call_limit"


def test_repeated_tool_signature_is_rejected_without_using_another_slot() -> None:
    budget = ExecutionBudget(limits())

    budget.reserve_tool_call("search_inventory", {"sku": "SKU-001", "market": "DE"})
    with pytest.raises(BudgetExceededError) as captured:
        budget.reserve_tool_call(
            "search_inventory",
            {"market": "DE", "sku": "SKU-001"},
        )

    assert captured.value.reason == "repeated_tool_call"
    assert budget.snapshot().tool_calls == 1


def test_total_and_individual_tool_time_are_checked_with_monotonic_clock() -> None:
    clock = ManualClock()
    budget = ExecutionBudget(limits(total_timeout_ms=100), clock)
    started_at = budget.current_time()
    clock.advance_ms(51)

    with pytest.raises(ToolTimeoutError):
        budget.ensure_tool_duration(started_at, timeout_ms=50)

    clock.advance_ms(49)
    with pytest.raises(BudgetExceededError) as captured:
        budget.ensure_total_time()
    assert captured.value.reason == "total_timeout"
    assert budget.snapshot().remaining_ms == 0


def test_budget_limit_contract_rejects_impossible_values() -> None:
    with pytest.raises(ValueError):
        limits(max_tool_calls=11)
    with pytest.raises(ValueError):
        limits(max_repeat_tool_calls=4)
    with pytest.raises(ValueError):
        limits(total_timeout_ms=0)


def test_trace_argument_summary_redacts_and_bounds_sensitive_data() -> None:
    raw: Mapping[str, object] = {
        "sku": "LR-TL-MUSH-OR01",
        "password": "must-not-leak",
        "access_token": "signed-secret-token",
        "nested": {
            "api_key": "must-not-leak-either",
            "note": "x" * 250,
        },
        "sql_query": "DROP TABLE users",
    }

    summary = summarize_arguments(raw)
    serialized = str(summary)

    assert summary["password"] == "[REDACTED]"
    assert summary["access_token"] == "[REDACTED]"
    assert summary["sql_query"] == "[REDACTED]"
    assert summary["nested"] == {
        "api_key": "[REDACTED]",
        "note": "x" * 197 + "...",
    }
    assert "must-not-leak" not in serialized
    assert "DROP TABLE" not in serialized
