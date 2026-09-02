from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import uuid4

import pytest

from app.core.errors import ApplicationError, EvidenceNotFoundError, ToolExecutionError
from app.runtime.executor import (
    HarnessExecutor,
    ToolExecutionContext,
    ToolExecutionResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.evidence import GetEvidenceDetailInput, GetEvidenceDetailResult
from app.services.evidence import EvidenceQueryService
from app.tools import GetEvidenceDetailTool
from app.tools.contracts import InvalidToolBindingError
from app.tools.registry import create_m2_tool_registry
from tests.unit.test_file_evidence_tool_contracts import document_evidence_detail


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="evidence-tool@example.com",
        display_name="Evidence Tool Reader",
        roles=["product_scout"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


class FakeHarness:
    def __init__(self, user: CurrentUser) -> None:
        self.tenant_id = user.tenant_id
        self.trace_id = uuid4()
        self.definition = create_m2_tool_registry().get("get_evidence_detail")
        self.context = ToolExecutionContext(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            roles=tuple(user.roles),
            market_scopes=tuple(user.market_scopes),
            agent_run_id=uuid4(),
            tool_call_id=uuid4(),
            trace_id=self.trace_id,
        )
        self.calls: list[tuple[str, object, object]] = []

    def get_tool_definition(self, name: str) -> object:
        assert name == "get_evidence_detail"
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
        except Exception:  # noqa: BLE001 - Fake preserves the Harness trust boundary
            raise ToolExecutionError from None
        return ToolExecutionResult(data=result, context=self.context)


class FakeEvidenceQueryService:
    def __init__(self, result: object, *, failure: Exception | None = None) -> None:
        self.result = result
        self.failure = failure
        self.calls: list[tuple[CurrentUser, GetEvidenceDetailInput]] = []

    def get_tool_detail(
        self,
        current_user: CurrentUser,
        request: GetEvidenceDetailInput,
    ) -> GetEvidenceDetailResult:
        self.calls.append((current_user, request))
        if self.failure is not None:
            raise self.failure
        return cast(GetEvidenceDetailResult, self.result)


def _tool(
    harness: FakeHarness,
    service: FakeEvidenceQueryService,
    user: CurrentUser,
) -> GetEvidenceDetailTool:
    return GetEvidenceDetailTool(
        cast(HarnessExecutor, harness),
        cast(EvidenceQueryService, service),
        user,
    )


def test_get_evidence_detail_tool_binds_exact_m2_registry_contract() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeEvidenceQueryService(object())

    tool = _tool(harness, service, user)

    assert tool.name == "get_evidence_detail"
    harness.definition = replace(
        harness.definition,
        output_schema=GetEvidenceDetailInput,
    )
    with pytest.raises(InvalidToolBindingError):
        _tool(harness, service, user)


def test_success_uses_trusted_identity_and_returns_only_verified_evidence_id() -> None:
    user = _user()
    harness = FakeHarness(user)
    detail = document_evidence_detail()
    request = GetEvidenceDetailInput(evidence_id=detail.id)
    result = GetEvidenceDetailResult(detail=detail)
    service = FakeEvidenceQueryService(result)

    envelope = _tool(harness, service, user).invoke(request)

    assert envelope.status == "success"
    assert envelope.data == result
    assert envelope.evidence_ids == [request.evidence_id]
    assert envelope.error is None
    assert envelope.meta.tool == "get_evidence_detail"
    assert envelope.meta.version == "1.0.0"
    assert envelope.meta.trace_id == harness.trace_id
    assert harness.calls == [("get_evidence_detail", request, user.tenant_id)]
    assert service.calls == [(user, request)]


def test_known_evidence_error_becomes_safe_error_envelope() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeEvidenceQueryService(object(), failure=EvidenceNotFoundError())

    envelope = _tool(harness, service, user).invoke(
        GetEvidenceDetailInput(evidence_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert envelope.error is not None
    assert envelope.error.code == "EVIDENCE_NOT_FOUND"
    assert envelope.error.field == "evidence_id"


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
    service = FakeEvidenceQueryService(object())

    envelope = _tool(harness, service, bound).invoke(
        GetEvidenceDetailInput(evidence_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert envelope.evidence_ids == []
    assert service.calls == []


def test_invalid_service_result_is_sanitized() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeEvidenceQueryService(object())

    envelope = _tool(harness, service, user).invoke(
        GetEvidenceDetailInput(evidence_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    assert envelope.evidence_ids == []


def test_service_result_must_match_requested_public_evidence_id() -> None:
    user = _user()
    harness = FakeHarness(user)
    request = GetEvidenceDetailInput(evidence_id=uuid4())
    service = FakeEvidenceQueryService(
        GetEvidenceDetailResult(detail=document_evidence_detail())
    )

    envelope = _tool(harness, service, user).invoke(request)

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    assert envelope.evidence_ids == []


def test_unknown_service_failure_does_not_leak_private_details() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeEvidenceQueryService(
        object(),
        failure=RuntimeError(
            "tenant/private/evidence/secret.json SQL=DROP TABLE evidences"
        ),
    )

    envelope = _tool(harness, service, user).invoke(
        GetEvidenceDetailInput(evidence_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    serialized = envelope.model_dump_json()
    assert "secret.json" not in serialized
    assert "DROP TABLE" not in serialized
    assert envelope.evidence_ids == []
