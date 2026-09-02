from __future__ import annotations

from dataclasses import replace
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.core.errors import ApplicationError, FileReadLocatorError, ToolExecutionError
from app.runtime.executor import (
    HarnessExecutor,
    ToolExecutionContext,
    ToolExecutionResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.file_reading import ReadUploadedFileResult
from app.schemas.files import ReadUploadedFileInput
from app.services.file_reading import FileReadingService
from app.tools import ReadUploadedFileTool
from app.tools.contracts import InvalidToolBindingError
from app.tools.registry import create_m2_tool_registry


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="file-tool@example.com",
        display_name="File Tool Reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def _result(file_id: UUID | None = None) -> ReadUploadedFileResult:
    content = "合成说明书额定电压为 230V。"
    return ReadUploadedFileResult(
        file_id=file_id or uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        version_no=2,
        original_name="synthetic-manual.pdf",
        source_type="pdf",
        is_active_version=False,
        sections=[
            {
                "kind": "text",
                "locator": {"source_type": "pdf", "page_number": 2},
                "content": content,
                "truncated": False,
            }
        ],
        total_characters=len(content),
        truncated=False,
        synthetic_data=True,
    )


class FakeHarness:
    def __init__(self, user: CurrentUser) -> None:
        self.tenant_id = user.tenant_id
        self.trace_id = uuid4()
        self.definition = create_m2_tool_registry().get("read_uploaded_file")
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
        assert name == "read_uploaded_file"
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


class FakeFileReadingService:
    def __init__(self, result: object, *, failure: Exception | None = None) -> None:
        self.result = result
        self.failure = failure
        self.calls: list[tuple[CurrentUser, ReadUploadedFileInput]] = []

    def read_uploaded_file(
        self,
        current_user: CurrentUser,
        request: ReadUploadedFileInput,
    ) -> ReadUploadedFileResult:
        self.calls.append((current_user, request))
        if self.failure is not None:
            raise self.failure
        return cast(ReadUploadedFileResult, self.result)


def _tool(
    harness: FakeHarness,
    service: FakeFileReadingService,
    user: CurrentUser,
) -> ReadUploadedFileTool:
    return ReadUploadedFileTool(
        cast(HarnessExecutor, harness),
        cast(FileReadingService, service),
        user,
    )


def test_read_uploaded_file_tool_binds_exact_m2_registry_contract() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeFileReadingService(_result())

    tool = _tool(harness, service, user)

    assert tool.name == "read_uploaded_file"
    harness.definition = replace(
        harness.definition,
        output_schema=ReadUploadedFileInput,
    )
    with pytest.raises(InvalidToolBindingError):
        _tool(harness, service, user)


def test_success_uses_trusted_identity_and_never_invents_evidence() -> None:
    user = _user()
    harness = FakeHarness(user)
    request = ReadUploadedFileInput(file_id=uuid4())
    result = _result(request.file_id)
    service = FakeFileReadingService(result)

    envelope = _tool(harness, service, user).invoke(request)

    assert envelope.status == "success"
    assert envelope.data == result
    assert envelope.evidence_ids == []
    assert envelope.error is None
    assert envelope.meta.tool == "read_uploaded_file"
    assert envelope.meta.version == "1.0.0"
    assert envelope.meta.trace_id == harness.trace_id
    assert harness.calls == [("read_uploaded_file", request, user.tenant_id)]
    assert service.calls == [(user, request)]


def test_known_file_error_becomes_safe_error_envelope() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeFileReadingService(object(), failure=FileReadLocatorError())

    envelope = _tool(harness, service, user).invoke(
        ReadUploadedFileInput(file_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert envelope.error is not None
    assert envelope.error.code == "VALIDATION_ERROR"
    assert envelope.error.field == "locator"


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
    service = FakeFileReadingService(_result())

    envelope = _tool(harness, service, bound).invoke(
        ReadUploadedFileInput(file_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert envelope.evidence_ids == []
    assert service.calls == []


def test_invalid_service_result_is_sanitized() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeFileReadingService(object())

    envelope = _tool(harness, service, user).invoke(
        ReadUploadedFileInput(file_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    assert envelope.evidence_ids == []


def test_service_result_must_match_requested_public_file_id() -> None:
    user = _user()
    harness = FakeHarness(user)
    request = ReadUploadedFileInput(file_id=uuid4())
    service = FakeFileReadingService(_result())

    envelope = _tool(harness, service, user).invoke(request)

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    assert envelope.evidence_ids == []


def test_unknown_service_failure_does_not_leak_private_details() -> None:
    user = _user()
    harness = FakeHarness(user)
    service = FakeFileReadingService(
        object(),
        failure=RuntimeError(
            "tenant/private/parsed/secret.json SQL=DROP TABLE document_versions"
        ),
    )

    envelope = _tool(harness, service, user).invoke(
        ReadUploadedFileInput(file_id=uuid4())
    )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INTERNAL_ERROR"
    serialized = envelope.model_dump_json()
    assert "secret.json" not in serialized
    assert "DROP TABLE" not in serialized
    assert envelope.evidence_ids == []
