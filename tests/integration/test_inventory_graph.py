from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.graphs.inventory_query import InventoryQueryAgent
from app.agents.state import InventoryQueryInput
from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.llm.mock import MockProvider
from app.llm.provider import ModelProvider
from app.llm.schemas import ToolCallProposal, ToolDecisionRequest
from app.models.runtime import AgentRun, Evidence, Thread, ToolCall
from app.repositories.identity import IdentityRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.context import RunContext, build_run_context
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import TraceRecorder
from app.schemas.auth import LoginRequest
from app.services.auth import AuthService
from app.services.evidence import EvidenceService
from app.services.inventory import InventoryService
from app.services.product import ProductSpecService
from app.tools.registry import create_m1_tool_registry
from scripts.seed_m1 import seed_m1


@dataclass(frozen=True, slots=True)
class InventoryGraphFixture:
    settings: Settings
    runtime: DatabaseRuntime
    session_factory: sessionmaker[Session]
    business_session: Session
    context: RunContext
    recorder: TraceRecorder
    thread_id: UUID


@pytest.fixture
def inventory_graph_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[InventoryGraphFixture, None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    seed_m1(settings, manifest_path=tmp_path / "m1_manifest.json")
    runtime = create_database_runtime(settings)

    with runtime.session_factory() as auth_session:
        auth = AuthService(
            IdentityRepository(
                auth_session,
                settings.database_statement_timeout_ms,
            ),
            settings,
        )
        login = auth.login(
            LoginRequest(
                email="de.operator@demo.deepsearch.local",
                password=SecretStr("M1-demo-only-change-me"),
            )
        )
        user = auth.resolve_access_token(login.access_token)
        auth_session.rollback()

    thread_id = uuid4()
    with runtime.session_factory.begin() as setup_session:
        setup_session.add(
            Thread(
                id=thread_id,
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                title="M1-17 Inventory Graph Test",
            )
        )

    business_session = runtime.session_factory()
    try:
        yield InventoryGraphFixture(
            settings=settings,
            runtime=runtime,
            session_factory=runtime.session_factory,
            business_session=business_session,
            context=build_run_context(user, thread_id, trace_id=uuid4()),
            recorder=TraceRecorder(runtime.session_factory),
            thread_id=thread_id,
        )
    finally:
        business_session.rollback()
        business_session.close()
        with runtime.session_factory.begin() as cleanup_session:
            cleanup_session.execute(delete(Thread).where(Thread.id == thread_id))
        runtime.engine.dispose()


def agent(
    fixture: InventoryGraphFixture,
    *,
    max_model_calls: int = 2,
    max_tool_calls: int = 2,
    provider: ModelProvider | None = None,
) -> InventoryQueryAgent:
    registry = create_m1_tool_registry()
    return InventoryQueryAgent(
        context=fixture.context,
        provider=provider or MockProvider(),
        budget=ExecutionBudget(
            BudgetLimits(
                max_model_calls=max_model_calls,
                max_tool_calls=max_tool_calls,
                max_repeat_tool_calls=1,
                total_timeout_ms=8_000,
            )
        ),
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=fixture.recorder,
        product_service=ProductSpecService(
            ProductRepository(
                fixture.business_session,
                fixture.settings.database_statement_timeout_ms,
            )
        ),
        inventory_service=InventoryService(
            InventoryRepository(
                fixture.business_session,
                fixture.settings.database_statement_timeout_ms,
            ),
            EvidenceService(fixture.business_session),
        ),
        business_session=fixture.business_session,
    )


def load_run_and_calls(
    fixture: InventoryGraphFixture,
    run_id: UUID,
) -> tuple[AgentRun, list[ToolCall]]:
    with fixture.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        calls = list(
            session.scalars(
                select(ToolCall)
                .where(ToolCall.agent_run_id == run_id)
                .order_by(ToolCall.sequence_no)
            )
        )
        session.expunge(run)
        for call in calls:
            session.expunge(call)
        return run, calls


@pytest.mark.asyncio
async def test_real_graph_returns_125_with_evidence_and_complete_trace(
    inventory_graph_fixture: InventoryGraphFixture,
) -> None:
    fixture = inventory_graph_fixture

    result = await agent(fixture).run(
        InventoryQueryInput(question="德国仓蘑菇灯还有多少可售库存？")
    )
    fixture.business_session.commit()

    assert result.status == "completed"
    assert result.inventory is not None
    assert result.inventory.available == 125
    assert result.inventory.warehouse_code == "DE-FRA"
    assert result.tool_names == ["get_product_spec", "search_inventory"]
    assert len(result.evidence_ids) == 1
    assert "可售库存为125件" in result.answer
    assert "合成演示数据" in result.answer
    assert result.node_history == [
        "propose_next_tool",
        "validate_proposal",
        "execute_tool",
        "propose_next_tool",
        "validate_proposal",
        "execute_tool",
        "compose_answer",
    ]

    run, calls = load_run_and_calls(fixture, result.agent_run_id)
    assert run.status == "completed"
    assert run.model_call_count == 2
    assert run.tool_call_count == 2
    assert [call.tool_name for call in calls] == [
        "get_product_spec",
        "search_inventory",
    ]
    assert all(call.status == "success" for call in calls)
    with fixture.session_factory() as session:
        evidence = session.get(Evidence, result.evidence_ids[0])
        assert evidence is not None
        assert evidence.agent_run_id == result.agent_run_id
        assert evidence.tool_call_id == calls[1].id
        assert evidence.structured_data["available"] == 125


@pytest.mark.asyncio
async def test_real_graph_exact_sku_uses_one_model_and_one_tool(
    inventory_graph_fixture: InventoryGraphFixture,
) -> None:
    fixture = inventory_graph_fixture

    result = await agent(fixture).run(
        InventoryQueryInput(question="查询LR-TL-MUSH-OR01在DE-FRA的库存")
    )
    fixture.business_session.commit()

    assert result.status == "completed"
    assert result.tool_names == ["search_inventory"]
    run, calls = load_run_and_calls(fixture, result.agent_run_id)
    assert run.model_call_count == 1
    assert run.tool_call_count == 1
    assert [call.tool_name for call in calls] == ["search_inventory"]


@pytest.mark.asyncio
async def test_real_graph_denies_fr_inventory_before_repository_result(
    inventory_graph_fixture: InventoryGraphFixture,
) -> None:
    fixture = inventory_graph_fixture

    result = await agent(fixture).run(
        InventoryQueryInput(question="法国仓蘑菇灯还有多少库存？")
    )

    assert result.status == "denied"
    assert result.error is not None
    assert result.error.code == "FORBIDDEN"
    assert result.error.field == "market_code"
    assert result.evidence_ids == []
    run, calls = load_run_and_calls(fixture, result.agent_run_id)
    assert run.status == "denied"
    assert run.model_call_count == 2
    assert run.tool_call_count == 2
    assert [
        (call.tool_name, call.permission_result, call.status) for call in calls
    ] == [
        ("get_product_spec", "allowed", "success"),
        ("search_inventory", "denied", "denied"),
    ]


@pytest.mark.asyncio
async def test_real_graph_unsupported_question_stops_without_tool(
    inventory_graph_fixture: InventoryGraphFixture,
) -> None:
    fixture = inventory_graph_fixture

    result = await agent(fixture).run(
        InventoryQueryInput(question="帮我写一份蘑菇灯广告")
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "PROVIDER_ERROR"
    assert result.tool_names == []
    assert "DE/FR库存查询" in result.answer
    run, calls = load_run_and_calls(fixture, result.agent_run_id)
    assert run.status == "failed"
    assert run.model_call_count == 1
    assert run.tool_call_count == 0
    assert calls == []


@pytest.mark.asyncio
async def test_real_graph_model_budget_stops_before_second_provider_call(
    inventory_graph_fixture: InventoryGraphFixture,
) -> None:
    fixture = inventory_graph_fixture

    result = await agent(fixture, max_model_calls=1).run(
        InventoryQueryInput(question="德国仓蘑菇灯还有多少库存？")
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "BUDGET_EXCEEDED"
    assert result.tool_names == ["get_product_spec"]
    run, calls = load_run_and_calls(fixture, result.agent_run_id)
    assert run.status == "failed"
    assert run.model_call_count == 1
    assert run.tool_call_count == 1
    assert [call.tool_name for call in calls] == ["get_product_spec"]


@pytest.mark.asyncio
async def test_real_graph_sanitizes_unexpected_provider_exception(
    inventory_graph_fixture: InventoryGraphFixture,
) -> None:
    class BrokenProvider:
        async def propose_tool_call(
            self,
            _request: ToolDecisionRequest,
        ) -> ToolCallProposal:
            raise RuntimeError("api_key=secret SQL=DROP TABLE inventory_snapshots")

    fixture = inventory_graph_fixture
    result = await agent(fixture, provider=BrokenProvider()).run(
        InventoryQueryInput(question="德国仓蘑菇灯还有多少库存？")
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INTERNAL_ERROR"
    assert result.answer == "Agent流程执行失败"
    serialized = result.model_dump_json()
    assert "secret" not in serialized
    assert "DROP TABLE" not in serialized
    run, calls = load_run_and_calls(fixture, result.agent_run_id)
    assert run.status == "failed"
    assert run.model_call_count == 1
    assert run.tool_call_count == 0
    assert calls == []
