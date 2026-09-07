"""Fixed tenant/user-scoped reads and writes for M1 conversations."""

from __future__ import annotations

from datetime import UTC, datetime
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

    def list_owned_messages(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        limit: int,
    ) -> list[Message]:
        """Return a small chronological tail only from the owned active Thread."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        rows = list(
            self._session.scalars(
                select(Message)
                .join(
                    Thread,
                    (Thread.tenant_id == Message.tenant_id)
                    & (Thread.id == Message.thread_id),
                )
                .where(
                    Message.tenant_id == tenant_id,
                    Message.thread_id == thread_id,
                    Thread.user_id == user_id,
                    Thread.status == "active",
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
        )
        rows.reverse()
        return rows

    def find_owned_message(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        message_id: UUID,
    ) -> Message | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(Message)
            .join(
                Thread,
                (Thread.tenant_id == Message.tenant_id)
                & (Thread.id == Message.thread_id),
            )
            .where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
                Message.thread_id == thread_id,
                Thread.user_id == user_id,
                Thread.status == "active",
            )
        )

    def add_message_once(
        self,
        *,
        message_id: UUID,
        tenant_id: UUID,
        thread_id: UUID,
        role: str,
        content: str,
    ) -> Message:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row = Message(
            id=message_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            role=role,
            content_summary=content,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        self._session.flush()
        return row
