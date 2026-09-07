"""Conversation, execution audit, Context, and Evidence models for M1/M2."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.identity import Tenant, User


class Thread(Base):
    """A tenant-scoped chat conversation owned by one user."""

    __tablename__ = "threads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_threads_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "user_id",
            name="uq_threads_tenant_id_user_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_threads_tenant_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="status_allowed",
        ),
        Index("ix_threads_tenant_user_created", "tenant_id", "user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active",
        server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tenant: Mapped[Tenant] = relationship(overlaps="user")
    user: Mapped[User] = relationship(overlaps="tenant")
    messages: Mapped[list[Message]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    runs: Mapped[list[AgentRun]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    """A bounded user question or assistant answer summary."""

    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "thread_id"],
            ["threads.tenant_id", "threads.id"],
            name="fk_messages_tenant_thread",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="role_allowed",
        ),
        CheckConstraint(
            "char_length(content_summary) BETWEEN 1 AND 4000",
            name="content_summary_length",
        ),
        Index(
            "ix_messages_tenant_thread_created",
            "tenant_id",
            "thread_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    thread_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    thread: Mapped[Thread] = relationship(back_populates="messages")


class AgentRun(Base):
    """One legacy run or one supervisor/worker run in a trusted run tree."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "id",
            "thread_id",
            "user_id",
            name="uq_agent_runs_tenant_id_thread_user",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "thread_id", "user_id"],
            ["threads.tenant_id", "threads.id", "threads.user_id"],
            name="fk_agent_runs_tenant_thread_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "thread_id", "user_id"],
            [
                "agent_runs.tenant_id",
                "agent_runs.id",
                "agent_runs.thread_id",
                "agent_runs.user_id",
            ],
            name="fk_agent_runs_tenant_root_thread_user",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_run_id", "thread_id", "user_id"],
            [
                "agent_runs.tenant_id",
                "agent_runs.id",
                "agent_runs.thread_id",
                "agent_runs.user_id",
            ],
            name="fk_agent_runs_tenant_parent_thread_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('waiting', 'running', 'waiting_user', 'completed', "
            "'failed', 'denied', 'timed_out')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(run_kind = 'legacy' AND root_run_id IS NULL "
            "AND parent_run_id IS NULL AND agent_id IS NULL AND task_id IS NULL "
            "AND budget_ref IS NULL AND depth IS NULL "
            "AND business_outcome IS NULL) "
            "OR (run_kind = 'supervisor' AND root_run_id = id "
            "AND parent_run_id IS NULL AND agent_id = 'supervisor' "
            "AND task_id IS NULL AND budget_ref IS NULL AND depth = 0) "
            "OR (run_kind = 'worker' AND root_run_id IS NOT NULL "
            "AND parent_run_id IS NOT NULL AND root_run_id <> id "
            "AND parent_run_id <> id AND agent_id IS NOT NULL "
            "AND task_id IS NOT NULL AND budget_ref IS NOT NULL "
            "AND depth BETWEEN 1 AND 8)",
            name="run_tree_shape",
        ),
        CheckConstraint(
            "(run_kind = 'legacy' AND status IN "
            "('running', 'completed', 'failed', 'denied', 'timed_out') "
            "AND business_outcome IS NULL) OR "
            "(run_kind <> 'legacy' "
            "AND status IN ('waiting', 'running', 'waiting_user') "
            "AND business_outcome IS NULL AND finished_at IS NULL) OR "
            "(run_kind <> 'legacy' AND status = 'completed' "
            "AND business_outcome IN "
            "('answered', 'partial', 'no_evidence', 'unsupported', 'denied') "
            "AND finished_at IS NOT NULL) OR "
            "(run_kind <> 'legacy' AND status = 'failed' AND business_outcome IN "
            "('timed_out', 'system_error') AND finished_at IS NOT NULL)",
            name="engineered_status_outcome_consistent",
        ),
        CheckConstraint("model_call_count >= 0", name="model_call_count_nonnegative"),
        CheckConstraint("tool_call_count >= 0", name="tool_call_count_nonnegative"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="finished_after_started",
        ),
        Index(
            "ix_agent_runs_tenant_thread_started",
            "tenant_id",
            "thread_id",
            "started_at",
        ),
        Index(
            "uq_agent_runs_root_trace_id",
            "trace_id",
            unique=True,
            postgresql_where=text("run_kind IN ('legacy', 'supervisor')"),
        ),
        Index(
            "ix_agent_runs_tenant_root_started",
            "tenant_id",
            "root_run_id",
            "started_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    thread_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    trace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route: Mapped[str] = mapped_column(String(64), nullable=False)
    run_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="legacy",
    )
    root_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    parent_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    agent_id: Mapped[str | None] = mapped_column(String(64))
    task_id: Mapped[str | None] = mapped_column(String(64))
    budget_ref: Mapped[UUID | None] = mapped_column(Uuid)
    depth: Mapped[int | None] = mapped_column(Integer)
    business_outcome: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="running",
        server_default="running",
    )
    model_call_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    tool_call_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    thread: Mapped[Thread] = relationship(back_populates="runs")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="agent_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ToolCall(Base):
    """A safe audit summary of one guarded Agent Tool execution."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            "agent_run_id",
            name="uq_tool_calls_tenant_id_run_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "agent_run_id",
            "sequence_no",
            name="uq_tool_calls_tenant_run_sequence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_tool_calls_tenant_agent_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence_no >= 1", name="sequence_no_positive"),
        CheckConstraint(
            "permission_result IN ('allowed', 'denied')",
            name="permission_result_allowed",
        ),
        CheckConstraint(
            "status IN ('running', 'success', 'error', 'denied', 'timeout')",
            name="status_allowed",
        ),
        CheckConstraint(
            "jsonb_typeof(arguments_summary) = 'object'",
            name="arguments_summary_object",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    arguments_summary: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    permission_result: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent_run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
    evidences: Mapped[list[Evidence]] = relationship(
        back_populates="tool_call",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    context_link: Mapped[ToolContextLink | None] = relationship(
        back_populates="tool_call",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class ContextArtifact(Base):
    """One immutable, tenant-scoped Context Bundle identity and budget snapshot."""

    __tablename__ = "context_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_context_artifacts_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "requested_by_user_id",
            "identity_sha256",
            name="uq_context_artifacts_tenant_user_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_context_artifacts_tenant_user",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "contract_version = 'm2-context-bundle-v1' "
            "AND token_counter_version = 'm2-unicode-token-counter-v1'",
            name="versions_allowed",
        ),
        CheckConstraint(
            "query_sha256 ~ '^[0-9a-f]{64}$' "
            "AND retrieval_snapshot_sha256 ~ '^[0-9a-f]{64}$' "
            "AND config_sha256 ~ '^[0-9a-f]{64}$' "
            "AND context_sha256 ~ '^[0-9a-f]{64}$' "
            "AND identity_sha256 ~ '^[0-9a-f]{64}$'",
            name="hashes_format",
        ),
        CheckConstraint(
            "jsonb_typeof(retrieval_snapshot_json) = 'object' "
            "AND jsonb_typeof(config_json) = 'object'",
            name="json_objects",
        ),
        CheckConstraint(
            "max_tokens BETWEEN 700 AND 16000 "
            "AND total_tokens BETWEEN 0 AND max_tokens "
            "AND segment_count BETWEEN 0 AND 12",
            name="budget_bounds",
        ),
        CheckConstraint(
            "(segment_count = 0 AND total_tokens = 0) "
            "OR (segment_count >= 1 AND total_tokens >= segment_count)",
            name="empty_state_consistent",
        ),
        Index(
            "ix_context_artifacts_tenant_user_created",
            "tenant_id",
            "requested_by_user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    token_counter_version: Mapped[str] = mapped_column(String(100), nullable=False)
    query_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_snapshot_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    retrieval_snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    context_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    requested_by_user: Mapped[User] = relationship()
    evidences: Mapped[list[Evidence]] = relationship(
        back_populates="context_artifact",
        viewonly=True,
    )
    tool_context_links: Mapped[list[ToolContextLink]] = relationship(
        back_populates="context_artifact",
        viewonly=True,
    )


class ToolContextLink(Base):
    """One guarded ToolCall's auditable use of a reusable Context Artifact."""

    __tablename__ = "tool_context_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "tool_call_id",
            name="uq_tool_context_links_tenant_tool_call",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tool_call_id", "agent_run_id"],
            ["tool_calls.tenant_id", "tool_calls.id", "tool_calls.agent_run_id"],
            name="fk_tool_context_links_tenant_tool_call_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "context_artifact_id"],
            ["context_artifacts.tenant_id", "context_artifacts.id"],
            name="fk_tool_context_links_tenant_context",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_tool_context_links_tenant_context",
            "tenant_id",
            "context_artifact_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    tool_call_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    context_artifact_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tool_call: Mapped[ToolCall] = relationship(back_populates="context_link")
    context_artifact: Mapped[ContextArtifact] = relationship(
        back_populates="tool_context_links",
        viewonly=True,
    )


