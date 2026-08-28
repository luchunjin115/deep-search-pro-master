"""Fixed tenant-scoped Evidence read used by the M1 HTTP boundary."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.runtime import Evidence
from app.repositories.common import apply_statement_timeout


class EvidenceRepository:
    """Load one Evidence row only inside a trusted tenant boundary."""

    def __init__(self, session: Session, statement_timeout_ms: int) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def find_by_id(self, *, tenant_id: UUID, evidence_id: UUID) -> Evidence | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(Evidence).where(
                Evidence.id == evidence_id,
                Evidence.tenant_id == tenant_id,
            )
        )
