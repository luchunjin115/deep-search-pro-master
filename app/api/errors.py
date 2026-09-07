"""Unified safe HTTP error responses for M1."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import AgentTerminalError, ApplicationError
from app.schemas.common import ApiErrorResponse, ErrorDetail


def register_error_handlers(application: FastAPI) -> None:
    """Install stable JSON handlers without exposing stack traces or inputs."""

    @application.exception_handler(ApplicationError)
    async def application_error_handler(
        _request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        status_code = _status_for_error(error)
        headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
        trace_id = error.trace_id if isinstance(error, AgentTerminalError) else None
        body = ApiErrorResponse(error=error.to_detail(), trace_id=trace_id)
        return JSONResponse(
            status_code=status_code,
            content=body.model_dump(mode="json"),
            headers=headers,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        location = first.get("loc", ())
        field = ".".join(str(part) for part in location if part != "body") or None
        body = ApiErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="请求参数格式无效",
                retryable=False,
                field=field,
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @application.exception_handler(Exception)
    async def unexpected_error_handler(
        _request: Request,
        _error: Exception,
    ) -> JSONResponse:
        body = ApiErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="服务暂时无法完成请求",
                retryable=True,
            )
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


def _status_for_error(error: ApplicationError) -> int:
    if isinstance(error, AgentTerminalError) and error.terminal_status == "timed_out":
        return 504
    return {
        "UNAUTHENTICATED": 401,
        "FORBIDDEN": 403,
        "THREAD_NOT_FOUND": 404,
        "EVIDENCE_NOT_FOUND": 404,
        "FILE_NOT_FOUND": 404,
        "DOCUMENT_NOT_FOUND": 404,
        "PRODUCT_NOT_FOUND": 404,
        "INVENTORY_NOT_FOUND": 404,
        "AMBIGUOUS_PRODUCT": 409,
        "FILE_STATE_CONFLICT": 409,
        "DOCUMENT_STATE_CONFLICT": 409,
        "DOCUMENT_VERSION_CONFLICT": 409,
        "DOCUMENT_ACL_CONFLICT": 409,
        "AGENT_RUN_CONFLICT": 409,
        "VALIDATION_ERROR": 422,
        "DATABASE_UNAVAILABLE": 503,
        "DATABASE_TIMEOUT": 504,
        "BUDGET_EXCEEDED": 429,
        "PROVIDER_ERROR": 503 if error.retryable else 422,
        "INTERNAL_ERROR": 500,
    }[error.code]
