from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.errors import _status_for_error
from app.core.errors import (
    ApplicationError,
    DocumentAclConflictError,
    DocumentNotFoundError,
    DocumentStateConflictError,
    DocumentVersionConflictError,
    FileNotFoundError,
    FileStateConflictError,
)
from app.schemas.common import ErrorCode
from app.schemas.files import (
    FileRegistrationInput,
    FileResponse,
    FileStateUpdate,
    FileUploadResponse,
)
from app.schemas.knowledge import (
    DocumentAclGrantInput,
    DocumentCreateInput,
    DocumentDetailResponse,
    DocumentIndexStateUpdate,
    DocumentParseStateUpdate,
    DocumentVersionCreateInput,
)

NOW = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "forbidden_field",
    ["tenant_id", "owner_user_id", "path", "storage_key", "sql"],
)
def test_file_registration_rejects_trusted_or_unsafe_fields(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError, match=forbidden_field):
        FileRegistrationInput(
            original_name="synthetic-manual.pdf",
            extension=".pdf",
            **{forbidden_field: "must-not-enter"},
        )


def test_file_registration_requires_base_name_and_matching_extension() -> None:
    valid = FileRegistrationInput(
        original_name="合成产品说明书.PDF",
        extension=".pdf",
    )
    assert valid.category == "uploads"

    with pytest.raises(ValidationError):
        FileRegistrationInput(original_name="../secret.pdf", extension=".pdf")
    with pytest.raises(ValidationError):
        FileRegistrationInput(original_name="manual.csv", extension=".pdf")
    normalized = FileRegistrationInput(
        original_name=" manual.pdf ",
        extension=".pdf",
    )
    assert normalized.original_name == "manual.pdf"
    with pytest.raises(ValidationError):
        FileRegistrationInput(original_name="manual\n.pdf", extension=".pdf")


def test_file_state_update_requires_coherent_safe_error() -> None:
    failed = FileStateUpdate(status="failed", error_message="解析失败，请重试")
    assert failed.error_message == "解析失败，请重试"

    with pytest.raises(ValidationError):
        FileStateUpdate(status="failed")
    with pytest.raises(ValidationError):
        FileStateUpdate(status="ready", error_message="should not remain")
    with pytest.raises(ValidationError):
        FileStateUpdate(status="failed", error_message="x\nsecret")


@pytest.mark.parametrize("forbidden_field", ["tenant_id", "path", "storage_key", "sql"])
def test_document_inputs_reject_context_path_and_sql_fields(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError, match=forbidden_field):
        DocumentCreateInput(
            file_id=uuid4(),
            title="合成产品说明书",
            document_type="product_manual",
            **{forbidden_field: "must-not-enter"},
        )

    with pytest.raises(ValidationError, match=forbidden_field):
        DocumentVersionCreateInput(
            file_id=uuid4(),
            **{forbidden_field: "must-not-enter"},
        )


def test_acl_grant_requires_exactly_one_matching_subject() -> None:
    assert (
        DocumentAclGrantInput(
            subject_type="role",
            role_name="product_scout",
        ).role_name
        == "product_scout"
    )
    assert (
        DocumentAclGrantInput(
            subject_type="user",
            user_id=uuid4(),
        ).user_id
        is not None
    )
    assert (
        DocumentAclGrantInput(subject_type="market", market_code="DE").market_code
        == "DE"
    )

    with pytest.raises(ValidationError):
        DocumentAclGrantInput(subject_type="user", market_code="DE")
    with pytest.raises(ValidationError):
        DocumentAclGrantInput(
            subject_type="role",
            role_name="product_scout",
            user_id=uuid4(),
        )


def test_parse_and_index_commands_freeze_ready_artifact_boundary() -> None:
    with pytest.raises(ValidationError):
        DocumentParseStateUpdate(status="ready")
    with pytest.raises(ValidationError):
        DocumentParseStateUpdate(
            status="parsing",
            parser_name="pdf",
            parser_version="1.0.0",
            parsed_storage_key="not-yet-allowed",
        )

    assert DocumentParseStateUpdate(status="parsing").status == "parsing"
    assert DocumentIndexStateUpdate(status="indexing").status == "indexing"


def test_public_responses_have_no_internal_storage_or_tenant_fields() -> None:
    file_response = FileResponse(
        file_id=uuid4(),
        owner_user_id=uuid4(),
        original_name="synthetic.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        size_bytes=128,
        sha256="a" * 64,
        category="uploads",
        status="uploaded",
        created_at=NOW,
    )
    document_response = DocumentDetailResponse(
        document_id=uuid4(),
        owner_user_id=uuid4(),
        title="合成产品说明书",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        access_level="private",
        created_at=NOW,
        versions=[],
        acl=[],
    )

    for payload in (file_response.model_dump(), document_response.model_dump()):
        assert "tenant_id" not in payload
        assert "storage_key" not in payload
        assert "path" not in payload
        assert "sql" not in payload


def test_every_m2_06_public_schema_forbids_unknown_fields() -> None:
    public_models = [
        FileRegistrationInput,
        FileResponse,
        FileStateUpdate,
        FileUploadResponse,
        DocumentCreateInput,
        DocumentVersionCreateInput,
        DocumentAclGrantInput,
        DocumentDetailResponse,
    ]
    for model in public_models:
        assert model.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_status"),
    [
        (FileNotFoundError(), "FILE_NOT_FOUND", 404),
        (DocumentNotFoundError(), "DOCUMENT_NOT_FOUND", 404),
        (FileStateConflictError(), "FILE_STATE_CONFLICT", 409),
        (DocumentStateConflictError(), "DOCUMENT_STATE_CONFLICT", 409),
        (DocumentVersionConflictError(), "DOCUMENT_VERSION_CONFLICT", 409),
        (DocumentAclConflictError(), "DOCUMENT_ACL_CONFLICT", 409),
    ],
)
def test_m2_05_errors_have_stable_public_codes_and_http_statuses(
    error: ApplicationError,
    expected_code: ErrorCode,
    expected_status: int,
) -> None:
    assert error.to_detail().code == expected_code
    assert _status_for_error(error) == expected_status
