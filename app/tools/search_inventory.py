"""Registered search_inventory Agent Tool for the M1 inventory slice."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from app.core.errors import ApplicationError
from app.runtime.executor import HarnessExecutor, ToolExecutionContext
from app.schemas.common import ToolEnvelope
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.services.evidence import EvidenceWriteContext
from app.services.inventory import InventoryService, InventoryServiceResult
from app.tools.contracts import ToolEnvelopeBuilder, validate_tool_binding


class SearchInventoryTool:
    """Read controlled stock and persist its database Evidence through Harness."""

    name: Literal["search_inventory"] = "search_inventory"

    def __init__(
        self,
        harness: HarnessExecutor,
        service: InventoryService,
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
            input_schema=SearchInventoryInput,
            output_schema=InventoryResult,
        )

    def invoke(
        self,
        request: SearchInventoryInput,
    ) -> ToolEnvelope[InventoryResult]:
        """Return inventory, source time, and the already-flushed Evidence ID."""

        response = ToolEnvelopeBuilder[InventoryResult](
            self._definition,
            self._harness.trace_id,
            self._monotonic,
        )
        try:
            execution = self._harness.execute_tool(
                self.name,
                request,
                target_tenant_id=self._harness.tenant_id,
                operation=lambda context: self._search(context, request),
            )
        except ApplicationError as error:
            return response.error(error)

        service_result = execution.data
        return response.success(
            service_result.inventory,
            evidence_ids=[service_result.evidence.id],
            source_time=service_result.inventory.snapshot_at,
        )

    def _search(
        self,
        context: ToolExecutionContext,
        request: SearchInventoryInput,
    ) -> InventoryServiceResult:
        result = self._service.search_inventory(
            EvidenceWriteContext(
                tenant_id=context.tenant_id,
                agent_run_id=context.agent_run_id,
                tool_call_id=context.tool_call_id,
            ),
            request,
        )
        if not isinstance(result, InventoryServiceResult):
            raise TypeError("Inventory Service returned an invalid Tool result")
        return result
