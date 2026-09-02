"""Registered get_evidence_detail Tool adapter for authorized Evidence reads."""

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
from app.schemas.evidence import GetEvidenceDetailInput, GetEvidenceDetailResult
from app.services.evidence import EvidenceQueryService
from app.tools.contracts import ToolEnvelopeBuilder, validate_tool_binding


class GetEvidenceDetailTool:
    """Run one identity-bound Evidence read through the trusted Harness."""

    name: Literal["get_evidence_detail"] = "get_evidence_detail"

    def __init__(
        self,
        harness: HarnessExecutor,
        service: EvidenceQueryService,
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
            input_schema=GetEvidenceDetailInput,
            output_schema=GetEvidenceDetailResult,
        )

    def invoke(
        self,
        request: GetEvidenceDetailInput,
    ) -> ToolEnvelope[GetEvidenceDetailResult]:
        """Return one verified Evidence while Harness controls execution."""

        response = ToolEnvelopeBuilder[GetEvidenceDetailResult](
            self._definition,
            self._harness.trace_id,
            self._monotonic,
        )
        try:
            execution = self._harness.execute_tool(
                self.name,
                request,
                target_tenant_id=self._harness.tenant_id,
                operation=lambda context: self._read(context, request),
            )
        except ApplicationError as error:
            return response.error(error)

        result = execution.data
        return response.success(result, evidence_ids=[result.evidence_id])

    def _read(
        self,
        context: ToolExecutionContext,
        request: GetEvidenceDetailInput,
    ) -> GetEvidenceDetailResult:
        self._validate_bound_identity(context)
        result = self._service.get_tool_detail(self._current_user, request)
        if not isinstance(result, GetEvidenceDetailResult) or result.evidence_id != (
            request.evidence_id
        ):
            raise TypeError("Evidence Query Service returned an invalid Tool result")
        return result

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
