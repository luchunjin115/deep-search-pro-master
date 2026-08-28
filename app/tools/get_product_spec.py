"""Registered get_product_spec Agent Tool for the M1 inventory slice."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from app.core.errors import ApplicationError
from app.runtime.executor import HarnessExecutor, ToolExecutionContext
from app.schemas.common import ToolEnvelope
from app.schemas.product import GetProductSpecInput, ProductSpecResult
from app.services.product import ProductSpecService
from app.tools.contracts import ToolEnvelopeBuilder, validate_tool_binding


class GetProductSpecTool:
    """Resolve one product through Harness and the deterministic product Service."""

    name: Literal["get_product_spec"] = "get_product_spec"

    def __init__(
        self,
        harness: HarnessExecutor,
        service: ProductSpecService,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._harness = harness
        self._service = service
        self._monotonic = monotonic
        self._definition = harness.get_tool_definition(self.name)
        validate_tool_binding(
            self._definition,
            name=self.name,
            input_schema=GetProductSpecInput,
            output_schema=ProductSpecResult,
        )

    def invoke(
        self,
        request: GetProductSpecInput,
    ) -> ToolEnvelope[ProductSpecResult]:
        """Return a standard envelope while Harness records every Tool attempt."""

        response = ToolEnvelopeBuilder[ProductSpecResult](
            self._definition,
            self._harness.trace_id,
            self._monotonic,
        )
        try:
            execution = self._harness.execute_tool(
                self.name,
                request,
                target_tenant_id=self._harness.tenant_id,
                operation=lambda context: self._get_spec(context, request),
            )
        except ApplicationError as error:
            return response.error(error)
        return response.success(execution.data)

    def _get_spec(
        self,
        context: ToolExecutionContext,
        request: GetProductSpecInput,
    ) -> ProductSpecResult:
        result = self._service.get_product_spec(context.tenant_id, request)
        if not isinstance(result, ProductSpecResult):
            raise TypeError("Product Service returned an invalid Tool result")
        return result
