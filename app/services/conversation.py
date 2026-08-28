"""Ownership and persistence rules for M1 threads and messages."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ConversationPersistenceError, ThreadNotFoundError
from app.models.runtime import Message, Thread
from app.schemas.auth import CurrentUser
from app.schemas.chat import ThreadResponse


class ConversationStore(Protocol):
    def create_thread(
        self, *, tenant_id: UUID, user_id: UUID, title: str | None
    ) -> Thread: ...

    def find_owned_active_thread(
        self, *, tenant_id: UUID, user_id: UUID, thread_id: UUID
    ) -> Thread | None: ...

    def add_message(
        self, *, tenant_id: UUID, thread_id: UUID, role: str, content: str
    ) -> Message: ...


class ConversationService:
    """Enforce user ownership before a thread reaches RunContext or the graph."""

    def __init__(self, repository: ConversationStore) -> None:
        self._repository = repository

    def create_thread(self, user: CurrentUser, title: str | None) -> ThreadResponse:
        try:
            row = self._repository.create_thread(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                title=title,
            )
            return ThreadResponse(
                thread_id=row.id,
                title=row.title,
                status=row.status,  # type: ignore[arg-type]
                created_at=row.created_at,
            )
        except SQLAlchemyError:
            raise ConversationPersistenceError from None

    def require_owned_active_thread(self, user: CurrentUser, thread_id: UUID) -> Thread:
        try:
            row = self._repository.find_owned_active_thread(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                thread_id=thread_id,
            )
        except SQLAlchemyError:
            raise ConversationPersistenceError from None
        if row is None:
            raise ThreadNotFoundError
        return row

    def add_message(
        self,
        user: CurrentUser,
        thread_id: UUID,
        *,
        role: str,
        content: str,
    ) -> Message:
        try:
            return self._repository.add_message(
                tenant_id=user.tenant_id,
                thread_id=thread_id,
                role=role,
                content=content,
            )
        except SQLAlchemyError:
            raise ConversationPersistenceError from None
