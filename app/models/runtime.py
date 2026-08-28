"""Conversation, execution audit, tool call, and evidence models for M1."""

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
    """One traceable execution of the M1 graph for a thread and user."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("trace_id", name="uq_agent_runs_trace_id"),
        UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "thread_id", "user_id"],
            ["threads.tenant_id", "threads.id", "threads.user_id"],
            name="fk_agent_runs_tenant_thread_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'denied', 'timed_out')",
            name="status_allowed",
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
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    thread_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    trace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    route: Mapped[str] = mapped_column(String(64), nullable=False)
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


class Evidence(Base):
    """A structured, tenant-scoped fact supporting an M1 answer."""

    __tablename__ = "evidences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "tool_call_id", "agent_run_id"],
            ["tool_calls.tenant_id", "tool_calls.id", "tool_calls.agent_run_id"],
            name="fk_evidences_tenant_tool_call_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("source_type = 'database'", name="source_type_database"),
        CheckConstraint(
            "source_name IN ('synthetic_inventory', 'synthetic_product_catalog')",
            name="source_name_allowed",
        ),
        CheckConstraint(
            "jsonb_typeof(query_summary) = 'object'",
            name="query_summary_object",
        ),
        CheckConstraint(
            "jsonb_typeof(structured_data) = 'object'",
            name="structured_data_object",
        ),
        CheckConstraint(
            "jsonb_typeof(access_scope) = 'object'",
            name="access_scope_object",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint("synthetic_data", name="synthetic_data_required"),
        Index("ix_evidences_tenant_run", "tenant_id", "agent_run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    agent_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    tool_call_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    query_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    structured_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
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
    access_scope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
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

    tool_call: Mapped[ToolCall] = relationship(back_populates="evidences")