class Evidence(Base):
    """A tenant-scoped database or document fact supporting an answer."""

    __tablename__ = "evidences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_evidences_tenant_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tool_call_id", "agent_run_id"],
            ["tool_calls.tenant_id", "tool_calls.id", "tool_calls.agent_run_id"],
            name="fk_evidences_tenant_tool_call_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "context_artifact_id"],
            ["context_artifacts.tenant_id", "context_artifacts.id"],
            name="fk_evidences_tenant_context",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id", "file_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
                "document_versions.file_id",
            ],
            name="fk_evidences_tenant_version_document_file",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "document_chunk_id",
                "document_index_set_id",
                "document_chunk_set_id",
                "document_version_id",
                "document_id",
            ],
            [
                "document_chunks.tenant_id",
                "document_chunks.id",
                "document_chunks.document_index_set_id",
                "document_chunks.document_chunk_set_id",
                "document_chunks.document_version_id",
                "document_chunks.document_id",
            ],
            name="fk_evidences_tenant_chunk_provenance",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_type IN ('database', 'knowledge', 'user_file')",
            name="source_type_allowed",
        ),
        CheckConstraint(
            "(source_type = 'database' AND source_name IN "
            "('synthetic_inventory', 'synthetic_product_catalog')) "
            "OR (source_type IN ('knowledge', 'user_file') "
            "AND source_name = 'document_chunk')",
            name="source_name_matches_type",
        ),
        CheckConstraint(
            "(agent_run_id IS NULL AND tool_call_id IS NULL) "
            "OR (agent_run_id IS NOT NULL AND tool_call_id IS NOT NULL)",
            name="runtime_trace_pair",
        ),
        CheckConstraint(
            "(query_summary IS NULL OR jsonb_typeof(query_summary) = 'object') "
            "AND (structured_data IS NULL "
            "OR jsonb_typeof(structured_data) = 'object') "
            "AND (access_scope IS NULL OR jsonb_typeof(access_scope) = 'object') "
            "AND (source_locator_json IS NULL "
            "OR jsonb_typeof(source_locator_json) = 'object')",
            name="json_shapes",
        ),
        CheckConstraint(
            "citation_ordinal IS NULL OR citation_ordinal BETWEEN 1 AND 12",
            name="citation_ordinal_range",
        ),
        CheckConstraint(
            "(source_content_sha256 IS NULL "
            "OR source_content_sha256 ~ '^[0-9a-f]{64}$') "
            "AND (context_text_sha256 IS NULL "
            "OR context_text_sha256 ~ '^[0-9a-f]{64}$')",
            name="hashes_format",
        ),
        CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 300 "
            "AND char_length(excerpt) BETWEEN 1 AND 1000",
            name="public_text_lengths",
        ),
        CheckConstraint(
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
            "AND context_text_sha256 IS NOT NULL)",
            name="source_shape",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint("synthetic_data", name="synthetic_data_required"),
        UniqueConstraint(
            "tenant_id",
            "context_artifact_id",
            "citation_ordinal",
            name="uq_evidences_context_citation",
        ),
        UniqueConstraint(
            "tenant_id",
            "context_artifact_id",
            "document_chunk_id",
            name="uq_evidences_context_chunk",
        ),
        Index("ix_evidences_tenant_run", "tenant_id", "agent_run_id"),
        Index(
            "ix_evidences_tenant_context_citation",
            "tenant_id",
            "context_artifact_id",
            "citation_ordinal",
        ),
        Index(
            "ix_evidences_tenant_document_version",
            "tenant_id",
            "document_id",
            "document_version_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    agent_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    tool_call_id: Mapped[UUID | None] = mapped_column(Uuid)
    evidence_schema_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="m1-database-evidence-v1",
        server_default="m1-database-evidence-v1",
    )
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(255))
    source_locator_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    query_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    structured_data: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    trust_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="internal_demo",
        server_default="internal_demo",
    )
    access_scope: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    context_artifact_id: Mapped[UUID | None] = mapped_column(Uuid)
    citation_ordinal: Mapped[int | None] = mapped_column(Integer)
    file_id: Mapped[UUID | None] = mapped_column(Uuid)
    document_id: Mapped[UUID | None] = mapped_column(Uuid)
    document_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    document_chunk_set_id: Mapped[UUID | None] = mapped_column(Uuid)
    document_index_set_id: Mapped[UUID | None] = mapped_column(Uuid)
    document_chunk_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_content_sha256: Mapped[str | None] = mapped_column(String(64))
    context_text_sha256: Mapped[str | None] = mapped_column(String(64))
    synthetic_data: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tool_call: Mapped[ToolCall | None] = relationship(back_populates="evidences")
    context_artifact: Mapped[ContextArtifact | None] = relationship(
        back_populates="evidences",
        viewonly=True,
    )


