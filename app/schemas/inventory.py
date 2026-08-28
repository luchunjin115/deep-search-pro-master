"""Inventory intent, Tool input, and result contracts for M1."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.common import (
    SKU,
    M1Schema,
    MarketCode,
    ProductQuery,
    WarehouseCode,
)


def _warehouse_matches_market(
    warehouse_code: str | None,
    market_code: str | None,
) -> bool:
    return warehouse_code is None or (
        market_code is not None and warehouse_code.startswith(f"{market_code}-")
    )


class InventoryIntent(M1Schema):
    """The only structured interpretation a model may return for inventory."""

    intent: Literal["inventory_query"] = "inventory_query"
    product_query: ProductQuery = Field(
        description="从用户问题提取的商品名称、受控别名或SKU"
    )
    market_code: MarketCode = Field(
        description="用户明确或可确定的目标Amazon市场；M1只允许DE或FR"
    )
    warehouse_code: WarehouseCode | None = Field(
        default=None,
        description="用户明确指定的仓库代码；没有指定时保持为空，不允许猜测",
    )

    @model_validator(mode="after")
    def validate_warehouse_market(self) -> InventoryIntent:
        if not _warehouse_matches_market(self.warehouse_code, self.market_code):
            raise ValueError("warehouse_code must belong to market_code")
        return self


class SearchInventoryInput(M1Schema):
    """Validated arguments accepted by search_inventory."""

    sku: SKU = Field(
        description="已经通过商品规格查询确认的准确SKU；不接受商品名称或自然语言"
    )
    market_code: MarketCode = Field(
        description="需要查询的Amazon市场；M1只允许DE或FR，并受用户市场权限限制"
    )
    warehouse_code: WarehouseCode | None = Field(
        default=None,
        description="具体仓库代码；可省略，但市场存在多个仓库时必须补充",
    )

    @model_validator(mode="after")
    def validate_warehouse_market(self) -> SearchInventoryInput:
        if not _warehouse_matches_market(self.warehouse_code, self.market_code):
            raise ValueError("warehouse_code must belong to market_code")
        return self


class InventoryResult(M1Schema):
    """Raw stock fields plus the checked sellable quantity returned to callers."""

    sku: SKU
    product_name: str = Field(min_length=1, max_length=200)
    market_code: MarketCode
    warehouse_code: WarehouseCode
    warehouse_name: str = Field(min_length=1, max_length=160)
    on_hand: int = Field(ge=0)
    reserved: int = Field(ge=0)
    unsellable: int = Field(ge=0)
    available: int = Field(ge=0)
    inbound: int = Field(ge=0)
    safety_stock: int = Field(ge=0)
    snapshot_at: AwareDatetime
    synthetic_data: Literal[True] = True

    @model_validator(mode="after")
    def validate_inventory_consistency(self) -> InventoryResult:
        if not _warehouse_matches_market(self.warehouse_code, self.market_code):
            raise ValueError("warehouse_code must belong to market_code")
        expected_available = self.on_hand - self.reserved - self.unsellable
        if expected_available < 0:
            raise ValueError("reserved plus unsellable cannot exceed on_hand")
        if self.available != expected_available:
            raise ValueError(
                "available must equal on_hand minus reserved minus unsellable"
            )
        return self
