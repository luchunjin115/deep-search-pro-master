from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.core.config import Settings
from app.db.session import create_database_runtime


def _config() -> Config:
    return Config("alembic.ini")


def test_engineered_agent_migration_down_up_and_single_head() -> None:
    config = _config()
    assert ScriptDirectory.from_config(config).get_heads() == ["20260905_0011"]
    new_tables = {
        "agent_tasks",
        "agent_task_dependencies",
        "agent_checkpoints",
        "agent_answer_evidences",
    }

    try:
        command.downgrade(config, "20260902_0010")
        runtime = create_database_runtime(Settings(_env_file=".env.example"))
        try:
            inspector = inspect(runtime.engine)
            assert new_tables.isdisjoint(inspector.get_table_names())
            assert "run_kind" not in {
                column["name"] for column in inspector.get_columns("agent_runs")
            }
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260905_0011")
        runtime = create_database_runtime(Settings(_env_file=".env.example"))
        try:
            inspector = inspect(runtime.engine)
            assert new_tables <= set(inspector.get_table_names())
            assert {
                "run_kind",
                "root_run_id",
                "parent_run_id",
                "business_outcome",
            } <= {column["name"] for column in inspector.get_columns("agent_runs")}
            assert any(
                index["name"] == "uq_agent_runs_root_trace_id" and index["unique"]
                for index in inspector.get_indexes("agent_runs")
            )
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260902_0010")
        command.upgrade(config, "20260905_0011")
    finally:
        command.upgrade(config, "head")
