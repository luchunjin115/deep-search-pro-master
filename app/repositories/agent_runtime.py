"""Fixed, tenant-scoped persistence operations for engineered Agent runs."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.runtime import (
    AgentAnswerEvidence,
    AgentCheckpoint,
    AgentRun,
    AgentTaskDependency,
    AgentTaskRecord,
    Evidence,
    Thread,
    ToolCall,
)
from app.repositories.common import apply_statement_timeout


class AgentRuntimeRepository:
    """Persist only fixed Agent records; callers cannot provide SQL or filters."""

    def __init__(self, session: Session, statement_timeout_ms: int) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def find_owned_active_thread(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        for_update: bool = False,
    ) -> Thread | None:
        self._prepare()
        statement = select(Thread).where(
            Thread.tenant_id == tenant_id,
            Thread.user_id == user_id,
            Thread.id == thread_id,
            Thread.status == "active",
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def add_root_run(self, row: AgentRun) -> AgentRun:
        self._prepare()
        self._session.add(row)
        self._session.flush()
        return row

    def find_owned_root_run(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        root_run_id: UUID,
        for_update: bool = False,
    ) -> AgentRun | None:
        self._prepare()
        statement = select(AgentRun).where(
            AgentRun.tenant_id == tenant_id,
            AgentRun.user_id == user_id,
            AgentRun.thread_id == thread_id,
            AgentRun.id == root_run_id,
            AgentRun.root_run_id == root_run_id,
            AgentRun.run_kind == "supervisor",
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def add_worker_run(self, row: AgentRun) -> AgentRun:
        self._prepare()
        self._session.add(row)
        self._session.flush()
        return row

    def find_owned_worker_run(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        root_run_id: UUID,
        worker_run_id: UUID,
    ) -> AgentRun | None:
        self._prepare()
        return self._session.scalar(
            select(AgentRun).where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.user_id == user_id,
                AgentRun.thread_id == thread_id,
                AgentRun.root_run_id == root_run_id,
                AgentRun.id == worker_run_id,
                AgentRun.run_kind == "worker",
            )
        )

    def add_tasks(
        self,
        rows: Sequence[AgentTaskRecord],
        dependencies: Sequence[AgentTaskDependency],
    ) -> None:
        self._prepare()
        self._session.add_all(rows)
        self._session.flush()
        self._session.add_all(dependencies)
        self._session.flush()

    def list_tasks(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> list[AgentTaskRecord]:
        self._prepare()
        return list(
            self._session.scalars(
                select(AgentTaskRecord)
                .where(
                    AgentTaskRecord.tenant_id == tenant_id,
                    AgentTaskRecord.root_run_id == root_run_id,
                )
                .order_by(AgentTaskRecord.sequence_no)
            )
        )

    def list_dependencies(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> list[AgentTaskDependency]:
        self._prepare()
        return list(
            self._session.scalars(
                select(AgentTaskDependency)
                .where(
                    AgentTaskDependency.tenant_id == tenant_id,
                    AgentTaskDependency.root_run_id == root_run_id,
                )
                .order_by(
                    AgentTaskDependency.task_id,
                    AgentTaskDependency.depends_on_task_id,
                )
            )
        )

    def find_task(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
        task_id: str,
        for_update: bool = False,
    ) -> AgentTaskRecord | None:
        self._prepare()
        statement = select(AgentTaskRecord).where(
            AgentTaskRecord.tenant_id == tenant_id,
            AgentTaskRecord.root_run_id == root_run_id,
            AgentTaskRecord.task_id == task_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def latest_checkpoint(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        root_run_id: UUID,
    ) -> AgentCheckpoint | None:
        self._prepare()
        return self._session.scalar(
            select(AgentCheckpoint)
            .where(
                AgentCheckpoint.tenant_id == tenant_id,
                AgentCheckpoint.user_id == user_id,
                AgentCheckpoint.thread_id == thread_id,
                AgentCheckpoint.root_run_id == root_run_id,
            )
            .order_by(AgentCheckpoint.checkpoint_version.desc())
            .limit(1)
        )

    def add_checkpoint(self, row: AgentCheckpoint) -> AgentCheckpoint:
        self._prepare()
        self._session.add(row)
        self._session.flush()
        return row

    def find_checkpoint_by_request_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        request_id: UUID,
    ) -> AgentCheckpoint | None:
        """Find the newest checkpoint that already accepted one request ID."""

        self._prepare()
        return self._session.scalar(
            select(AgentCheckpoint)
            .join(
                AgentRun,
                (AgentRun.tenant_id == AgentCheckpoint.tenant_id)
                & (AgentRun.id == AgentCheckpoint.root_run_id),
            )
            .where(
                AgentCheckpoint.tenant_id == tenant_id,
                AgentCheckpoint.user_id == user_id,
                AgentCheckpoint.thread_id == thread_id,
                AgentRun.user_id == user_id,
                AgentRun.run_kind == "supervisor",
                AgentCheckpoint.state_json["active_request_id"].as_string()
                == str(request_id),
            )
            .order_by(
                AgentCheckpoint.created_at.desc(),
                AgentCheckpoint.checkpoint_version.desc(),
            )
            .limit(1)
        )

    def find_latest_owned_waiting_root(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
        for_update: bool = False,
    ) -> AgentRun | None:
        self._prepare()
        statement = (
            select(AgentRun)
            .where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.user_id == user_id,
                AgentRun.thread_id == thread_id,
                AgentRun.run_kind == "supervisor",
                AgentRun.status == "waiting_user",
            )
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def find_owned_active_root(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        thread_id: UUID,
    ) -> AgentRun | None:
        self._prepare()
        return self._session.scalar(
            select(AgentRun)
            .where(
                AgentRun.tenant_id == tenant_id,
                AgentRun.user_id == user_id,
                AgentRun.thread_id == thread_id,
                AgentRun.run_kind == "supervisor",
                AgentRun.status.in_(("running", "waiting_user")),
            )
            .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
            .limit(1)
        )

    def count_worker_runs(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> int:
        self._prepare()
        return int(
            self._session.scalar(
                select(func.count(AgentRun.id)).where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.root_run_id == root_run_id,
                    AgentRun.run_kind == "worker",
                )
            )
            or 0
        )

    def list_tool_calls(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> list[ToolCall]:
        self._prepare()
        return list(
            self._session.scalars(
                select(ToolCall)
                .join(AgentRun, AgentRun.id == ToolCall.agent_run_id)
                .where(
                    ToolCall.tenant_id == tenant_id,
                    AgentRun.root_run_id == root_run_id,
                )
                .order_by(ToolCall.started_at, ToolCall.id)
            )
        )

    def delete_task_board(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> None:
        self._prepare()
        self._session.execute(
            delete(AgentTaskDependency).where(
                AgentTaskDependency.tenant_id == tenant_id,
                AgentTaskDependency.root_run_id == root_run_id,
            )
        )
        self._session.execute(
            delete(AgentTaskRecord).where(
                AgentTaskRecord.tenant_id == tenant_id,
                AgentTaskRecord.root_run_id == root_run_id,
            )
        )
        self._session.flush()

    def find_evidence_ids(
        self,
        *,
        tenant_id: UUID,
        evidence_ids: Iterable[UUID],
    ) -> set[UUID]:
        self._prepare()
        values = tuple(evidence_ids)
        if not values:
            return set()
        return set(
            self._session.scalars(
                select(Evidence.id).where(
                    Evidence.tenant_id == tenant_id,
                    Evidence.id.in_(values),
                )
            )
        )

    def list_answer_evidence(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> list[AgentAnswerEvidence]:
        self._prepare()
        return list(
            self._session.scalars(
                select(AgentAnswerEvidence)
                .where(
                    AgentAnswerEvidence.tenant_id == tenant_id,
                    AgentAnswerEvidence.root_run_id == root_run_id,
                )
                .order_by(AgentAnswerEvidence.citation_ordinal)
            )
        )

    def add_answer_evidence(
        self,
        rows: Sequence[AgentAnswerEvidence],
    ) -> None:
        self._prepare()
        self._session.add_all(rows)
        self._session.flush()

    def list_tool_names(
        self,
        *,
        tenant_id: UUID,
        root_run_id: UUID,
    ) -> list[str]:
        self._prepare()
        names = self._session.scalars(
            select(ToolCall.tool_name)
            .join(AgentRun, AgentRun.id == ToolCall.agent_run_id)
            .where(
                ToolCall.tenant_id == tenant_id,
                or_(
                    AgentRun.id == root_run_id,
                    AgentRun.root_run_id == root_run_id,
                ),
            )
            .order_by(ToolCall.started_at, ToolCall.id)
        )
        return list(dict.fromkeys(names))

    def flush(self) -> None:
        self._prepare()
        self._session.flush()

    def _prepare(self) -> None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
