"""Add reusable Context to ToolCall audit links.

Revision ID: 20260902_0010
Revises: 20260901_0009
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0010"
down_revision: str | None = "20260901_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_M2_DOCUMENT_EVIDENCE_SHAPE = (
    "(source_type = 'database' "
    "AND evidence_schema_version = 'm1-database-evidence-v1' "
    "AND agent_run_id IS NOT NULL AND tool_call_id IS NOT NULL "
    "AND source_locator IS NOT NULL AND source_locator_json IS NULL "
    "AND query_summary IS NOT NULL AND structured_data IS NOT NULL "
    "AND access_scope IS NOT NULL AND trust_level = 'internal_demo' "
    "AND context_artifact_id IS NULL AND citation_ordinal IS NULL "
    "AND file_id IS NULL AND document_id IS NULL "
    "AND document_version_id IS NULL AND document_chunk_set_id IS NULL "
    "AND document_index_set_id IS NULL AND document_chunk_id IS NULL "
    "AND source_content_sha256 IS NULL AND context_text_sha256 IS NULL) "
    "OR (source_type IN ('knowledge', 'user_file') "
    "AND evidence_schema_version = 'm2-document-evidence-v1' "
    "AND agent_run_id IS NULL AND tool_call_id IS NULL "
    "AND source_locator IS NULL AND source_locator_json IS NOT NULL "
    "AND query_summary IS NULL AND structured_data IS NULL "
    "AND access_scope IS NULL AND trust_level = 'document_snapshot' "
    "AND context_artifact_id IS NOT NULL "
    "AND citation_ordinal IS NOT NULL AND file_id IS NOT NULL "
    "AND document_id IS NOT NULL AND document_version_id IS NOT NULL "
    "AND document_chunk_set_id IS NOT NULL "
    "AND document_index_set_id IS NOT NULL "
    "AND document_chunk_id IS NOT NULL "
    "AND source_content_sha256 IS NOT NULL "
    "AND context_text_sha256 IS NOT NULL)"
)

_M2_0009_EVIDENCE_SHAPE = _M2_DOCUMENT_EVIDENCE_SHAPE.replace(
    "AND agent_run_id IS NULL AND tool_call_id IS NULL "
    "AND source_locator IS NULL AND source_locator_json IS NOT NULL ",
    "AND source_locator IS NULL AND source_locator_json IS NOT NULL ",
)


def upgrade() -> None:
    """Backfill reusable Context audit links and unbind document Evidence."""

    op.create_table(
        "tool_context_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.Uuid(), nullable=False),
        sa.Column("context_artifact_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "tool_call_id", "agent_run_id"],
            ["tool_calls.tenant_id", "tool_calls.id", "tool_calls.agent_run_id"],
            name=op.f("fk_tool_context_links_tenant_tool_call_run"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "context_artifact_id"],
            ["context_artifacts.tenant_id", "context_artifacts.id"],
            name=op.f("fk_tool_context_links_tenant_context"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_context_links")),
        sa.UniqueConstraint(
            "tenant_id",
            "tool_call_id",
            name=op.f("uq_tool_context_links_tenant_tool_call"),
        ),
    )
    op.create_index(
        "ix_tool_context_links_tenant_context",
        "tool_context_links",
        ["tenant_id", "context_artifact_id"],
        unique=False,
    )

    bind = op.get_bind()
    has_unrepresentable_binding = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM evidences "
            "WHERE source_type IN ('knowledge', 'user_file') "
            "AND agent_run_id IS NOT NULL "
            "GROUP BY tenant_id, agent_run_id, tool_call_id "
            "HAVING count(DISTINCT context_artifact_id) > 1)"
        )
    ).scalar_one()
    if has_unrepresentable_binding:
        raise RuntimeError(
            "Cannot migrate document Evidence with one ToolCall bound to multiple Contexts"
        )

    bind.execute(
        sa.text(
            "INSERT INTO tool_context_links ("
            "id, tenant_id, agent_run_id, tool_call_id, context_artifact_id, created_at"
            ") "
            "SELECT "
            "md5(tenant_id::text || ':' || tool_call_id::text || ':' "
            "|| context_artifact_id::text)::uuid, "
            "tenant_id, agent_run_id, tool_call_id, context_artifact_id, min(created_at) "
            "FROM evidences "
            "WHERE source_type IN ('knowledge', 'user_file') "
            "AND agent_run_id IS NOT NULL "
            "GROUP BY tenant_id, agent_run_id, tool_call_id, context_artifact_id"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE evidences SET agent_run_id = NULL, tool_call_id = NULL "
            "WHERE source_type IN ('knowledge', 'user_file')"
        )
    )

    op.drop_constraint(
        op.f("ck_evidences_source_shape"),
        "evidences",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_evidences_source_shape"),
        "evidences",
        _M2_DOCUMENT_EVIDENCE_SHAPE,
    )


def downgrade() -> None:
    """Refuse to discard Tool-Context audit links, otherwise restore 0009."""

    bind = op.get_bind()
    has_links = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tool_context_links LIMIT 1)")
    ).scalar_one()
    if has_links:
        raise RuntimeError(
            "Cannot downgrade Tool-Context audit links while associations exist"
        )

    op.drop_constraint(
        op.f("ck_evidences_source_shape"),
        "evidences",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_evidences_source_shape"),
        "evidences",
        _M2_0009_EVIDENCE_SHAPE,
    )
    op.drop_index(
        "ix_tool_context_links_tenant_context",
        table_name="tool_context_links",
    )
    op.drop_table("tool_context_links")
