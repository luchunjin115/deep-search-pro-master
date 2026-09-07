from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agents.engineered_state import EngineeredAgentState
from app.agents.gateway import _public_context
from app.schemas.agent import AgentConversationMemory, AgentMemoryTurn, ResourceUsage
from app.schemas.auth import CurrentUser
from app.services.agent_memory import AgentMemoryService


@dataclass(frozen=True)
class StoredTurn:
    id: UUID
    role: str
    content_summary: str


class MemoryStore:
    def __init__(self, turns: list[StoredTurn]) -> None:
        self.turns = turns

    def list_owned_messages(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        limit: int,
    ) -> list[StoredTurn]:
        assert tenant_id == TENANT_ID
        assert user_id == USER_ID
        assert thread_id == THREAD_ID
        return self.turns[-limit:]


TENANT_ID = UUID("00000000-0000-0000-0000-000000001101")
USER_ID = UUID("00000000-0000-0000-0000-000000001102")
THREAD_ID = UUID("00000000-0000-0000-0000-000000001103")
CURRENT_TURN_ID = UUID("00000000-0000-0000-0000-000000001104")
USER = CurrentUser(
    user_id=USER_ID,
    tenant_id=TENANT_ID,
    email="operator@example.com",
    display_name="Operator",
    roles=["amazon_operator"],
    market_scopes=["DE"],
)


def test_memory_keeps_only_recent_turns_and_a_bounded_safe_summary() -> None:
    turns = [
        StoredTurn(
            id=UUID(int=1_200 + index),
            role="user" if index % 2 == 0 else "assistant",
            content_summary=f"第{index}轮内容 " + "x" * 1_200,
        )
        for index in range(12)
    ]
    service = AgentMemoryService(MemoryStore(turns))

    memory = service.build(
        USER,
        thread_id=THREAD_ID,
        current_turn_id=CURRENT_TURN_ID,
        current_message="继续查询德国库存",
    )

    assert len(memory.recent_turns) == 8
    assert memory.recent_turns[-1].turn_id == CURRENT_TURN_ID
    assert memory.recent_turns[-1].content_summary == "继续查询德国库存"
    assert all(len(turn.content_summary) <= 1_000 for turn in memory.recent_turns)
    assert memory.safe_summary is not None
    assert len(memory.safe_summary) <= 2_000
    assert memory.summarized_turn_count == 5


def test_memory_redacts_paths_sql_and_secret_assignments_before_checkpointing() -> None:
    service = AgentMemoryService(
        MemoryStore(
            [
                StoredTurn(
                    id=UUID(int=1_300),
                    role="user",
                    content_summary=(
                        r"api_key=top-secret C:\\private\\file.txt "
                        "SELECT password FROM users"
                    ),
                )
            ]
        )
    )

    memory = service.build(
        USER,
        thread_id=THREAD_ID,
        current_turn_id=CURRENT_TURN_ID,
        current_message="password=hunter2 然后继续",
    )
    serialized = memory.model_dump_json()

    assert "top-secret" not in serialized
    assert "hunter2" not in serialized
    assert "private" not in serialized
    assert "SELECT" not in serialized
    assert "[redacted" in serialized


def test_memory_contract_rejects_duplicate_turns_and_unknown_fields() -> None:
    turn = AgentMemoryTurn(
        turn_id=CURRENT_TURN_ID,
        role="user",
        content_summary="德国",
    )
    with pytest.raises(ValidationError, match="unique"):
        AgentConversationMemory(
            recent_turns=[turn, turn],
            summarized_turn_count=0,
        )


def test_resume_state_rejects_unaccepted_active_request_and_unbounded_counts() -> None:
    values = {
        "run_id": UUID(int=1_401),
        "goal": "继续任务",
        "execution_status": "running",
        "resource_usage": ResourceUsage(
            model_calls=0,
            tool_calls=0,
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
        ),
    }
    with pytest.raises(ValidationError, match="active request"):
        EngineeredAgentState(
            **values,
            active_request_id=UUID(int=1_402),
        )
    with pytest.raises(ValidationError):
        EngineeredAgentState(
            **values,
            resume_count=5,
        )
    with pytest.raises(ValidationError):
        EngineeredAgentState(
            **values,
            resume_count=1,
            replan_count=2,
        )


def test_model_memory_projection_stays_inside_bounded_json_with_multibyte_text() -> (
    None
):
    memory = AgentConversationMemory(
        safe_summary="🙂" * 2_000,
        summarized_turn_count=8,
        recent_turns=[
            AgentMemoryTurn(
                turn_id=UUID(int=1_500 + index),
                role="user" if index % 2 == 0 else "assistant",
                content_summary="🙂" * 1_000,
            )
            for index in range(8)
        ],
    )

    context = _public_context("🙂" * 2_000, memory)

    assert context.root["question"] == "🙂" * 2_000
    assert len(context.model_dump_json().encode("utf-8")) <= 16_384
    with pytest.raises(ValidationError):
        AgentMemoryTurn.model_validate(
            {
                "turn_id": str(CURRENT_TURN_ID),
                "role": "user",
                "content_summary": "德国",
                "tenant_id": str(TENANT_ID),
            }
        )
