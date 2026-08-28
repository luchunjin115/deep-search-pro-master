"""Authorized Evidence detail route for M1."""

from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import (
    CurrentUserDependency,
    EvidenceQueryServiceDependency,
)
from app.schemas.common import ApiErrorResponse
from app.schemas.evidence import EvidenceDetail

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get(
    "/{evidence_id}",
    response_model=EvidenceDetail,
    responses={
        401: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
    },
)
async def get_evidence(
    evidence_id: UUID,
    user: CurrentUserDependency,
    service: EvidenceQueryServiceDependency,
) -> EvidenceDetail:
    """Return one tenant- and market-authorized database Evidence record."""

    return service.get_detail(user, evidence_id)
