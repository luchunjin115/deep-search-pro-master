"""Authenticated upload, metadata, download, and soft-delete routes for M2."""

from __future__ import annotations

from functools import partial
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.api.dependencies import (
    AppSettings,
    CurrentUserDependency,
    FileServiceDependency,
    RequestCompensationsDependency,
)
from app.core.errors import FileUploadValidationError
from app.schemas.common import ApiErrorResponse
from app.schemas.files import (
    FileListResponse,
    FileResponse,
    FileStateUpdate,
    FileUploadResponse,
)

router = APIRouter(prefix="/files", tags=["files"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorResponse},
    404: {"model": ApiErrorResponse},
    409: {"model": ApiErrorResponse},
    422: {"model": ApiErrorResponse},
    500: {"model": ApiErrorResponse},
}


@router.post(
    "",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
)
async def upload_files(
    files: Annotated[list[UploadFile], File(description="PDF、DOCX、XLSX或CSV")],
    user: CurrentUserDependency,
    settings: AppSettings,
    compensations: RequestCompensationsDependency,
    service: FileServiceDependency,
) -> FileUploadResponse:
    """Atomically accept a bounded multipart batch without parsing its content."""

    if not files or len(files) > settings.upload_max_files_per_request:
        raise FileUploadValidationError

    uploaded = []
    try:
        for item in files:
            result = service.upload_file(
                user,
                original_name=item.filename or "",
                declared_content_type=item.content_type or "",
                stream=item.file,
                allowed_extensions=settings.upload_allowed_extensions,
                max_size_bytes=settings.upload_max_file_size_bytes,
            )
            compensations.add(partial(service.compensate_upload, result.storage_key))
            uploaded.append(result.response)
    finally:
        for item in files:
            await item.close()
    return FileUploadResponse(items=uploaded)


@router.get(
    "",
    response_model=FileListResponse,
    responses={401: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
)
async def list_files(
    user: CurrentUserDependency,
    service: FileServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> FileListResponse:
    """List only files visible to the current owner or document ACL."""

    return service.list_files(user, limit=limit)


@router.get(
    "/{file_id}/status",
    response_model=FileResponse,
    responses={
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
    },
)
async def get_file_status(
    file_id: UUID,
    user: CurrentUserDependency,
    service: FileServiceDependency,
) -> FileResponse:
    """Return authorized public metadata and lifecycle state by opaque ID."""

    return service.get_file(user, file_id)


@router.get(
    "/{file_id}",
    responses={
        200: {"content": {"application/octet-stream": {}}},
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        500: {"model": ApiErrorResponse},
    },
)
async def download_file(
    file_id: UUID,
    user: CurrentUserDependency,
    compensations: RequestCompensationsDependency,
    service: FileServiceDependency,
) -> StreamingResponse:
    """Stream one authorized object without exposing its internal Storage key."""

    download = service.open_download(user, file_id)
    compensations.add(download.stream.close)
    encoded_name = quote(download.original_name, safe="")
    fallback_name = (
        f"{file_id}{download.original_name[download.original_name.rfind('.') :]}"
    )
    return StreamingResponse(
        download.stream,
        media_type=download.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{fallback_name}"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
            "Content-Length": str(download.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(download.stream.close),
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        409: {"model": ApiErrorResponse},
    },
)
async def soft_delete_file(
    file_id: UUID,
    user: CurrentUserDependency,
    service: FileServiceDependency,
) -> Response:
    """Hide file metadata without physically removing the immutable object."""

    service.transition_file(user, file_id, FileStateUpdate(status="soft_deleted"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
