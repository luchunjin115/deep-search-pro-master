"""Registered read_uploaded_file Tool adapter for bounded parsed-file reads."""

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
from app.schemas.file_reading import ReadUploadedFileResult
from app.schemas.files import ReadUploadedFileInput
from app.services.file_reading import FileReadingService
from app.tools.contracts import ToolEnvelopeBuilder, validate_tool_binding


class ReadUploadedFileTool:
    """Run one identity-bound parsed-file read through the trusted Harness."""

    name: Literal["read_uploaded_file"] = "read_uploaded_file"

    def __init__(
        self,
        harness: HarnessExecutor,
        service: FileReadingService,
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
            input_schema=ReadUploadedFileInput,
            output_schema=ReadUploadedFileResult,
        )

    def invoke(
        self,
        request: ReadUploadedFileInput,
    ) -> ToolEnvelope[ReadUploadedFileResult]:
        """Return a bounded public file result while Harness controls execution."""

        response = ToolEnvelopeBuilder[ReadUploadedFileResult](
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

        return response.success(execution.data)

    def _read(
        self,
        context: ToolExecutionContext,
        request: ReadUploadedFileInput,
    ) -> ReadUploadedFileResult:
        self._validate_bound_identity(context)
        result = self._service.read_uploaded_file(self._current_user, request)
        if not isinstance(result, ReadUploadedFileResult) or result.file_id != (
            request.file_id
        ):
            raise TypeError("File Reading Service returned an invalid Tool result")
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
