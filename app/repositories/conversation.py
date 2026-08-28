"""Fixed tenant/user-scoped reads and writes for M1 conversations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.runtime import Message, Thread
from app.repositories.common import apply_statement_timeout


class ConversationRepository:
    """Persist chat rows without accepting model-generated SQL or filters."""

    def __init__(self, session: Session, statement_timeout_ms: int) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def create_thread(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        title: str | None,
    ) -> Thread:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row = Thread(tenant_id=tenant_id, user_id=user_id, title=title)
        self._session.add(row)
        self._session.flush()
        return row

    def find_owned_active_thread(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
    ) -> Thread | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(Thread).where(
                Thread.id == thread_id,
                Thread.tenant_id == tenant_id,
                Thread.user_id == user_id,
                Thread.status == "active",
            )
        )

    def add_message(
        self,
        *,
        tenant_id: UUID,
        thread_id: UUID,
        role: str,
        content: str,
    ) -> Message:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row = Message(
            tenant_id=tenant_id,
            thread_id=thread_id,
            role=role,
            content_summary=content,
        )
        self._session.add(row)
        self._session.flush()
        return row
