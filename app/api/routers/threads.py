"""Owned thread creation and the unique synchronous Agent Gateway route."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies import (
    AgentGatewayDependency,
    ConversationServiceDependency,
    CurrentUserDependency,
    EvidenceQueryServiceDependency,
)
from app.schemas.chat import (
    ChatMessageRequest,
    ChatSuccessResponse,
    CreateThreadRequest,
    ExecutionSummary,
    ThreadResponse,
)
from app.schemas.common import ApiErrorResponse

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
    gateway: AgentGatewayDependency,
) -> ChatSuccessResponse:
    """Run only the Agent Gateway and commit its safe answer in one response."""

    conversations.require_owned_active_thread(user, thread_id)
    result = await gateway.run(
        user,
        thread_id=thread_id,
        request_id=request.request_id,
        message=request.message,
    )

    conversations.add_message_once(
        user,
        thread_id,
        message_id=result.user_message_id,
        role="user",
        content=request.message,
    )
    assistant_message = conversations.add_message_once(
        user,
        thread_id,
        message_id=result.assistant_message_id,
        role="assistant",
        content=result.answer,
    )
    evidence_summaries = evidence.get_agent_summaries(user, result.evidence_ids)
    return ChatSuccessResponse(
        status=result.status,
        request_id=request.request_id,
        thread_id=thread_id,
        message_id=assistant_message.id,
        answer=result.answer,
        evidence=evidence_summaries,
        execution=ExecutionSummary(
            trace_id=result.trace_id,
            route="agent_gateway",
            tool_names=result.tool_names,
            duration_ms=result.duration_ms,
            status=result.status,
            business_outcome=result.business_outcome,
        ),
    )
