"""Persist engineered Agent run trees, task boards, checkpoints, and citations.

Revision ID: 20260905_0011
Revises: 20260902_0010
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0011"
down_revision: str | None = "20260902_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the durable, trusted storage boundary for M2-21 Agent contracts."""

    op.add_column(
        "agent_runs",
        sa.Column(
            "run_kind",
            sa.String(length=16),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column("agent_runs", sa.Column("root_run_id", sa.Uuid(), nullable=True))
    op.add_column("agent_runs", sa.Column("parent_run_id", sa.Uuid(), nullable=True))
    op.add_column("agent_runs", sa.Column("agent_id", sa.String(64), nullable=True))
    op.add_column("agent_runs", sa.Column("task_id", sa.String(64), nullable=True))
    op.add_column("agent_runs", sa.Column("budget_ref", sa.Uuid(), nullable=True))
    op.add_column("agent_runs", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("business_outcome", sa.String(24), nullable=True),
    )

    op.drop_constraint(
        op.f("uq_agent_runs_trace_id"),
        "agent_runs",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_agent_runs_status_allowed"),
        "agent_runs",
        type_="check",
    )
    op.create_unique_constraint(
        op.f("uq_agent_runs_tenant_id_thread_user"),
        "agent_runs",
        ["tenant_id", "id", "thread_id", "user_id"],
    )
    op.create_foreign_key(
        op.f("fk_agent_runs_tenant_root_thread_user"),
        "agent_runs",
        "agent_runs",
        ["tenant_id", "root_run_id", "thread_id", "user_id"],
        ["tenant_id", "id", "thread_id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_agent_runs_tenant_parent_thread_user"),
        "agent_runs",
        "agent_runs",
        ["tenant_id", "parent_run_id", "thread_id", "user_id"],
        ["tenant_id", "id", "thread_id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_status_allowed"),
        "agent_runs",
        "status IN ('waiting', 'running', 'waiting_user', 'completed', "
        "'failed', 'denied', 'timed_out')",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_run_tree_shape"),
        "agent_runs",
        "(run_kind = 'legacy' AND root_run_id IS NULL "
        "AND parent_run_id IS NULL AND agent_id IS NULL AND task_id IS NULL "
        "AND budget_ref IS NULL AND depth IS NULL AND business_outcome IS NULL) "
        "OR (run_kind = 'supervisor' AND root_run_id = id "
        "AND parent_run_id IS NULL AND agent_id = 'supervisor' "
        "AND task_id IS NULL AND budget_ref IS NULL AND depth = 0) "
        "OR (run_kind = 'worker' AND root_run_id IS NOT NULL "
        "AND parent_run_id IS NOT NULL AND root_run_id <> id "
        "AND parent_run_id <> id AND agent_id IS NOT NULL "
        "AND task_id IS NOT NULL AND budget_ref IS NOT NULL "
        "AND depth BETWEEN 1 AND 8)",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_engineered_status_outcome_consistent"),
        "agent_runs",
        "(run_kind = 'legacy' AND status IN "
        "('running', 'completed', 'failed', 'denied', 'timed_out') "
        "AND business_outcome IS NULL) OR "
        "(run_kind <> 'legacy' AND status IN "
        "('waiting', 'running', 'waiting_user') "
        "AND business_outcome IS NULL AND finished_at IS NULL) OR "
        "(run_kind <> 'legacy' AND status = 'completed' "
        "AND business_outcome IN "
        "('answered', 'partial', 'no_evidence', 'unsupported', 'denied') "
        "AND finished_at IS NOT NULL) OR "
        "(run_kind <> 'legacy' AND status = 'failed' "
        "AND business_outcome IN ('timed_out', 'system_error') "
        "AND finished_at IS NOT NULL)",
    )
    op.create_index(
        "uq_agent_runs_root_trace_id",
        "agent_runs",
        ["trace_id"],
        unique=True,
        postgresql_where=sa.text("run_kind IN ('legacy', 'supervisor')"),
    )
    op.create_index(
        "ix_agent_runs_tenant_root_started",
        "agent_runs",
        ["tenant_id", "root_run_id", "started_at"],
        unique=False,
    )

    op.create_unique_constraint(
        op.f("uq_evidences_tenant_id"),
        "evidences",
        ["tenant_id", "id"],
    )

    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("root_run_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("required_capabilities", postgresql.JSONB(), nullable=False),
        sa.Column("assignment_status", sa.String(16), nullable=False),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("execution_status", sa.String(16), nullable=False),
        sa.Column("business_outcome", sa.String(24), nullable=True),
        sa.Column("completion_criteria", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_requirement", postgresql.JSONB(), nullable=False),
        sa.Column("failure_impact", sa.String(32), nullable=False),
        sa.Column("result_json", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("result_sha256", sa.String(64), nullable=True),
        sa.Column("row_version", sa.Integer(), server_default="1", nullable=False),
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
            "sequence_no BETWEEN 1 AND 24",
            name=op.f("ck_agent_tasks_sequence_range"),
        ),
        sa.CheckConstraint(
            "char_length(task_id) BETWEEN 1 AND 64 "
            "AND task_id ~ '^[a-z0-9][a-z0-9_-]{0,63}$'",
            name=op.f("ck_agent_tasks_task_id_format"),
        ),
        sa.CheckConstraint(
            "char_length(goal) BETWEEN 1 AND 2000 "
            "AND char_length(failure_impact) BETWEEN 1 AND 32",
            name=op.f("ck_agent_tasks_text_lengths"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(required_capabilities) = 'array' "
            "AND jsonb_array_length(required_capabilities) <= 5 "
            "AND jsonb_typeof(completion_criteria) = 'array' "
            "AND jsonb_array_length(completion_criteria) BETWEEN 1 AND 8 "
            "AND jsonb_typeof(evidence_requirement) = 'object'",
            name=op.f("ck_agent_tasks_json_shapes"),
        ),
        sa.CheckConstraint(
            "(assignment_status = 'unassigned' AND worker_id IS NULL) OR "
            "(assignment_status = 'assigned' AND worker_id IS NOT NULL)",
            name=op.f("ck_agent_tasks_assignment_consistent"),
        ),
        sa.CheckConstraint(
            "execution_status IN "
            "('waiting', 'running', 'waiting_user', 'completed', 'failed')",
            name=op.f("ck_agent_tasks_execution_status_allowed"),
        ),
        sa.CheckConstraint(
            "(execution_status IN ('waiting', 'running', 'waiting_user') "
            "AND business_outcome IS NULL) OR "
            "(execution_status = 'completed' AND business_outcome IN "
            "('answered', 'partial', 'no_evidence', 'unsupported', 'denied')) OR "
            "(execution_status = 'failed' AND business_outcome IN "
            "('timed_out', 'system_error'))",
            name=op.f("ck_agent_tasks_status_outcome_consistent"),
        ),
        sa.CheckConstraint(
            "failure_impact IN ('blocks_dependents', 'allows_partial', 'non_blocking')",
            name=op.f("ck_agent_tasks_failure_impact_allowed"),
        ),
        sa.CheckConstraint(
            "(result_json IS NULL AND result_sha256 IS NULL) OR "
            "(jsonb_typeof(result_json) = 'object' "
            "AND octet_length(result_json::text) <= 262144 "
            "AND result_sha256 ~ '^[0-9a-f]{64}$')",
            name=op.f("ck_agent_tasks_result_pair_consistent"),
        ),
        sa.CheckConstraint(
            "row_version >= 1",
            name=op.f("ck_agent_tasks_row_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "root_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name=op.f("fk_agent_tasks_tenant_root_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tasks")),
        sa.UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "task_id",
            name=op.f("uq_agent_tasks_root_task"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "sequence_no",
            name=op.f("uq_agent_tasks_root_sequence"),
        ),
    )
    op.create_index(
        "ix_agent_tasks_tenant_root_status",
        "agent_tasks",
        ["tenant_id", "root_run_id", "execution_status"],
        unique=False,
    )

    op.create_table(
        "agent_task_dependencies",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("root_run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("depends_on_task_id", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "task_id <> depends_on_task_id",
            name=op.f("ck_agent_task_dependencies_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "task_id"],
            ["agent_tasks.tenant_id", "agent_tasks.root_run_id", "agent_tasks.task_id"],
            name=op.f("fk_agent_task_dependencies_task"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "depends_on_task_id"],
            ["agent_tasks.tenant_id", "agent_tasks.root_run_id", "agent_tasks.task_id"],
            name=op.f("fk_agent_task_dependencies_dependency"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "root_run_id",
            "task_id",
            "depends_on_task_id",
            name=op.f("pk_agent_task_dependencies"),
        ),
    )
    op.create_index(
        "ix_agent_task_dependencies_tenant_root_dependency",
        "agent_task_dependencies",
        ["tenant_id", "root_run_id", "depends_on_task_id"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION reject_agent_task_dependency_cycle()
        RETURNS trigger AS $$
        BEGIN
            IF EXISTS (
                WITH RECURSIVE reachable(task_id) AS (
                    SELECT NEW.depends_on_task_id
                    UNION
                    SELECT dependency.depends_on_task_id
                    FROM agent_task_dependencies AS dependency
                    JOIN reachable
                      ON dependency.task_id = reachable.task_id
                    WHERE dependency.tenant_id = NEW.tenant_id
                      AND dependency.root_run_id = NEW.root_run_id
                )
                SELECT 1 FROM reachable WHERE task_id = NEW.task_id
            ) THEN
                RAISE EXCEPTION 'agent task dependency cycle is not allowed';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER agent_task_dependencies_reject_cycle
        AFTER INSERT OR UPDATE ON agent_task_dependencies
        DEFERRABLE INITIALLY IMMEDIATE
        FOR EACH ROW EXECUTE FUNCTION reject_agent_task_dependency_cycle()
        """
    )

    op.create_table(
        "agent_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("root_run_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("checkpoint_version", sa.Integer(), nullable=False),
        sa.Column("state_contract_version", sa.String(64), nullable=False),
        sa.Column("state_json", postgresql.JSONB(), nullable=False),
        sa.Column("state_sha256", sa.String(64), nullable=False),
        sa.Column("execution_status", sa.String(16), nullable=False),
        sa.Column("business_outcome", sa.String(24), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "checkpoint_version >= 1",
            name=op.f("ck_agent_checkpoints_version_positive"),
        ),
        sa.CheckConstraint(
            "state_contract_version = 'm2-agent-contract-v1'",
            name=op.f("ck_agent_checkpoints_contract_version_allowed"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(state_json) = 'object' "
            "AND octet_length(state_json::text) <= 262144",
            name=op.f("ck_agent_checkpoints_state_json_bounded"),
        ),
        sa.CheckConstraint(
            "state_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_agent_checkpoints_state_hash_format"),
        ),
        sa.CheckConstraint(
            "execution_status IN "
            "('waiting', 'running', 'waiting_user', 'completed', 'failed')",
            name=op.f("ck_agent_checkpoints_execution_status_allowed"),
        ),
        sa.CheckConstraint(
            "(execution_status IN ('waiting', 'running', 'waiting_user') "
            "AND business_outcome IS NULL) OR "
            "(execution_status = 'completed' AND business_outcome IN "
            "('answered', 'partial', 'no_evidence', 'unsupported', 'denied')) OR "
            "(execution_status = 'failed' AND business_outcome IN "
            "('timed_out', 'system_error'))",
            name=op.f("ck_agent_checkpoints_status_outcome_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "thread_id", "user_id"],
            [
                "agent_runs.tenant_id",
                "agent_runs.id",
                "agent_runs.thread_id",
                "agent_runs.user_id",
            ],
            name=op.f("fk_agent_checkpoints_tenant_root_thread_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_checkpoints")),
        sa.UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "checkpoint_version",
            name=op.f("uq_agent_checkpoints_root_version"),
        ),
    )
    op.create_index(
        "ix_agent_checkpoints_tenant_root_created",
        "agent_checkpoints",
        ["tenant_id", "root_run_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_answer_evidences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("root_run_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("citation_ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "citation_ordinal BETWEEN 1 AND 12",
            name=op.f("ck_agent_answer_evidences_citation_ordinal_range"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "root_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name=op.f("fk_agent_answer_evidences_tenant_root_run"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["evidences.tenant_id", "evidences.id"],
            name=op.f("fk_agent_answer_evidences_tenant_evidence"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_answer_evidences")),
        sa.UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "citation_ordinal",
            name=op.f("uq_agent_answer_evidences_root_ordinal"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "evidence_id",
            name=op.f("uq_agent_answer_evidences_root_evidence"),
        ),
    )
    op.create_index(
        "ix_agent_answer_evidences_tenant_root",
        "agent_answer_evidences",
        ["tenant_id", "root_run_id"],
        unique=False,
    )


def downgrade() -> None:
    """Refuse data loss, then restore the M2-21.8 runtime schema."""

    bind = op.get_bind()
    has_engineered_data = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM agent_runs "
            "WHERE run_kind <> 'legacy' LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM agent_tasks LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM agent_checkpoints LIMIT 1) "
            "OR EXISTS (SELECT 1 FROM agent_answer_evidences LIMIT 1)"
        )
    ).scalar_one()
    if has_engineered_data:
        raise RuntimeError(
            "Cannot downgrade engineered Agent persistence while records exist"
        )

    op.drop_index(
        "ix_agent_answer_evidences_tenant_root",
        table_name="agent_answer_evidences",
    )
    op.drop_table("agent_answer_evidences")
    op.drop_index(
        "ix_agent_checkpoints_tenant_root_created",
        table_name="agent_checkpoints",
    )
    op.drop_table("agent_checkpoints")
    op.execute(
        "DROP TRIGGER agent_task_dependencies_reject_cycle ON agent_task_dependencies"
    )
    op.execute("DROP FUNCTION reject_agent_task_dependency_cycle()")
    op.drop_index(
        "ix_agent_task_dependencies_tenant_root_dependency",
        table_name="agent_task_dependencies",
    )
    op.drop_table("agent_task_dependencies")
    op.drop_index(
        "ix_agent_tasks_tenant_root_status",
        table_name="agent_tasks",
    )
    op.drop_table("agent_tasks")

    op.drop_constraint(
        op.f("uq_evidences_tenant_id"),
        "evidences",
        type_="unique",
    )
    op.drop_index("ix_agent_runs_tenant_root_started", table_name="agent_runs")
    op.drop_index("uq_agent_runs_root_trace_id", table_name="agent_runs")
    op.drop_constraint(
        op.f("ck_agent_runs_engineered_status_outcome_consistent"),
        "agent_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_runs_run_tree_shape"),
        "agent_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_agent_runs_status_allowed"),
        "agent_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_agent_runs_tenant_parent_thread_user"),
        "agent_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_agent_runs_tenant_root_thread_user"),
        "agent_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("uq_agent_runs_tenant_id_thread_user"),
        "agent_runs",
        type_="unique",
    )
    op.create_check_constraint(
        op.f("ck_agent_runs_status_allowed"),
        "agent_runs",
        "status IN ('running', 'completed', 'failed', 'denied', 'timed_out')",
    )
    op.create_unique_constraint(
        op.f("uq_agent_runs_trace_id"),
        "agent_runs",
        ["trace_id"],
    )

    op.drop_column("agent_runs", "business_outcome")
    op.drop_column("agent_runs", "depth")
    op.drop_column("agent_runs", "budget_ref")
    op.drop_column("agent_runs", "task_id")
    op.drop_column("agent_runs", "agent_id")
    op.drop_column("agent_runs", "parent_run_id")
    op.drop_column("agent_runs", "root_run_id")
    op.drop_column("agent_runs", "run_kind")
