"""Owned thread creation and synchronous M1 chat execution routes."""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, status

from app.agents.graphs.inventory_query import InventoryQueryAgent
from app.agents.state import InventoryQueryInput
from app.api.dependencies import (
    AppSettings,
    ConversationServiceDependency,
    CurrentUserDependency,
    DatabaseRuntimeDependency,
    DatabaseSession,
    EvidenceQueryServiceDependency,
    ModelProviderDependency,
)
from app.core.errors import AgentTerminalError
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.context import build_run_context
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import TraceRecorder
from app.schemas.chat import (
    ChatMessageRequest,
    ChatSuccessResponse,
    CreateThreadRequest,
    ExecutionSummary,
    ThreadResponse,
)
from app.schemas.common import ApiErrorResponse
from app.services.evidence import EvidenceService
from app.services.inventory import InventoryService
from app.services.product import ProductSpecService
from app.tools.registry import create_m1_tool_registry

router = APIRouter(prefix="/threads", tags=["threads"])


@router.post(
    "",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ApiErrorResponse}, 422: {"model": ApiErrorResponse}},
)
async def create_thread(
    request: CreateThreadRequest,
    user: CurrentUserDependency,
    conversations: ConversationServiceDependency,
) -> ThreadResponse:
    """Create one active chat thread owned by the authenticated user."""

    return conversations.create_thread(user, request.title)


@router.post(
    "/{thread_id}/messages",
    response_model=ChatSuccessResponse,
    responses={
        401: {"model": ApiErrorResponse},
        403: {"model": ApiErrorResponse},
        404: {"model": ApiErrorResponse},
        422: {"model": ApiErrorResponse},
        429: {"model": ApiErrorResponse},
        503: {"model": ApiErrorResponse},
        504: {"model": ApiErrorResponse},
    },
)
async def send_message(
    thread_id: UUID,
    request: ChatMessageRequest,
    user: CurrentUserDependency,
    conversations: ConversationServiceDependency,
    evidence: EvidenceQueryServiceDependency,
    provider: ModelProviderDependency,
    session: DatabaseSession,
    settings: AppSettings,
    runtime: DatabaseRuntimeDependency,
) -> ChatSuccessResponse:
    """Run the bounded graph and return its committed answer in one HTTP response."""

    conversations.require_owned_active_thread(user, thread_id)
    conversations.add_message(
        user,
        thread_id,
        role="user",
        content=request.message,
    )

    context = build_run_context(user, thread_id)
    registry = create_m1_tool_registry()
    agent = InventoryQueryAgent(
        context=context,
        provider=provider,
        budget=ExecutionBudget(BudgetLimits.from_settings(settings)),
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=TraceRecorder(runtime.session_factory),
        product_service=ProductSpecService(
            ProductRepository(session, settings.database_statement_timeout_ms)
        ),
        inventory_service=InventoryService(
            InventoryRepository(session, settings.database_statement_timeout_ms),
            EvidenceService(session),
        ),
        business_session=session,
    )
    result = await agent.run(InventoryQueryInput(question=request.message))
    if result.status != "completed":
        assert result.error is not None
        raise AgentTerminalError(
            result.error,
            terminal_status=cast(
                Literal["failed", "denied", "timed_out"],
                result.status,
            ),
            trace_id=result.trace_id,
        )

    assistant_message = conversations.add_message(
        user,
        thread_id,
        role="assistant",
        content=result.answer,
    )
    evidence_summaries = evidence.get_summaries(user, result.evidence_ids)
    return ChatSuccessResponse(
        thread_id=thread_id,
        message_id=assistant_message.id,
        answer=result.answer,
        evidence=evidence_summaries,
        execution=ExecutionSummary(
            trace_id=result.trace_id,
            route=result.route,
            tool_names=result.tool_names,
            duration_ms=result.duration_ms,
            status=result.status,
        ),
    )