class AgentTaskRecord(Base):
    """One normalized task on the shared, tenant-scoped Agent task board."""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "task_id",
            name="uq_agent_tasks_root_task",
        ),
        UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "sequence_no",
            name="uq_agent_tasks_root_sequence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "root_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_tasks_tenant_root_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence_no BETWEEN 1 AND 24", name="sequence_range"),
        CheckConstraint(
            "char_length(task_id) BETWEEN 1 AND 64 "
            "AND task_id ~ '^[a-z0-9][a-z0-9_-]{0,63}$'",
            name="task_id_format",
        ),
        CheckConstraint(
            "char_length(goal) BETWEEN 1 AND 2000 "
            "AND char_length(failure_impact) BETWEEN 1 AND 32",
            name="text_lengths",
        ),
        CheckConstraint(
            "jsonb_typeof(required_capabilities) = 'array' "
            "AND jsonb_array_length(required_capabilities) <= 5 "
            "AND jsonb_typeof(completion_criteria) = 'array' "
            "AND jsonb_array_length(completion_criteria) BETWEEN 1 AND 8 "
            "AND jsonb_typeof(evidence_requirement) = 'object'",
            name="json_shapes",
        ),
        CheckConstraint(
            "(assignment_status = 'unassigned' AND worker_id IS NULL) OR "
            "(assignment_status = 'assigned' AND worker_id IS NOT NULL)",
            name="assignment_consistent",
        ),
        CheckConstraint(
            "execution_status IN "
            "('waiting', 'running', 'waiting_user', 'completed', 'failed')",
            name="execution_status_allowed",
        ),
        CheckConstraint(
            "(execution_status IN ('waiting', 'running', 'waiting_user') "
            "AND business_outcome IS NULL) OR "
            "(execution_status = 'completed' AND business_outcome IN "
            "('answered', 'partial', 'no_evidence', 'unsupported', 'denied')) OR "
            "(execution_status = 'failed' AND business_outcome IN "
            "('timed_out', 'system_error'))",
            name="status_outcome_consistent",
        ),
        CheckConstraint(
            "failure_impact IN ('blocks_dependents', 'allows_partial', 'non_blocking')",
            name="failure_impact_allowed",
        ),
        CheckConstraint(
            "(result_json IS NULL AND result_sha256 IS NULL) OR "
            "(jsonb_typeof(result_json) = 'object' "
            "AND octet_length(result_json::text) <= 262144 "
            "AND result_sha256 ~ '^[0-9a-f]{64}$')",
            name="result_pair_consistent",
        ),
        CheckConstraint("row_version >= 1", name="row_version_positive"),
        Index(
            "ix_agent_tasks_tenant_root_status",
            "tenant_id",
            "root_run_id",
            "execution_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    root_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    plan_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    assignment_status: Mapped[str] = mapped_column(String(16), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(64))
    execution_status: Mapped[str] = mapped_column(String(16), nullable=False)
    business_outcome: Mapped[str | None] = mapped_column(String(24))
    completion_criteria: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_requirement: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    failure_impact: Mapped[str] = mapped_column(String(32), nullable=False)
    result_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    result_sha256: Mapped[str | None] = mapped_column(String(64))
    row_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AgentTaskDependency(Base):
    """One normalized edge in the shared Agent task DAG."""

    __tablename__ = "agent_task_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "task_id"],
            ["agent_tasks.tenant_id", "agent_tasks.root_run_id", "agent_tasks.task_id"],
            name="fk_agent_task_dependencies_task",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "depends_on_task_id"],
            ["agent_tasks.tenant_id", "agent_tasks.root_run_id", "agent_tasks.task_id"],
            name="fk_agent_task_dependencies_dependency",
            ondelete="CASCADE",
        ),
        CheckConstraint("task_id <> depends_on_task_id", name="not_self"),
        Index(
            "ix_agent_task_dependencies_tenant_root_dependency",
            "tenant_id",
            "root_run_id",
            "depends_on_task_id",
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    root_run_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    depends_on_task_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class AgentCheckpoint(Base):
    """One immutable, integrity-checked checkpoint for a trusted root run."""

    __tablename__ = "agent_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "checkpoint_version",
            name="uq_agent_checkpoints_root_version",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "root_run_id", "thread_id", "user_id"],
            [
                "agent_runs.tenant_id",
                "agent_runs.id",
                "agent_runs.thread_id",
                "agent_runs.user_id",
            ],
            name="fk_agent_checkpoints_tenant_root_thread_user",
            ondelete="CASCADE",
        ),
        CheckConstraint("checkpoint_version >= 1", name="version_positive"),
        CheckConstraint(
            "state_contract_version = 'm2-agent-contract-v1'",
            name="contract_version_allowed",
        ),
        CheckConstraint(
            "jsonb_typeof(state_json) = 'object' "
            "AND octet_length(state_json::text) <= 262144",
            name="state_json_bounded",
        ),
        CheckConstraint(
            "state_sha256 ~ '^[0-9a-f]{64}$'",
            name="state_hash_format",
        ),
        CheckConstraint(
            "execution_status IN "
            "('waiting', 'running', 'waiting_user', 'completed', 'failed')",
            name="execution_status_allowed",
        ),
        CheckConstraint(
            "(execution_status IN ('waiting', 'running', 'waiting_user') "
            "AND business_outcome IS NULL) OR "
            "(execution_status = 'completed' AND business_outcome IN "
            "('answered', 'partial', 'no_evidence', 'unsupported', 'denied')) OR "
            "(execution_status = 'failed' AND business_outcome IN "
            "('timed_out', 'system_error'))",
            name="status_outcome_consistent",
        ),
        Index(
            "ix_agent_checkpoints_tenant_root_created",
            "tenant_id",
            "root_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    root_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    thread_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    checkpoint_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    state_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(16), nullable=False)
    business_outcome: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AgentAnswerEvidence(Base):
    """A final answer's stable, ordered mapping from labels to Evidence IDs."""

    __tablename__ = "agent_answer_evidences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "citation_ordinal",
            name="uq_agent_answer_evidences_root_ordinal",
        ),
        UniqueConstraint(
            "tenant_id",
            "root_run_id",
            "evidence_id",
            name="uq_agent_answer_evidences_root_evidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "root_run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_answer_evidences_tenant_root_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["evidences.tenant_id", "evidences.id"],
            name="fk_agent_answer_evidences_tenant_evidence",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "citation_ordinal BETWEEN 1 AND 12",
            name="citation_ordinal_range",
        ),
        Index(
            "ix_agent_answer_evidences_tenant_root",
            "tenant_id",
            "root_run_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    root_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    citation_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
