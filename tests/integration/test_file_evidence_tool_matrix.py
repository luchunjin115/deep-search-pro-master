from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models.runtime import Evidence
from app.repositories.evidence import AuthorizedDocumentEvidence
from app.repositories.files import ReadableParsedFile
from app.schemas.auth import CurrentUser
from app.schemas.files import ReadUploadedFileInput
from app.services.evidence import EvidenceQueryService, EvidenceReader
from app.services.file_reading import FileReadingService, ParsedFileReader
from tests.integration.m2_20_matrix_support import M2FileEvidenceToolMatrix
from tests.integration.test_agent_tools import AgentToolFixture

pytest_plugins = ("tests.integration.test_agent_tools",)


@pytest.mark.parametrize(
    ("role", "access_mode"),
    (
        ("product_scout", "owner"),
        ("company_owner", "company_owner"),
        ("amazon_operator", "user"),
        ("amazon_operator", "role"),
        ("product_scout", "market"),
    ),
)
def test_both_tools_complete_real_harness_service_repository_chain_for_roles_and_acl(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
    role: str,
    access_mode: str,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role=role,  # type: ignore[arg-type]
        access_mode=access_mode,  # type: ignore[arg-type]
    )

    result = matrix.run_both()

    assert result.file_envelope is not None
    assert result.file_envelope.status == "success", result.file_envelope.model_dump()
    assert result.file_envelope.evidence_ids == []
    assert result.evidence_envelope is not None
    assert result.evidence_envelope.status == "success", (
        result.evidence_envelope.model_dump()
    )
    assert result.evidence_envelope.evidence_ids == [matrix.evidence_id]
    assert [
        (call.tool_name, call.permission_result, call.status)
        for call in matrix.calls(result.run_id)
    ] == [
        ("read_uploaded_file", "allowed", "success"),
        ("get_evidence_detail", "allowed", "success"),
    ]


def test_acl_revocation_after_evidence_creation_hides_both_real_tool_reads(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="amazon_operator",
        access_mode="user",
    )
    matrix.mutate("acl_revoked")

    result = matrix.run_both()

    assert result.file_envelope is not None
    assert result.file_envelope.status == "error"
    assert result.file_envelope.error is not None
    assert result.file_envelope.error.code == "FILE_NOT_FOUND"
    assert result.evidence_envelope is not None
    assert result.evidence_envelope.status == "error"
    assert result.evidence_envelope.error is not None
    assert result.evidence_envelope.error.code == "EVIDENCE_NOT_FOUND"
    assert [call.status for call in matrix.calls(result.run_id)] == ["error", "error"]


@pytest.mark.parametrize(
    ("invalid_state", "expected_file_status"),
    (
        ("document_deleted", "error"),
        ("file_deleted", "error"),
        ("version_inactive", "success"),
        ("index_inactive", "success"),
    ),
)
def test_current_resource_state_is_rechecked_with_file_and_evidence_semantics(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
    invalid_state: str,
    expected_file_status: str,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="company_owner",
        access_mode="company_owner",
    )
    matrix.mutate(invalid_state)  # type: ignore[arg-type]

    result = matrix.run_both()

    assert result.file_envelope is not None
    assert result.file_envelope.status == expected_file_status
    if expected_file_status == "error":
        assert result.file_envelope.error is not None
        assert result.file_envelope.error.code == "FILE_NOT_FOUND"
    assert result.evidence_envelope is not None
    assert result.evidence_envelope.status == "error"
    assert result.evidence_envelope.error is not None
    assert result.evidence_envelope.error.code == "EVIDENCE_NOT_FOUND"


@pytest.mark.parametrize("parse_status", ("pending", "failed"))
def test_unready_or_failed_parse_is_a_safe_file_state_error_through_real_tool(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
    parse_status: str,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="product_scout",
        access_mode="owner",
    )
    matrix.set_parse_status(parse_status)  # type: ignore[arg-type]

    result = matrix.run_file()

    assert result.file_envelope is not None
    assert result.file_envelope.status == "error"
    assert result.file_envelope.error is not None
    assert result.file_envelope.error.code == "FILE_STATE_CONFLICT"
    assert result.file_envelope.evidence_ids == []
    assert [(call.status, call.error_code) for call in matrix.calls(result.run_id)] == [
        ("error", "FILE_STATE_CONFLICT")
    ]


