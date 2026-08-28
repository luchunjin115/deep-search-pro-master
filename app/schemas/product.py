"""Product Tool input and output contracts for M1."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import (
    SKU,
    M1Schema,
    ProductQuery,
    ProductStatus,
    VerificationStatus,
)


class GetProductSpecInput(M1Schema):
    """The only model-controlled argument accepted by get_product_spec."""

    product_query: ProductQuery = Field(
        description=(
            "商品名称、受控别名或准确SKU；库存问题只有商品名称时，"
            "先用该字段解析租户内唯一SKU"
        )
    )


class ProductSpecItem(M1Schema):
    """One safe, traceable specification returned for a variant."""

    name: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    verification_status: VerificationStatus


class ProductSpecResult(M1Schema):
    """Resolved product and SKU data returned by get_product_spec."""

    product_id: UUID
    variant_id: UUID
    sku: SKU
    name_zh: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    status: ProductStatus
    specs: list[ProductSpecItem] = Field(min_length=1, max_length=20)
    synthetic_data: Literal[True] = True
