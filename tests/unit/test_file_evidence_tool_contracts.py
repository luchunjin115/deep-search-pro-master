from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    CsvFileReadLocator,
    DocxFileReadLocator,
    FileReadSection,
    GetEvidenceDetailInput,
    GetEvidenceDetailResult,
    PdfFileReadLocator,
    ReadUploadedFileInput,
    ReadUploadedFileResult,
    ToolDocumentEvidenceDetail,
    XlsxFileReadLocator,
)
from app.schemas.evidence import (
    GetEvidenceDetailInput as DirectGetEvidenceDetailInput,
)
from app.schemas.files import ReadUploadedFileInput as DirectReadUploadedFileInput
from app.schemas.retrieval import (
    PdfRetrievalSourceLocator,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
)
from app.tools import create_m2_tool_registry
from app.tools.registry import create_m1_tool_registry


def document_evidence_detail() -> ToolDocumentEvidenceDetail:
    now = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    return ToolDocumentEvidenceDetail(
        id=uuid4(),
        source_type="knowledge",
        title="合成蘑菇灯说明书",
        excerpt="本产品支持三档亮度调节。",
        observed_at=now,
        context_id=uuid4(),
        citation_label="[E1]",
        identity=RetrievalCandidateIdentity(
            document_id=uuid4(),
            version_id=uuid4(),
            index_set_id=uuid4(),
            chunk_id=uuid4(),
        ),
        document=RetrievalDocumentMetadata(
            title="合成蘑菇灯说明书",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        source_locator=PdfRetrievalSourceLocator(page_number=3),
        source_content_sha256="a" * 64,
        context_text_sha256="b" * 64,
        trust_level="document_snapshot",
        synthetic_data=True,
        created_at=now,
        file_id=uuid4(),
    )


def test_file_read_locators_are_strict_small_format_specific_windows() -> None:
    assert PdfFileReadLocator(page_start=3).page_end is None
    assert PdfFileReadLocator(page_start=3, page_end=5).page_end == 5
    with pytest.raises(ValidationError):
        PdfFileReadLocator(page_start=3, page_end=6)
    with pytest.raises(ValidationError):
        PdfFileReadLocator(page_start=3, page_end=2)

    assert DocxFileReadLocator(block_number=4).block_number == 4
    with pytest.raises(ValidationError):
        DocxFileReadLocator(block_number=4, table_number=1)
    with pytest.raises(ValidationError):
        DocxFileReadLocator()

    assert XlsxFileReadLocator(sheet_name="规格", cell_range="A1:T50").cell_range
    assert (
        XlsxFileReadLocator(
            sheet_name="规格",
            row_start=2,
            row_end=51,
        ).row_end
        == 51
    )
    for invalid in (
        {"sheet_name": "规格", "row_start": 1, "row_end": 51},
        {"sheet_name": "规格", "cell_range": "A1:U50"},
        {"sheet_name": "规格", "cell_range": "XFE1"},
        {
            "sheet_name": "规格",
            "cell_range": "A1",
            "row_start": 1,
            "row_end": 1,
        },
    ):
        with pytest.raises(ValidationError):
            XlsxFileReadLocator(**invalid)  # type: ignore[arg-type]

    assert CsvFileReadLocator(row_start=1, row_end=50).row_end == 50
    with pytest.raises(ValidationError):
        CsvFileReadLocator(row_start=1, row_end=51)


def test_read_uploaded_file_input_only_accepts_file_id_and_optional_locator() -> None:
    file_id = uuid4()
    request = ReadUploadedFileInput(
        file_id=file_id,
        locator={"source_type": "pdf", "page_start": 2, "page_end": 3},
    )

    assert request.file_id == file_id
    assert isinstance(request.locator, PdfFileReadLocator)
    assert DirectReadUploadedFileInput is ReadUploadedFileInput
    schema = ReadUploadedFileInput.model_json_schema()
    assert schema["required"] == ["file_id"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"file_id", "locator"}

    for forbidden in (
        "tenant_id",
        "user_id",
        "role",
        "market",
        "sql",
        "path",
        "storage_key",
        "document_id",
        "max_characters",
        "max_pages",
        "max_rows",
    ):
        with pytest.raises(ValidationError, match=forbidden):
            ReadUploadedFileInput(
                file_id=file_id,
                **{forbidden: "must-not-enter"},
            )


def test_read_uploaded_file_result_is_bounded_located_and_public_safe() -> None:
    content = "本产品支持三档亮度调节。"
    result = ReadUploadedFileResult(
        file_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        version_no=2,
        original_name="合成蘑菇灯说明书.pdf",
        source_type="pdf",
        is_active_version=False,
        sections=[
            FileReadSection(
                kind="text",
                locator=PdfRetrievalSourceLocator(page_number=3),
                content=content,
                truncated=False,
            )
        ],
        total_characters=len(content),
        truncated=False,
        synthetic_data=True,
    )

    assert result.total_characters == len(content)
    assert result.is_active_version is False
    assert set(result.model_dump()) == {
        "file_id",
        "document_id",
        "version_id",
        "version_no",
        "original_name",
        "source_type",
        "is_active_version",
        "sections",
        "total_characters",
        "truncated",
        "synthetic_data",
    }
    rendered = result.model_dump_json()
    for forbidden in (
        "tenant_id",
        "owner_user_id",
        "acl",
        "storage_key",
        "local_path",
        "sql",
    ):
        assert forbidden not in rendered

    with pytest.raises(ValidationError):
        ReadUploadedFileResult(
            **(result.model_dump() | {"total_characters": result.total_characters + 1})
        )
    with pytest.raises(ValidationError):
        ReadUploadedFileResult(
            **(
                result.model_dump()
                | {
                    "source_type": "csv",
                }
            )
        )
    with pytest.raises(ValidationError):
        FileReadSection(
            kind="text",
            locator=PdfRetrievalSourceLocator(page_number=3),
            content="x" * 8001,
            truncated=True,
        )


def test_get_evidence_detail_contract_accepts_only_id_and_adds_safe_file_hop() -> None:
    evidence_id = uuid4()
    request = GetEvidenceDetailInput(evidence_id=evidence_id)

    assert request.evidence_id == evidence_id
    assert DirectGetEvidenceDetailInput is GetEvidenceDetailInput
    assert set(request.model_dump()) == {"evidence_id"}
    with pytest.raises(ValidationError):
        GetEvidenceDetailInput(evidence_id=evidence_id, tenant_id=uuid4())

    detail = document_evidence_detail()
    result = GetEvidenceDetailResult(detail=detail)
    assert result.evidence_id == detail.id
    assert result.detail.file_id == detail.file_id
    rendered = result.model_dump_json()
    for forbidden in ("tenant_id", "owner_user_id", "acl", "storage_key", "sql"):
        assert forbidden not in rendered


def test_m2_registry_accumulates_exactly_five_tools_while_m1_stays_two() -> None:
    m1_registry = create_m1_tool_registry()
    m2_registry = create_m2_tool_registry()

    assert m1_registry.names == ("get_product_spec", "search_inventory")
    assert m2_registry.names == (
        "get_evidence_detail",
        "get_product_spec",
        "read_uploaded_file",
        "search_inventory",
        "search_knowledge",
    )

    file_reader = m2_registry.get("read_uploaded_file")
    assert file_reader.version == "1.0.0"
    assert file_reader.input_schema is ReadUploadedFileInput
    assert file_reader.output_schema is ReadUploadedFileResult
    assert file_reader.timeout_ms == 3_000
    assert file_reader.allowed_roles == frozenset(
        {"company_owner", "product_scout", "amazon_operator"}
    )
    assert file_reader.data_scope == "tenant"
    assert file_reader.side_effect == "read"

    evidence_reader = m2_registry.get("get_evidence_detail")
    assert evidence_reader.version == "1.0.0"
    assert evidence_reader.input_schema is GetEvidenceDetailInput
    assert evidence_reader.output_schema is GetEvidenceDetailResult
    assert evidence_reader.timeout_ms == 3_000
    assert evidence_reader.allowed_roles == file_reader.allowed_roles
    assert evidence_reader.data_scope == "tenant"
    assert evidence_reader.side_effect == "read"


def test_new_tool_descriptions_explain_use_return_limits_and_synthetic_data() -> None:
    registry = create_m2_tool_registry()
    file_description = registry.get("read_uploaded_file").description
    for phrase in (
        "上传文件",
        "解析产物",
        "返回",
        "有界",
        "只读",
        "合成演示数据",
        "不接受路径",
        "Storage Key",
        "tenant",
        "SQL",
        "读取预算",
    ):
        assert phrase in file_description

    evidence_description = registry.get("get_evidence_detail").description
    for phrase in (
        "Evidence",
        "当前权限",
        "返回",
        "数据库",
        "文档",
        "只读",
        "合成演示数据",
        "不接受",
        "tenant",
        "路径",
        "Storage Key",
    ):
        assert phrase in evidence_description

    specs = registry.model_specs(("read_uploaded_file", "get_evidence_detail"))
    assert [spec.name for spec in specs] == [
        "read_uploaded_file",
        "get_evidence_detail",
    ]
    assert set(specs[0].parameters["properties"]) == {"file_id", "locator"}
    assert set(specs[1].parameters["properties"]) == {"evidence_id"}


def test_m2_20_5_adds_both_execution_tools_but_not_agent_or_api() -> None:
    project_root = Path(__file__).parents[2]

    assert (project_root / "app/services/file_reading.py").is_file()
    evidence_service = (project_root / "app/services/evidence.py").read_text(
        encoding="utf-8"
    )
    assert "def get_tool_detail" in evidence_service
    assert (project_root / "app/tools/read_uploaded_file.py").is_file()
    assert (project_root / "app/tools/get_evidence_detail.py").is_file()
    assert not (project_root / "app/agents/graphs/knowledge_query.py").exists()
    assert not (project_root / "app/api/routes/knowledge.py").exists()
    inventory_graph = (project_root / "app/agents/graphs/inventory_query.py").read_text(
        encoding="utf-8"
    )
    assert "read_uploaded_file" not in inventory_graph
    assert "get_evidence_detail" not in inventory_graph
