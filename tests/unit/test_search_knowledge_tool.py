from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import uuid4

import pytest

from app.core.errors import (
    ApplicationError,
    ToolExecutionError,
)
from app.runtime.executor import ToolExecutionContext, ToolExecutionResult
from app.schemas.auth import CurrentUser
from app.schemas.knowledge import SearchKnowledgeInput, SearchKnowledgeResult
from app.services.evidence import EvidenceWriteContext
from app.services.knowledge import KnowledgeSearchOutcome, KnowledgeSearchService
from app.services.retrieval.errors import RetrievalEmbeddingProviderUnavailableError
from app.tools import SearchKnowledgeTool
from app.tools.contracts import InvalidToolBindingError
from app.tools.registry import create_m2_tool_registry
from tests.unit.test_search_knowledge_contracts import context_bundle


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="knowledge-tool@example.com",
        display_name="Knowledge Tool Reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


class FakeHarness:
    def __init__(
        self,
        user: CurrentUser,
        *,
        sanitize_unknown: bool = True,
    ) -> None:
        self.tenant_id = user.tenant_id
        self.trace_id = uuid4()
        self.definition = create_m2_tool_registry().get("search_knowledge")
        self.context = ToolExecutionContext(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            roles=tuple(user.roles),
            market_scopes=tuple(user.market_scopes),
            agent_run_id=uuid4(),
            tool_call_id=uuid4(),
            trace_id=self.trace_id,
        )
        self.sanitize_unknown = sanitize_unknown
        self.calls: list[tuple[str, object, object]] = []

    def get_tool_definition(self, name: str) -> object:
        assert name == "search_knowledge"
        return self.definition

    def execute_tool(
        self,
        name: str,
        arguments: object,
        *,
        target_tenant_id: object,
        operation: object,
    ) -> ToolExecutionResult[object]:
        self.calls.append((name, arguments, target_tenant_id))
        try:
            result = operation(self.context)  # type: ignore[operator]
        except ApplicationError:
            raise
        except Exception:
            if self.sanitize_unknown:
                raise ToolExecutionError from None
            raise
        return ToolExecutionResult(data=result, context=self.context)


class FakeKnowledgeService:
    def __init__(
        self,
        outcome: object,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.outcome = outcome
        self.failure = failure
        self.calls: list[tuple[CurrentUser, SearchKnowledgeInput, object]] = []

    def search(
        self,
        current_user: CurrentUser,
        request: SearchKnowledgeInput,
        *,
        runtime_context: EvidenceWriteContext | None = None,
    ) -> KnowledgeSearchOutcome:
        self.calls.append((current_user, request, runtime_context))
        if self.failure is not None:
            raise self.failure
        return cast(KnowledgeSearchOutcome, self.outcome)


def _tool(
    harness: FakeHarness,
    service: FakeKnowledgeService,
    user: CurrentUser,
) -> SearchKnowledgeTool:
    return SearchKnowledgeTool(
        cast(object, harness),
        cast(KnowledgeSearchService, service),
        user,
    )


def test_search_knowledge_tool_binds_exact_m2_registry_contract() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeKnowledgeService(
        KnowledgeSearchOutcome(
            result=SearchKnowledgeResult(context=context_bundle(0)),
            reused=False,
        )
    )

    tool = _tool(harness, service, user)

    assert tool.name == "search_knowledge"
    harness.definition = replace(
        harness.definition,
        output_schema=SearchKnowledgeInput,
    )
    with pytest.raises(InvalidToolBindingError):
        _tool(harness, service, user)


def test_success_envelope_uses_context_evidence_order_and_trusted_audit_ids() -> None:
    user = _user()
    harness = FakeHarness(user)
    result = SearchKnowledgeResult(context=context_bundle(3))
    service = FakeKnowledgeService(KnowledgeSearchOutcome(result=result, reused=False))
    request = SearchKnowledgeInput(query="合成说明书中的额定电压是多少？")

    envelope = _tool(harness, service, user).invoke(request)

    assert envelope.status == "success"
    assert envelope.data == result
    assert envelope.evidence_ids == list(result.evidence_ids)
    assert envelope.meta.tool == "search_knowledge"
    assert envelope.meta.version == "1.0.0"
    assert envelope.meta.trace_id == harness.trace_id
    assert harness.calls == [("search_knowledge", request, user.tenant_id)]
    assert len(service.calls) == 1
    called_user, called_request, runtime_context = service.calls[0]
    assert called_user is user
    assert called_request is request
    assert runtime_context == EvidenceWriteContext(
        tenant_id=harness.context.tenant_id,
        agent_run_id=harness.context.agent_run_id,
        tool_call_id=harness.context.tool_call_id,
    )


def test_unsupported_knowledge_is_an_ordinary_success_without_evidence() -> None:
    user = _user()
    harness = FakeHarness(user)
    result = SearchKnowledgeResult(context=context_bundle(0))
    service = FakeKnowledgeService(KnowledgeSearchOutcome(result=result, reused=False))

    envelope = _tool(harness, service, user).invoke(
        SearchKnowledgeInput(query="没有资料支持的问题")
    )

    assert envelope.status == "success"
    assert envelope.data is not None
    assert envelope.data.context.supported is False
    assert envelope.data.context.segments == []
    assert envelope.evidence_ids == []
    assert envelope.error is None


def test_known_service_error_becomes_safe_error_envelope() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeKnowledgeService(
        object(),
        failure=RetrievalEmbeddingProviderUnavailableError(),
    )

    envelope = _tool(harness, service, user).invoke(
        SearchKnowledgeInput(query="Provider故障")
    )

    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert envelope.error is not None
    assert envelope.error.code == "PROVIDER_ERROR"


@pytest.mark.parametrize("mismatch", ("user", "tenant", "roles", "markets"))
def test_bound_current_user_must_exactly_match_harness_identity(mismatch: str) -> None:
    trusted = _user()
    bound = trusted.model_copy(deep=True)
    if mismatch == "user":
        bound.user_id = uuid4()
    elif mismatch == "tenant":
        bound.tenant_id = uuid4()
    elif mismatch == "roles":
        bound.roles = ["company_owner"]
    else:
        bound.market_scopes = ["FR"]
    harness = FakeHarness(trusted)
    service = FakeKnowledgeService(
        KnowledgeSearchOutcome(
            result=SearchKnowledgeResult(context=context_bundle(0)),
            reused=False,
        )
    )

    envelope = _tool(harness, service, bound).invoke(
        SearchKnowledgeInput(query="身份不应被替换")
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert envelope.evidence_ids == []
    assert service.calls == []


class MisalignedOutcome(KnowledgeSearchOutcome):
    @property
    def evidence_ids(self) -> tuple[object, ...]:
        return (uuid4(),)


def test_misaligned_service_evidence_mapping_is_sanitized() -> None:
    user = _user()
    harness = FakeHarness(user)
    result = SearchKnowledgeResult(context=context_bundle(2))
    service = FakeKnowledgeService(MisalignedOutcome(result=result, reused=False))

    envelope = _tool(harness, service, user).invoke(
        SearchKnowledgeInput(query="错误Evidence映射")
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    assert envelope.evidence_ids == []


def test_unknown_service_failure_is_sanitized_without_private_details() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeKnowledgeService(
        object(),
        failure=RuntimeError("password=secret SQL=DROP TABLE document_chunks"),
    )

    envelope = _tool(harness, service, user).invoke(
        SearchKnowledgeInput(query="未知异常")
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    serialized = envelope.model_dump_json()
    assert "secret" not in serialized
    assert "DROP TABLE" not in serialized
    assert envelope.evidence_ids == []
