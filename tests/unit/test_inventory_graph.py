from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from app.agents.graphs.inventory_query import (
    InventoryGraphRuntime,
    build_inventory_query_graph,
)
from app.agents.state import InventoryGraphState
from app.core.errors import (
    DatabaseTimeoutError,
    ProductNotFoundError,
    UnsupportedProviderQuestionError,
)
from app.llm.schemas import (
    GetProductSpecToolCall,
    SearchInventoryToolCall,
    ToolCallProposal,
)
from app.schemas.common import ToolEnvelope, ToolMeta
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.schemas.product import (
    GetProductSpecInput,
    ProductSpecItem,
    ProductSpecResult,
)


def product_result() -> ProductSpecResult:
    return ProductSpecResult(
        product_id=uuid4(),
        variant_id=uuid4(),
        sku="LR-TL-MUSH-OR01",
        name_zh="橙色复古蘑菇台灯",
        name_en="Orange Retro Mushroom Table Lamp",
        status="active",
        specs=[
            ProductSpecItem(
                name="颜色",
                value="橙色",
                verification_status="demo_declared",
            )
        ],
        synthetic_data=True,
    )


def inventory_result() -> InventoryResult:
    return InventoryResult(
        sku="LR-TL-MUSH-OR01",
        product_name="橙色复古蘑菇台灯",
        market_code="DE",
        warehouse_code="DE-FRA",
        warehouse_name="德国法兰克福演示仓",
        on_hand=150,
        reserved=20,
        unsellable=5,
        available=125,
        inbound=80,
        safety_stock=60,
        snapshot_at=datetime(2026, 8, 28, 6, 0, tzinfo=UTC),
        synthetic_data=True,
    )


def meta(tool: str) -> ToolMeta:
    return ToolMeta(
        tool=tool,  # type: ignore[arg-type]
        version="1.0.0",
        duration_ms=1,
        trace_id=uuid4(),
        synthetic_data=True,
    )


@dataclass
class FakeRuntime:
    proposals: list[ToolCallProposal | Exception]
    product_envelope: ToolEnvelope[ProductSpecResult]
    inventory_envelope: ToolEnvelope[InventoryResult]
    product_calls: int = 0
    inventory_calls: int = 0

    async def propose(
        self,
        _question: str,
        _resolved_sku: str | None,
    ) -> ToolCallProposal:
        next_value = self.proposals.pop(0)
        if isinstance(next_value, Exception):
            raise next_value
        return next_value

    def get_product_spec(
        self,
        _arguments: GetProductSpecInput,
    ) -> ToolEnvelope[ProductSpecResult]:
        self.product_calls += 1
        return self.product_envelope

    def search_inventory(
        self,
        _arguments: SearchInventoryInput,
    ) -> ToolEnvelope[InventoryResult]:
        self.inventory_calls += 1
        return self.inventory_envelope


def runtime(
    proposals: list[ToolCallProposal | Exception],
) -> FakeRuntime:
    product = product_result()
    inventory = inventory_result()
    return FakeRuntime(
        proposals=proposals,
        product_envelope=ToolEnvelope[ProductSpecResult](
            status="success",
            data=product,
            meta=meta("get_product_spec"),
        ),
        inventory_envelope=ToolEnvelope[InventoryResult](
            status="success",
            data=inventory,
            evidence_ids=[uuid4()],
            meta=meta("search_inventory"),
        ),
    )


def initial_state(question: str) -> InventoryGraphState:
    return InventoryGraphState(
        question=question,
        tool_names=[],
        evidence_ids=[],
        node_history=[],
    )


@pytest.mark.asyncio
async def test_product_name_path_uses_two_bounded_tool_decisions() -> None:
    fake = runtime(
        [
            GetProductSpecToolCall(
                name="get_product_spec",
                arguments=GetProductSpecInput(product_query="蘑菇灯"),
            ),
            SearchInventoryToolCall(
                name="search_inventory",
                arguments=SearchInventoryInput(
                    sku="LR-TL-MUSH-OR01",
                    market_code="DE",
                ),
            ),
        ]
    )

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("德国仓蘑菇灯还有多少可售库存？")
        ),
    )

    assert result["inventory"].available == 125
    assert result["tool_names"] == ["get_product_spec", "search_inventory"]
    assert result["node_history"] == [
        "propose_next_tool",
        "validate_proposal",
        "execute_tool",
        "propose_next_tool",
        "validate_proposal",
        "execute_tool",
        "compose_answer",
    ]
    assert "可售库存为125件" in result["answer"]
    assert fake.product_calls == 1
    assert fake.inventory_calls == 1


