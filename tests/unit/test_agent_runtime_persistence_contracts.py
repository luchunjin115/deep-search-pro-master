from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import JSONB

from app.agents.engineered_state import EngineeredAgentState
from app.models.runtime import (
    AgentAnswerEvidence,
    AgentCheckpoint,
    AgentRun,
    AgentTaskDependency,
    AgentTaskRecord,
)
from app.schemas.agent import ResourceUsage
from app.schemas.evidence import AnswerEvidenceMapping, AnswerEvidenceReference
from app.services.agent_runtime import serialize_checkpoint_state


def _waiting_state() -> EngineeredAgentState:
    return EngineeredAgentState(
        run_id=uuid4(),
        goal="核对库存与知识证据",
        public_context={"market": "US"},
        execution_status="waiting",
        resource_usage=ResourceUsage(
            model_calls=0,
            tool_calls=0,
            input_tokens=0,
            output_tokens=0,
            duration_ms=0,
        ),
    )


def test_runtime_persistence_models_freeze_expected_tables_and_columns() -> None:
    assert AgentTaskRecord.__tablename__ == "agent_tasks"
    assert AgentTaskDependency.__tablename__ == "agent_task_dependencies"
    assert AgentCheckpoint.__tablename__ == "agent_checkpoints"
    assert AgentAnswerEvidence.__tablename__ == "agent_answer_evidences"

    assert {
        "run_kind",
        "root_run_id",
        "parent_run_id",
        "agent_id",
        "task_id",
        "budget_ref",
        "depth",
        "business_outcome",
    } <= set(AgentRun.__table__.columns.keys())
    assert isinstance(AgentTaskRecord.__table__.c.required_capabilities.type, JSONB)
    assert isinstance(AgentTaskRecord.__table__.c.result_json.type, JSONB)
    assert isinstance(AgentCheckpoint.__table__.c.state_json.type, JSONB)


def test_persistence_tables_do_not_offer_sensitive_runtime_columns() -> None:
    forbidden = {
        "chain_of_thought",
        "database_session",
        "raw_tool",
        "secret",
        "sql",
        "local_path",
        "storage_key",
        "raw_exception",
    }
    persisted_columns = {
        column.name
        for table in (
            AgentTaskRecord.__table__,
            AgentTaskDependency.__table__,
            AgentCheckpoint.__table__,
            AgentAnswerEvidence.__table__,
        )
        for column in table.columns
    }
    assert persisted_columns.isdisjoint(forbidden)


def test_answer_evidence_mapping_requires_unique_contiguous_labels() -> None:
    root_run_id = uuid4()
    evidence_id = uuid4()

    valid = AnswerEvidenceMapping(
        root_run_id=root_run_id,
        references=[
            AnswerEvidenceReference(citation_label="[E1]", evidence_id=evidence_id)
        ],
    )
    assert valid.references[0].citation_label == "[E1]"

    with pytest.raises(ValidationError, match="重复"):
        AnswerEvidenceMapping(
            root_run_id=root_run_id,
            references=[
                AnswerEvidenceReference(citation_label="[E1]", evidence_id=evidence_id),
                AnswerEvidenceReference(citation_label="[E2]", evidence_id=evidence_id),
            ],
        )

    with pytest.raises(ValidationError, match="连续"):
        AnswerEvidenceMapping(
            root_run_id=root_run_id,
            references=[
                AnswerEvidenceReference(citation_label="[E2]", evidence_id=uuid4())
            ],
        )


def test_answer_evidence_mapping_rejects_more_than_twelve_references() -> None:
    with pytest.raises(ValidationError):
        AnswerEvidenceMapping(
            root_run_id=uuid4(),
            references=[
                AnswerEvidenceReference(
                    citation_label=f"[E{index}]", evidence_id=uuid4()
                )
                for index in range(1, 14)
            ],
        )


def test_checkpoint_serialization_is_stable_and_round_trips_strict_state() -> None:
    state = _waiting_state()

    first = serialize_checkpoint_state(state)
    second = serialize_checkpoint_state(state)

    assert first.payload == second.payload
    assert first.sha256 == second.sha256
    assert first.size_bytes == second.size_bytes
    restored = EngineeredAgentState.model_validate(first.payload)
    assert restored == state
    assert first.execution_status == "waiting"
    assert first.business_outcome is None


def test_checkpoint_boundary_rejects_sensitive_state_before_serialization() -> None:
    with pytest.raises(ValidationError, match="sensitive"):
        EngineeredAgentState(
            run_id=uuid4(),
            goal="核对库存",
            public_context={"nested": {"api_key": "must-not-persist"}},
            execution_status="completed",
            business_outcome="answered",
            public_summary="已完成",
            stop_reason="finished",
            resource_usage=ResourceUsage(
                model_calls=0,
                tool_calls=0,
                input_tokens=0,
                output_tokens=0,
                duration_ms=0,
            ),
        )
