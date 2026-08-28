"""Create M1 conversations, execution audit, tool calls, and evidence.

Revision ID: 20260828_0003
Revises: 20260828_0002
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260828_0003"
down_revision: str | None = "20260828_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the M1 execution and evidence persistence boundary."""

    op.create_unique_constraint(
        "uq_users_tenant_id_id",
        "users",
        ["tenant_id", "id"],
    )
    op.create_table(
        "threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name=op.f("ck_threads_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_threads_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_threads_tenant_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threads")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_threads_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "user_id",
            name=op.f("uq_threads_tenant_id_user_id"),
        ),
    )
    op.create_index(
        "ix_threads_tenant_user_created",
        "threads",
        ["tenant_id", "user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content_summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(content_summary) BETWEEN 1 AND 4000",
            name=op.f("ck_messages_content_summary_length"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name=op.f("ck_messages_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "thread_id"],
            ["threads.tenant_id", "threads.id"],
            name=op.f("fk_messages_tenant_thread"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_tenant_thread_created",
        "messages",
        ["tenant_id", "thread_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("route", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "model_call_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "tool_call_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_agent_runs_duration_ms_nonnegative"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_agent_runs_finished_after_started"),
        ),
        sa.CheckConstraint(
            "model_call_count >= 0",
            name=op.f("ck_agent_runs_model_call_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'denied', 'timed_out')",
            name=op.f("ck_agent_runs_status_allowed"),
        ),
        sa.CheckConstraint(
            "tool_call_count >= 0",
            name=op.f("ck_agent_runs_tool_call_count_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "thread_id", "user_id"],
            ["threads.tenant_id", "threads.id", "threads.user_id"],
            name=op.f("fk_agent_runs_tenant_thread_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_agent_runs_tenant_id_id"),
        ),
        sa.UniqueConstraint("trace_id", name=op.f("uq_agent_runs_trace_id")),
    )
    op.create_index(
        "ix_agent_runs_tenant_thread_started",
        "agent_runs",
        ["tenant_id", "thread_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("tool_version", sa.String(length=32), nullable=False),
        sa.Column(
            "arguments_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("permission_result", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "jsonb_typeof(arguments_summary) = 'object'",
            name=op.f("ck_tool_calls_arguments_summary_object"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_tool_calls_duration_ms_nonnegative"),
        ),
        sa.CheckConstraint(
            "permission_result IN ('allowed', 'denied')",
            name=op.f("ck_tool_calls_permission_result_allowed"),
        ),
        sa.CheckConstraint(
            "sequence_no >= 1",
            name=op.f("ck_tool_calls_sequence_no_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'error', 'denied', 'timeout')",
            name=op.f("ck_tool_calls_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name=op.f("fk_tool_calls_tenant_agent_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_calls")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "agent_run_id",
            name=op.f("uq_tool_calls_tenant_id_run_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_run_id",
            "sequence_no",
            name=op.f("uq_tool_calls_tenant_run_sequence"),
        ),
    )
    op.create_table(
        "evidences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("source_locator", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column(
            "query_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "structured_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "trust_level",
            sa.String(length=32),
            server_default=sa.text("'internal_demo'"),
            nullable=False,
        ),
        sa.Column(
            "access_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "synthetic_data",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(access_scope) = 'object'",
            name=op.f("ck_evidences_access_scope_object"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_evidences_confidence_range"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(query_summary) = 'object'",
            name=op.f("ck_evidences_query_summary_object"),
        ),
        sa.CheckConstraint(
            "source_name IN ('synthetic_inventory', 'synthetic_product_catalog')",
            name=op.f("ck_evidences_source_name_allowed"),
        ),
        sa.CheckConstraint(
            "source_type = 'database'",
            name=op.f("ck_evidences_source_type_database"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(structured_data) = 'object'",
            name=op.f("ck_evidences_structured_data_object"),
        ),
        sa.CheckConstraint(
            "synthetic_data",
            name=op.f("ck_evidences_synthetic_data_required"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "tool_call_id", "agent_run_id"],
            ["tool_calls.tenant_id", "tool_calls.id", "tool_calls.agent_run_id"],
            name=op.f("fk_evidences_tenant_tool_call_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidences")),
    )
    op.create_index(
        "ix_evidences_tenant_run",
        "evidences",
        ["tenant_id", "agent_run_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the M1 execution and evidence boundary only."""

    op.drop_index("ix_evidences_tenant_run", table_name="evidences")
    op.drop_table("evidences")
    op.drop_table("tool_calls")
    op.drop_index("ix_agent_runs_tenant_thread_started", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_messages_tenant_thread_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_threads_tenant_user_created", table_name="threads")
    op.drop_table("threads")
    op.drop_constraint("uq_users_tenant_id_id", "users", type_="unique")
