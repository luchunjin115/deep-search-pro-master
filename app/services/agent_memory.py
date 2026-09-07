"""Bounded, redacted short-term conversation memory for Agent checkpoints."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal, Protocol, cast
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ConversationPersistenceError
from app.schemas.agent import (
    MAX_MEMORY_TURNS,
    AgentConversationMemory,
    AgentMemoryTurn,
)
from app.schemas.auth import CurrentUser

_MAX_SOURCE_TURNS = MAX_MEMORY_TURNS + 16
_SECRET_ASSIGNMENT = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|storage[_-]?key)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_LOCAL_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s]+|\\\\[^\s]+|/(?:home|users|var|etc|tmp|workspace|mnt)/[^\s]+)",
    re.IGNORECASE,
)
_SQL_KEYWORD = re.compile(
    r"\b(?:select|insert|update|delete|drop|alter)\s+",
    re.IGNORECASE,
)
_TRACEBACK = re.compile(r"\btraceback\b", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class ConversationMemoryRecord(Protocol):
    id: UUID
    role: str
    content_summary: str


class ConversationMemoryStore(Protocol):
    def list_owned_messages(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        limit: int,
    ) -> Sequence[ConversationMemoryRecord]: ...


class AgentMemoryService:
    """Build memory only from an owned Thread's persisted messages and new input."""

    def __init__(self, repository: ConversationMemoryStore) -> None:
        self._repository = repository

    def build(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        current_turn_id: UUID,
        current_message: str,
    ) -> AgentConversationMemory:
        try:
            stored = list(
                self._repository.list_owned_messages(
                    tenant_id=user.tenant_id,
                    user_id=user.user_id,
                    thread_id=thread_id,
                    limit=_MAX_SOURCE_TURNS,
                )
            )
        except SQLAlchemyError:
            raise ConversationPersistenceError from None

        turns = [
            AgentMemoryTurn(
                turn_id=item.id,
                role=cast(Literal["user", "assistant"], item.role),
                content_summary=safe_memory_text(item.content_summary),
            )
            for item in stored
        ]
        if all(turn.turn_id != current_turn_id for turn in turns):
            turns.append(
                AgentMemoryTurn(
                    turn_id=current_turn_id,
                    role="user",
                    content_summary=safe_memory_text(current_message),
                )
            )
        older = turns[:-MAX_MEMORY_TURNS]
        recent = turns[-MAX_MEMORY_TURNS:]
        summary = _older_turn_summary(older) if older else None
        return AgentConversationMemory(
            safe_summary=summary,
            summarized_turn_count=len(older),
            recent_turns=recent,
        )


def safe_memory_text(value: str) -> str:
    """Return the exact public-safe representation stored in Agent memory."""

    text = _SECRET_ASSIGNMENT.sub("[redacted-secret]", value)
    text = _LOCAL_PATH.sub("[redacted-path]", text)
    text = _SQL_KEYWORD.sub("[redacted-sql] ", text)
    text = _TRACEBACK.sub("[redacted-trace]", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return (text or "[redacted-content]")[:1000]


def _older_turn_summary(turns: Sequence[AgentMemoryTurn]) -> str:
    parts: list[str] = []
    for turn in turns:
        role = "用户" if turn.role == "user" else "助手"
        parts.append(f"{role}：{turn.content_summary[:240]}")
    return " | ".join(parts)[:2000]
