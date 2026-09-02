"""Registered search_knowledge Tool adapter for the M2 knowledge slice."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from app.core.errors import (
    ApplicationError,
    MarketPermissionDeniedError,
    RolePermissionDeniedError,
    TenantPermissionDeniedError,
    UnsafeToolPermissionError,
)
from app.runtime.executor import HarnessExecutor, ToolExecutionContext
from app.schemas.auth import CurrentUser
from app.schemas.common import ToolEnvelope
from app.schemas.knowledge import SearchKnowledgeInput, SearchKnowledgeResult
from app.services.evidence import EvidenceWriteContext
from app.services.knowledge import KnowledgeSearchOutcome, KnowledgeSearchService
from app.tools.contracts import ToolEnvelopeBuilder, validate_tool_binding


class SearchKnowledgeTool:
    """Run one identity-bound knowledge search through the trusted Harness."""

    name: Literal["search_knowledge"] = "search_knowledge"

    def __init__(
        self,
        harness: HarnessExecutor,
        service: KnowledgeSearchService,
        current_user: CurrentUser,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._harness = harness
        self._service = service
        self._current_user = current_user
        self._monotonic = monotonic
        self._definition = harness.get_tool_definition(self.name)
        validate_tool_binding(
            self._definition,
            name=self.name,
            input_schema=SearchKnowledgeInput,
            output_schema=SearchKnowledgeResult,
        )

    def invoke(
        self,
        request: SearchKnowledgeInput,
    ) -> ToolEnvelope[SearchKnowledgeResult]:
        """Return a public Context envelope while Harness controls execution."""

        response = ToolEnvelopeBuilder[SearchKnowledgeResult](
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

        outcome = execution.data
        return response.success(
            outcome.result,
            evidence_ids=list(outcome.evidence_ids),
        )

    def _search(
        self,
        context: ToolExecutionContext,
        request: SearchKnowledgeInput,
    ) -> KnowledgeSearchOutcome:
        self._validate_bound_identity(context)
        outcome = self._service.search(
            self._current_user,
            request,
            runtime_context=EvidenceWriteContext(
                tenant_id=context.tenant_id,
                agent_run_id=context.agent_run_id,
                tool_call_id=context.tool_call_id,
            ),
        )
        if not isinstance(outcome, KnowledgeSearchOutcome) or not isinstance(
            outcome.result, SearchKnowledgeResult
        ):
            raise TypeError("Knowledge Service returned an invalid Tool result")
        if outcome.evidence_ids != outcome.result.evidence_ids:
            raise TypeError("Knowledge Service returned misaligned Evidence IDs")
        return outcome

    def _validate_bound_identity(self, context: ToolExecutionContext) -> None:
        user = self._current_user
        if user.user_id != context.user_id:
            raise UnsafeToolPermissionError
        if user.tenant_id != context.tenant_id:
            raise TenantPermissionDeniedError
        if tuple(user.roles) != context.roles:
            raise RolePermissionDeniedError
        if tuple(user.market_scopes) != context.market_scopes:
            raise MarketPermissionDeniedError
