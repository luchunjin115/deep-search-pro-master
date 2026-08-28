"""Deterministic, offline Tool proposals for the M1 demo workflow."""

from __future__ import annotations

import re

from pydantic import ValidationError

from app.core.errors import ProviderOutputError, UnsupportedProviderQuestionError
from app.llm.schemas import (
    GetProductSpecToolCall,
    SearchInventoryToolCall,
    ToolCallProposal,
    ToolDecisionRequest,
)
from app.schemas.inventory import SearchInventoryInput
from app.schemas.product import GetProductSpecInput

_WAREHOUSE_PATTERN = re.compile(r"(?<![A-Z0-9])(DE|FR)-[A-Z0-9]{3,8}(?![A-Z0-9])")
_SQL_MARKERS = (
    "drop table",
    "delete from",
    "insert into",
    "select *",
    "update ",
    "execute_sql",
)


class MockProvider:
    """Propose only controlled M1 calls without network access or model cost."""

    async def propose_tool_call(
        self,
        request: ToolDecisionRequest,
    ) -> ToolCallProposal:
        question = request.question.strip()
        normalized = question.casefold()
        upper_question = question.upper()

        if any(marker in normalized for marker in _SQL_MARKERS):
            raise UnsupportedProviderQuestionError
        if not any(
            marker in normalized
            for marker in ("库存", "可售", "存货", "inventory", "stock")
        ):
            raise UnsupportedProviderQuestionError

        warehouse_match = _WAREHOUSE_PATTERN.search(upper_question)
        warehouse_code = warehouse_match.group(0) if warehouse_match else None
        warehouse_market = warehouse_match.group(1) if warehouse_match else None
        has_de = bool(re.search(r"(?<![A-Z])DE(?![A-Z])", upper_question)) or any(
            marker in question for marker in ("德国", "德仓")
        )
        has_fr = bool(re.search(r"(?<![A-Z])FR(?![A-Z])", upper_question)) or any(
            marker in question for marker in ("法国", "法仓")
        )
        markets = {
            market for market, present in (("DE", has_de), ("FR", has_fr)) if present
        }
        if warehouse_market is not None:
            markets.add(warehouse_market)
        if len(markets) != 1:
            raise UnsupportedProviderQuestionError

        if "LR-TL-MUSH-OR01" in upper_question:
            product_query = "LR-TL-MUSH-OR01"
        elif "蘑菇灯" in question or "mushroom" in normalized:
            product_query = "蘑菇灯"
        else:
            raise UnsupportedProviderQuestionError

        market_code = markets.pop()

        try:
            if request.resolved_sku is not None:
                if "search_inventory" not in request.allowed_tool_names:
                    raise ProviderOutputError
                return SearchInventoryToolCall(
                    name="search_inventory",
                    arguments=SearchInventoryInput(
                        sku=request.resolved_sku,
                        market_code=market_code,  # type: ignore[arg-type]
                        warehouse_code=warehouse_code,  # type: ignore[arg-type]
                    ),
                )

            if product_query == "LR-TL-MUSH-OR01":
                if "search_inventory" not in request.allowed_tool_names:
                    raise ProviderOutputError
                return SearchInventoryToolCall(
                    name="search_inventory",
                    arguments=SearchInventoryInput(
                        sku=product_query,
                        market_code=market_code,  # type: ignore[arg-type]
                        warehouse_code=warehouse_code,  # type: ignore[arg-type]
                    ),
                )

            if "get_product_spec" not in request.allowed_tool_names:
                raise ProviderOutputError
            return GetProductSpecToolCall(
                name="get_product_spec",
                arguments=GetProductSpecInput(product_query=product_query),
            )
        except ValidationError:
            raise ProviderOutputError from None