def test_out_of_range_locator_is_safe_and_does_not_expose_storage(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="product_scout",
        access_mode="owner",
    )

    result = matrix.run_file(
        ReadUploadedFileInput(
            file_id=matrix.file_row.id,
            locator={"source_type": "pdf", "page_start": 999},
        )
    )

    assert result.file_envelope is not None
    assert result.file_envelope.status == "error"
    assert result.file_envelope.error is not None
    assert result.file_envelope.error.code == "VALIDATION_ERROR"
    assert result.file_envelope.error.field == "locator"
    assert matrix.parsed_storage_key not in result.file_envelope.model_dump_json()


@pytest.mark.parametrize("artifact_state", ("missing", "corrupt"))
def test_storage_and_artifact_failures_are_sanitized_through_real_tool_and_trace(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
    artifact_state: str,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="amazon_operator",
        access_mode="role",
    )
    if artifact_state == "missing":
        matrix.remove_parsed_artifact()
    else:
        matrix.corrupt_parsed_artifact()

    result = matrix.run_file()

    assert result.file_envelope is not None
    assert result.file_envelope.status == "error"
    assert result.file_envelope.error is not None
    assert result.file_envelope.error.code == "INTERNAL_ERROR"
    serialized = result.file_envelope.model_dump_json()
    assert matrix.parsed_storage_key not in serialized
    assert "D:/secret" not in serialized
    assert "DROP TABLE" not in serialized
    calls = matrix.calls(result.run_id)
    assert [(call.status, call.error_code) for call in calls] == [
        ("error", "INTERNAL_ERROR")
    ]
    assert matrix.parsed_storage_key not in (calls[0].error_message or "")


def test_changed_context_requester_hides_evidence_through_real_tool(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="company_owner",
        access_mode="company_owner",
    )
    matrix.mutate("context_requester_changed")

    result = matrix.run_evidence()

    assert result.evidence_envelope is not None
    assert result.evidence_envelope.status == "error"
    assert result.evidence_envelope.error is not None
    assert result.evidence_envelope.error.code == "EVIDENCE_NOT_FOUND"
    assert result.evidence_envelope.evidence_ids == []
    assert [(call.status, call.error_code) for call in matrix.calls(result.run_id)] == [
        ("error", "EVIDENCE_NOT_FOUND")
    ]


def test_file_repository_database_failure_is_sanitized_by_service_tool_and_trace(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    class BrokenFileReader:
        def find_readable_parsed_file(self, **_kwargs: object) -> ReadableParsedFile:
            raise SQLAlchemyError("password=private SQL=SELECT * FROM files")

    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="product_scout",
        access_mode="owner",
    )
    service = FileReadingService(
        cast(ParsedFileReader, BrokenFileReader()),
        matrix.storage,
        maximum_artifact_bytes=matrix.fixture.settings.file_read_max_artifact_bytes,
    )

    result = matrix.run_file(service=service)

    assert result.file_envelope is not None
    assert result.file_envelope.status == "error"
    assert result.file_envelope.error is not None
    assert result.file_envelope.error.code == "INTERNAL_ERROR"
    serialized = result.file_envelope.model_dump_json()
    assert "private" not in serialized
    assert "SELECT" not in serialized
    calls = matrix.calls(result.run_id)
    assert [(call.status, call.error_code) for call in calls] == [
        ("error", "INTERNAL_ERROR")
    ]
    assert "private" not in (calls[0].error_message or "")


def test_evidence_database_failure_is_sanitized_by_service_tool_and_trace(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    class BrokenEvidenceReader:
        def find_by_id(
            self,
            *,
            tenant_id: UUID,
            evidence_id: UUID,
        ) -> Evidence | None:
            del tenant_id, evidence_id
            raise SQLAlchemyError("password=private SQL=SELECT * FROM evidences")

        def find_authorized_document_by_id(
            self,
            current_user: CurrentUser,
            evidence_id: UUID,
        ) -> AuthorizedDocumentEvidence | None:
            del current_user, evidence_id
            raise SQLAlchemyError("D:/private/evidence.json")

    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="company_owner",
        access_mode="company_owner",
    )
    service = EvidenceQueryService(cast(EvidenceReader, BrokenEvidenceReader()))

    result = matrix.run_evidence(service=service)

    assert result.evidence_envelope is not None
    assert result.evidence_envelope.status == "error"
    assert result.evidence_envelope.error is not None
    assert result.evidence_envelope.error.code == "INTERNAL_ERROR"
    serialized = result.evidence_envelope.model_dump_json()
    assert "private" not in serialized
    assert "SELECT" not in serialized
    calls = matrix.calls(result.run_id)
    assert [(call.status, call.error_code) for call in calls] == [
        ("error", "INTERNAL_ERROR")
    ]
    assert "private" not in (calls[0].error_message or "")
