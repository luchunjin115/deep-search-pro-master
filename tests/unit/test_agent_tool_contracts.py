from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.errors import MarketPermissionDeniedError
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.schemas.product import GetProductSpecInput, ProductSpecResult
from app.tools.contracts import (
    InvalidToolBindingError,
    ToolEnvelopeBuilder,
    validate_tool_binding,
)
from app.tools.registry import create_m1_tool_registry


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value


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


def test_exactly_two_registered_tool_contracts_match_runtime_schemas() -> None:
    registry = create_m1_tool_registry()

    assert registry.names == ("get_product_spec", "search_inventory")
    product = registry.get("get_product_spec")
    inventory = registry.get("search_inventory")
    validate_tool_binding(
        product,
        name="get_product_spec",
        input_schema=GetProductSpecInput,
        output_schema=ProductSpecResult,
    )
    validate_tool_binding(
        inventory,
        name="search_inventory",
        input_schema=SearchInventoryInput,
        output_schema=InventoryResult,
    )

    with pytest.raises(InvalidToolBindingError):
        validate_tool_binding(
            replace(product, input_schema=SearchInventoryInput),
            name="get_product_spec",
            input_schema=GetProductSpecInput,
            output_schema=ProductSpecResult,
        )


def test_registered_tool_descriptions_and_generated_parameters_are_model_ready() -> (
    None
):
    registry = create_m1_tool_registry()
    product = registry.get("get_product_spec")
    inventory = registry.get("search_inventory")

    assert all(
        phrase in product.description
        for phrase in ("时使用", "返回", "不查询库存", "不接受SQL", "匹配多个")
    )
    assert all(
        phrase in inventory.description
        for phrase in ("准确SKU", "时使用", "返回", "Evidence ID", "只读", "获权")
    )

    product_parameters = product.input_schema.model_json_schema()
    assert product_parameters["required"] == ["product_query"]
    assert product_parameters["additionalProperties"] is False
    assert "唯一SKU" in product_parameters["properties"]["product_query"]["description"]

    inventory_parameters = inventory.input_schema.model_json_schema()
    assert inventory_parameters["required"] == ["sku", "market_code"]
    assert inventory_parameters["additionalProperties"] is False
    assert inventory_parameters["properties"]["market_code"]["enum"] == [
        "DE",
        "FR",
    ]
    assert inventory_parameters["properties"]["sku"]["pattern"] == (
        "^[A-Z0-9][A-Z0-9-]{2,63}$"
    )
    assert "不接受商品名称" in inventory_parameters["properties"]["sku"]["description"]
    assert (
        "可省略" in inventory_parameters["properties"]["warehouse_code"]["description"]
    )


def test_tool_envelope_builder_records_version_duration_source_and_evidence() -> None:
    definition = create_m1_tool_registry().get("search_inventory")
    trace_id = uuid4()
    evidence_id = uuid4()
    clock = ManualClock()
    builder = ToolEnvelopeBuilder[InventoryResult](
        definition,
        trace_id,
        clock.monotonic,
    )
    clock.value += 0.025

    result = inventory_result()
    envelope = builder.success(
        result,
        evidence_ids=[evidence_id],
        source_time=result.snapshot_at,
    )

    assert envelope.status == "success"
    assert envelope.data == result
    assert envelope.evidence_ids == [evidence_id]
    assert envelope.meta.tool == "search_inventory"
    assert envelope.meta.version == "1.0.0"
    assert envelope.meta.duration_ms == 25
    assert envelope.meta.source_time == result.snapshot_at
    assert envelope.meta.trace_id == trace_id
    assert envelope.meta.synthetic_data is True


def test_tool_envelope_builder_exposes_only_safe_application_error() -> None:
    definition = create_m1_tool_registry().get("search_inventory")
    builder = ToolEnvelopeBuilder[InventoryResult](definition, uuid4())

    envelope = builder.error(MarketPermissionDeniedError())

    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert envelope.error is not None
    assert envelope.error.model_dump() == {
        "code": "FORBIDDEN",
        "message": "当前账号无权访问该市场数据",
        "retryable": False,
        "field": "market_code",
    }
