from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest

from app.core.errors import BudgetExceededError
from app.runtime.budget import (
    AgentBudgetLimits,
    AgentBudgetRestore,
    AgentBudgetTree,
    WorkerBudgetLimits,
)

ROOT_RUN_ID = UUID("00000000-0000-0000-0000-000000000501")
CHILD_RUN_ID = UUID("00000000-0000-0000-0000-000000000502")
SECOND_CHILD_RUN_ID = UUID("00000000-0000-0000-0000-000000000503")
BUDGET_REF = UUID("00000000-0000-0000-0000-000000000504")
SECOND_BUDGET_REF = UUID("00000000-0000-0000-0000-000000000505")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000506")


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, milliseconds: int) -> None:
        self.value += milliseconds / 1000


def id_factory(*values: UUID) -> Iterator[UUID]:
    yield from values


def root_limits(**overrides: int) -> AgentBudgetLimits:
    values = {
        "max_model_calls": 6,
        "max_tool_calls": 6,
        "max_input_tokens": 2_000,
        "max_output_tokens": 1_000,
        "max_tasks": 3,
        "max_evidence": 12,
        "max_delegations": 3,
        "max_depth": 2,
        "total_timeout_ms": 5_000,
    }
    values.update(overrides)
    return AgentBudgetLimits(**values)


def child_limits(**overrides: int) -> WorkerBudgetLimits:
    values = {
        "max_model_calls": 2,
        "max_tool_calls": 2,
        "max_repeat_tool_calls": 1,
        "max_input_tokens": 500,
        "max_output_tokens": 250,
        "max_evidence": 4,
        "timeout_ms": 1_000,
    }
    values.update(overrides)
    return WorkerBudgetLimits(**values)


def test_child_usage_counts_toward_root_and_unused_reservation_is_returned() -> None:
    clock = ManualClock()
    refs = id_factory(BUDGET_REF, SECOND_BUDGET_REF)
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(max_model_calls=3),
        monotonic=clock,
        id_factory=lambda: next(refs),
    )

    first = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(max_model_calls=2),
    )
    assert first.budget_ref == BUDGET_REF
    assert first.parent_run_id == ROOT_RUN_ID
    assert first.depth == 1

    first.reserve_model_call()
    first.reserve_tool_call("search_inventory", {"market": "DE", "sku": "SKU-1"})
    first.record_tokens(input_tokens=120, output_tokens=30)
    first.record_evidence([EVIDENCE_ID])

    snapshot = tree.snapshot()
    assert snapshot.model_calls == 1
    assert snapshot.tool_calls == 1
    assert snapshot.input_tokens == 120
    assert snapshot.output_tokens == 30
    assert snapshot.evidence_count == 1
    assert snapshot.tasks == 1
    assert snapshot.delegations == 1
    assert snapshot.open_children == 1

    first.close()
    second = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=SECOND_CHILD_RUN_ID,
        task_id="policy",
        limits=child_limits(max_model_calls=2),
    )
    assert second.budget_ref == SECOND_BUDGET_REF
    assert tree.snapshot().open_children == 1


def test_child_allocations_are_atomic_and_cannot_overbook_root_capacity() -> None:
    refs = id_factory(BUDGET_REF, SECOND_BUDGET_REF)
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(max_model_calls=2),
        id_factory=lambda: next(refs),
    )
    first = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(max_model_calls=2),
    )

    before = tree.snapshot()
    with pytest.raises(BudgetExceededError) as captured:
        tree.allocate_child(
            parent_run_id=ROOT_RUN_ID,
            child_run_id=SECOND_CHILD_RUN_ID,
            task_id="policy",
            limits=child_limits(max_model_calls=1),
        )
    assert captured.value.reason == "child_budget_overbooked"
    assert tree.snapshot() == before

    first.reserve_model_call()
    first.close()
    second = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=SECOND_CHILD_RUN_ID,
        task_id="policy",
        limits=child_limits(max_model_calls=1),
    )
    assert second.budget_ref == SECOND_BUDGET_REF


def test_tree_rejects_unknown_parent_depth_delegation_and_task_limits() -> None:
    refs = id_factory(BUDGET_REF, SECOND_BUDGET_REF)
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(max_tasks=1, max_delegations=1, max_depth=1),
        id_factory=lambda: next(refs),
    )
    child = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(),
    )

    with pytest.raises(BudgetExceededError) as depth_error:
        tree.allocate_child(
            parent_run_id=CHILD_RUN_ID,
            child_run_id=SECOND_CHILD_RUN_ID,
            task_id="nested",
            limits=child_limits(),
        )
    assert depth_error.value.reason == "delegation_depth_limit"

    child.close()
    with pytest.raises(BudgetExceededError) as delegation_error:
        tree.allocate_child(
            parent_run_id=ROOT_RUN_ID,
            child_run_id=SECOND_CHILD_RUN_ID,
            task_id="policy",
            limits=child_limits(),
        )
    assert delegation_error.value.reason == "delegation_limit"

    other_tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(),
    )
    with pytest.raises(ValueError, match="parent"):
        other_tree.allocate_child(
            parent_run_id=UUID("00000000-0000-0000-0000-000000000599"),
            child_run_id=CHILD_RUN_ID,
            task_id="inventory",
            limits=child_limits(),
        )


