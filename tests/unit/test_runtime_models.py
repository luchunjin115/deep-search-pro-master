import warnings

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.models.runtime import AgentRun, Evidence, Message, Thread, ToolCall


def test_all_orm_relationships_configure_without_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()


def test_runtime_metadata_contains_m1_06_tables() -> None:
    assert {
        "agent_runs",
        "evidences",
        "messages",
        "threads",
        "tool_calls",
    } <= set(Base.metadata.tables)


def test_trace_id_is_unique() -> None:
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in AgentRun.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("trace_id",) in unique_column_sets


def test_runtime_json_fields_use_postgresql_jsonb() -> None:
    assert isinstance(ToolCall.__table__.c.arguments_summary.type, JSONB)
    assert isinstance(Evidence.__table__.c.query_summary.type, JSONB)
    assert isinstance(Evidence.__table__.c.structured_data.type, JSONB)
    assert isinstance(Evidence.__table__.c.access_scope.type, JSONB)


def test_message_stores_summary_not_raw_model_payload() -> None:
    message_columns = set(Message.__table__.columns.keys())

    assert "content_summary" in message_columns
    assert "raw_model_input" not in message_columns
    assert "raw_model_output" not in message_columns
    assert Thread.__tablename__ == "threads"