@pytest.mark.asyncio
async def test_exact_sku_path_skips_product_tool() -> None:
    fake = runtime(
        [
            SearchInventoryToolCall(
                name="search_inventory",
                arguments=SearchInventoryInput(
                    sku="LR-TL-MUSH-OR01",
                    market_code="DE",
                    warehouse_code="DE-FRA",
                ),
            )
        ]
    )

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("查询LR-TL-MUSH-OR01在DE-FRA的库存")
        ),
    )

    assert result["tool_names"] == ["search_inventory"]
    assert fake.product_calls == 0
    assert fake.inventory_calls == 1


@pytest.mark.asyncio
async def test_graph_rejects_product_tool_after_sku_was_resolved() -> None:
    fake = runtime(
        [
            GetProductSpecToolCall(
                name="get_product_spec",
                arguments=GetProductSpecInput(product_query="蘑菇灯"),
            ),
            GetProductSpecToolCall(
                name="get_product_spec",
                arguments=GetProductSpecInput(product_query="蘑菇灯"),
            ),
        ]
    )

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("德国仓蘑菇灯库存")
        ),
    )

    assert result["error"].code == "PROVIDER_ERROR"
    assert result["tool_names"] == ["get_product_spec"]
    assert result["node_history"][-2:] == ["validate_proposal", "compose_error"]
    assert fake.product_calls == 1
    assert fake.inventory_calls == 0


@pytest.mark.asyncio
async def test_graph_rejects_direct_sku_invented_by_model() -> None:
    fake = runtime(
        [
            SearchInventoryToolCall(
                name="search_inventory",
                arguments=SearchInventoryInput(
                    sku="FORGED-SKU-01",
                    market_code="DE",
                ),
            )
        ]
    )

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("德国仓蘑菇灯库存")
        ),
    )

    assert result["error"].code == "PROVIDER_ERROR"
    assert result["tool_names"] == []
    assert fake.product_calls == 0
    assert fake.inventory_calls == 0


@pytest.mark.asyncio
async def test_provider_error_routes_to_safe_error_node_without_tool() -> None:
    fake = runtime([UnsupportedProviderQuestionError()])

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("帮我写一份广告")
        ),
    )

    assert result["error"].code == "PROVIDER_ERROR"
    assert result["tool_names"] == []
    assert result["node_history"] == ["propose_next_tool", "compose_error"]
    assert "DE/FR库存查询" in result["answer"]


@pytest.mark.asyncio
async def test_product_error_stops_before_second_model_or_inventory_call() -> None:
    fake = runtime(
        [
            GetProductSpecToolCall(
                name="get_product_spec",
                arguments=GetProductSpecInput(product_query="不存在的灯"),
            )
        ]
    )
    fake.product_envelope = ToolEnvelope[ProductSpecResult](
        status="error",
        error=ProductNotFoundError().to_detail(),
        meta=meta("get_product_spec"),
    )

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("查询不存在的灯在德国的库存")
        ),
    )

    assert result["error"].code == "PRODUCT_NOT_FOUND"
    assert result["terminal_status"] == "failed"
    assert result["tool_names"] == ["get_product_spec"]
    assert fake.product_calls == 1
    assert fake.inventory_calls == 0
    assert fake.proposals == []


@pytest.mark.asyncio
async def test_database_timeout_gets_timed_out_terminal_status() -> None:
    fake = runtime(
        [
            SearchInventoryToolCall(
                name="search_inventory",
                arguments=SearchInventoryInput(
                    sku="LR-TL-MUSH-OR01",
                    market_code="DE",
                ),
            )
        ]
    )
    fake.inventory_envelope = ToolEnvelope[InventoryResult](
        status="error",
        error=DatabaseTimeoutError().to_detail(),
        meta=meta("search_inventory"),
    )

    result = cast(
        InventoryGraphState,
        await build_inventory_query_graph(fake).ainvoke(
            initial_state("查询LR-TL-MUSH-OR01在德国的库存")
        ),
    )

    assert result["error"].code == "DATABASE_TIMEOUT"
    assert result["terminal_status"] == "timed_out"
    assert result["tool_names"] == ["search_inventory"]
    assert fake.inventory_calls == 1


def test_compiled_graph_contains_only_the_five_authorized_nodes() -> None:
    fake = runtime([UnsupportedProviderQuestionError()])
    graph = build_inventory_query_graph(cast(InventoryGraphRuntime, fake)).get_graph()

    assert set(graph.nodes) == {
        "__start__",
        "propose_next_tool",
        "validate_proposal",
        "execute_tool",
        "compose_answer",
        "compose_error",
        "__end__",
    }
    mermaid = graph.draw_mermaid()
    assert "propose_next_tool" in mermaid
    assert "validate_proposal" in mermaid
    assert "execute_tool" in mermaid
    assert "compose_answer" in mermaid
    assert "compose_error" in mermaid