def test_tree_rejects_a_new_task_after_the_distinct_task_limit() -> None:
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(max_tasks=1),
        id_factory=lambda: BUDGET_REF,
    )
    child = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(),
    )
    child.close()

    with pytest.raises(BudgetExceededError) as captured:
        tree.allocate_child(
            parent_run_id=ROOT_RUN_ID,
            child_run_id=SECOND_CHILD_RUN_ID,
            task_id="policy",
            limits=child_limits(),
        )
    assert captured.value.reason == "task_limit"
    assert tree.snapshot().tasks == 1
    assert tree.snapshot().delegations == 1


def test_concurrent_child_reservations_cannot_overbook_one_root_slot() -> None:
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(max_model_calls=1),
        id_factory=lambda: BUDGET_REF,
    )

    def allocate(child_run_id: UUID, task_id: str) -> str:
        try:
            tree.allocate_child(
                parent_run_id=ROOT_RUN_ID,
                child_run_id=child_run_id,
                task_id=task_id,
                limits=child_limits(max_model_calls=1),
            )
        except BudgetExceededError as error:
            return error.reason
        return "allocated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda item: allocate(*item),
                (
                    (CHILD_RUN_ID, "inventory"),
                    (SECOND_CHILD_RUN_ID, "policy"),
                ),
            )
        )

    assert sorted(results) == ["allocated", "child_budget_overbooked"]
    assert tree.snapshot().delegations == 1
    assert tree.snapshot().open_children == 1


def test_child_enforces_its_own_calls_repetition_tokens_and_shared_deadline() -> None:
    clock = ManualClock()
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(total_timeout_ms=1_000),
        monotonic=clock,
        id_factory=lambda: BUDGET_REF,
    )
    child = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(
            max_model_calls=1,
            max_tool_calls=2,
            max_input_tokens=100,
            timeout_ms=200,
        ),
    )

    child.reserve_model_call()
    with pytest.raises(BudgetExceededError) as model_error:
        child.reserve_model_call()
    assert model_error.value.reason == "child_model_call_limit"

    child.reserve_tool_call("search_inventory", {"sku": "SKU-1"})
    with pytest.raises(BudgetExceededError) as repeat_error:
        child.reserve_tool_call("search_inventory", {"sku": "SKU-1"})
    assert repeat_error.value.reason == "repeated_tool_call"
    assert child.snapshot().tool_calls == 1

    with pytest.raises(BudgetExceededError) as token_error:
        child.record_tokens(input_tokens=101, output_tokens=0)
    assert token_error.value.reason == "child_token_limit"

    clock.advance_ms(200)
    with pytest.raises(BudgetExceededError) as time_error:
        child.ensure_total_time()
    assert time_error.value.reason == "child_timeout"

    child.close()
    with pytest.raises(BudgetExceededError) as closed_error:
        child.reserve_tool_call("search_inventory", {"sku": "SKU-2"})
    assert closed_error.value.reason == "child_budget_closed"


def test_root_calls_cannot_consume_capacity_reserved_for_children() -> None:
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(max_model_calls=2),
        id_factory=lambda: BUDGET_REF,
    )
    tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(max_model_calls=1),
    )

    tree.reserve_root_model_call()
    with pytest.raises(BudgetExceededError) as captured:
        tree.reserve_root_model_call()
    assert captured.value.reason == "model_call_limit"
    assert tree.snapshot().model_calls == 1


def test_restored_budget_preserves_usage_deadline_and_tool_repeat_guard() -> None:
    clock = ManualClock()
    tree = AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=root_limits(total_timeout_ms=5_000),
        monotonic=clock,
        id_factory=lambda: BUDGET_REF,
        restore=AgentBudgetRestore(
            model_calls=1,
            tool_calls=1,
            input_tokens=100,
            output_tokens=20,
            duration_ms=2_000,
            evidence_ids=(EVIDENCE_ID,),
            task_ids=("inventory",),
            delegations=1,
            tool_calls_by_signature=(("search_inventory", {"sku": "SKU-1"}),),
        ),
    )

    assert tree.snapshot().model_calls == 1
    assert tree.snapshot().tool_calls == 1
    assert tree.snapshot().remaining_ms == 3_000
    child = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=child_limits(max_model_calls=1, max_tool_calls=1),
    )
    with pytest.raises(BudgetExceededError) as repeated:
        child.reserve_tool_call("search_inventory", {"sku": "SKU-1"})
    assert repeated.value.reason == "repeated_tool_call"


@pytest.mark.parametrize(
    "invalid",
    [
        {"max_tasks": 0},
        {"max_evidence": 13},
        {"max_depth": 9},
        {"total_timeout_ms": 0},
    ],
)
def test_agent_budget_limits_are_strictly_bounded(invalid: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        root_limits(**invalid)

    with pytest.raises(ValueError):
        child_limits(timeout_ms=0)
