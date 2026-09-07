"""M2-21 G0-G7 traceability plus the real bounded-parallel Gateway proof."""

from __future__ import annotations

from importlib import import_module
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import select

from app.agents.definitions import create_m2_agent_definitions
from app.api.dependencies import get_engineered_agent_provider
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.models.runtime import AgentRun, ToolCall
from app.runtime.context import RunContext
from app.schemas.common import RoleName
from tests.fixtures.agent_acceptance import agent_acceptance_cases
from tests.fixtures.agent_gateway_provider import ConcurrentCrossWorkerGatewayProvider
from tests.integration.test_m1_api import (
    ApiFixture,
    bearer,
    create_thread,
    login,
)
from tests.integration.test_m1_api import (
    api_fixture as shared_api_fixture,  # noqa: F401 - imported pytest fixture
)

# Every frozen case points at executable tests, not a prose-only completion claim.
ACCEPTANCE_TEST_TARGETS: dict[str, tuple[tuple[str, str], ...]] = {
    "G0": (
        (
            "tests.unit.test_agent_gateway_migration",
            "test_public_chat_router_has_no_legacy_graph_or_direct_tool_wiring",
        ),
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_supports_l0_without_starting_a_worker",
        ),
    ),
    "G1": (
        (
            "tests.unit.test_agent_gateway_migration",
            "test_public_chat_router_has_no_legacy_graph_or_direct_tool_wiring",
        ),
        (
            "tests.integration.test_m1_api",
            "test_provider_timeout_maps_to_504_with_trace",
        ),
    ),
    "G2": (
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_exact_sku_keeps_m1_result_with_one_business_tool",
        ),
        (
            "tests.integration.test_business_data_worker",
            "test_supervisor_business_worker_real_postgres_l1_matrix",
        ),
    ),
    "G3": (
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_runs_one_knowledge_tool_without_business_fallback",
        ),
        (
            "tests.integration.test_knowledge_worker",
            "test_knowledge_worker_rechecks_acl_and_soft_delete_without_leaking_storage",
        ),
    ),
    "G4": (
        (
            "tests.integration.test_multi_agent_matrix",
            "test_g4_public_gateway_overlaps_two_workers_with_isolated_audit",
        ),
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_runs_two_workers_and_preserves_partial_success",
        ),
    ),
    "G5": (
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_resumes_clarification_with_bounded_memory_and_one_replan",
        ),
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_reauthorizes_retained_state_before_clarification_resume",
        ),
    ),
    "G6": (
        (
            "tests.unit.test_multi_agent_graph",
            "test_no_capability_path_returns_explicit_unsupported",
        ),
        (
            "tests.unit.test_worker_runtime",
            "test_worker_timeout_rolls_back_and_returns_timed_out",
        ),
        (
            "tests.unit.test_multi_agent_graph",
            "test_decision_step_limit_stops_before_another_model_call",
        ),
    ),
    "G7": (
        (
            "tests.unit.test_agent_answer_citations",
            "test_answer_citations_reject_forged_malformed_or_duplicate_labels",
        ),
        (
            "tests.integration.test_m1_api",
            "test_public_gateway_reauthorizes_again_after_tool_before_final_checkpoint",
        ),
    ),
}


def test_frozen_g0_g7_cases_all_map_to_live_executable_tests() -> None:
    cases = agent_acceptance_cases()

    assert [case["case_id"] for case in cases] == [f"G{index}" for index in range(8)]
    assert set(ACCEPTANCE_TEST_TARGETS) == {case["case_id"] for case in cases}
    for targets in ACCEPTANCE_TEST_TARGETS.values():
        assert targets
        for module_name, function_name in targets:
            function = getattr(import_module(module_name), function_name, None)
            assert callable(function), (
                f"missing acceptance target: {module_name}::{function_name}"
            )


@pytest.mark.parametrize("role", ("company_owner", "product_scout", "amazon_operator"))
def test_all_three_read_roles_receive_only_the_two_registered_workers(
    role: str,
) -> None:
    context = RunContext(
        user_id=UUID("41000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("41000000-0000-0000-0000-000000000002"),
        roles=(cast(RoleName, role),),
        market_scopes=("DE",),
        thread_id=UUID("41000000-0000-0000-0000-000000000003"),
        trace_id=UUID("41000000-0000-0000-0000-000000000004"),
    )
    resolver = CapabilityResolver(
        create_m2_capability_catalog(), create_m2_agent_definitions()
    )

    targets = resolver.resolve_delegation_targets(context, CapabilitySelection())

    assert [item.capability_id for item in targets.capabilities] == [
        "business_data",
        "knowledge",
    ]
    assert all(item.side_effect == "none" for item in targets.capabilities)
    for target in targets.capabilities:
        worker_capabilities = resolver.resolve_for_agent(
            context,
            target.capability_id,
            CapabilitySelection(),
        )
        assert worker_capabilities.capabilities
        assert all(
            item.side_effect in {"none", "read"}
            for item in worker_capabilities.capabilities
        )


def test_g4_public_gateway_overlaps_two_workers_with_isolated_audit(
    shared_api_fixture: ApiFixture,  # noqa: F811 - pytest injects imported fixture
) -> None:
    provider = ConcurrentCrossWorkerGatewayProvider(
        file_id=shared_api_fixture.knowledge_file_id
    )

    async def override_provider() -> object:
        return provider

    application = shared_api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    try:
        token = login(shared_api_fixture.client)
        thread_id = create_thread(
            shared_api_fixture.client, token, "gateway parallel G4"
        )
        response = shared_api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "分别查询LR-TL-MUSH-OR01库存并读取获权手册"},
        )
    finally:
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert provider.both_workers_entered.is_set()
    assert provider.entered_workers == {"business_data", "knowledge"}
    assert payload["execution"]["business_outcome"] == "answered"
    assert set(payload["execution"]["tool_names"]) == {
        "search_inventory",
        "read_uploaded_file",
    }

    with shared_api_fixture.runtime.session_factory() as session:
        runs = list(
            session.scalars(
                select(AgentRun)
                .where(AgentRun.thread_id == thread_id)
                .order_by(AgentRun.depth, AgentRun.started_at, AgentRun.id)
            )
        )
        tool_calls = list(
            session.scalars(
                select(ToolCall).where(
                    ToolCall.agent_run_id.in_([run.id for run in runs])
                )
            )
        )

    root = next(run for run in runs if run.run_kind == "supervisor")
    children = [run for run in runs if run.run_kind == "worker"]
    assert {run.agent_id for run in children} == {"business_data", "knowledge"}
    assert all(
        run.root_run_id == root.id and run.parent_run_id == root.id for run in children
    )
    assert len({run.budget_ref for run in children}) == 2
    assert {call.agent_run_id for call in tool_calls} == {run.id for run in children}
