"""Authenticated document creation, versioning, and indexing routes for M2."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import (
    CurrentUserDependency,
    DocumentIndexServiceDependency,
    DocumentServiceDependency,
)
from app.schemas.common import ApiErrorResponse
from app.schemas.knowledge import (
    DocumentCreateInput,
    DocumentDetailResponse,
    DocumentIndexResponse,
    DocumentVersionCreateInput,
    DocumentVersionResponse,
)

router = APIRouter(prefix="/documents", tags=["documents"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorResponse},
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
)
def create_document(
    request: DocumentCreateInput,
    user: CurrentUserDependency,
    service: DocumentServiceDependency,
) -> DocumentDetailResponse:
    """Create a logical document whose first version owns an uploaded file."""

    return service.create_document(user, request)


@router.post(
    "/{document_id}/versions",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
)
def add_document_version(
    document_id: UUID,
    request: DocumentVersionCreateInput,
    user: CurrentUserDependency,
    service: DocumentServiceDependency,
) -> DocumentVersionResponse:
    """Attach one new uploaded file as the next immutable document version."""

    return service.add_version(user, document_id, request)


@router.post(
    "/{document_id}/versions/{version_id}/index",
    response_model=DocumentIndexResponse,
    responses=_ERROR_RESPONSES,
)
def index_document_version(
    document_id: UUID,
    version_id: UUID,
    user: CurrentUserDependency,
    service: DocumentIndexServiceDependency,
) -> DocumentIndexResponse:
    """Synchronously make one version ready, then atomically activate it."""

    result = service.index_version(
        user,
        document_id=document_id,
        version_id=version_id,
    )
    return DocumentIndexResponse.model_validate(asdict(result))
