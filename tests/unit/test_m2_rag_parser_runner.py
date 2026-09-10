from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.evals.rag_runner import (
    ParserEvaluationReport,
    _selected_candidate_quality_gate_passed,
    build_default_fixture_registry,
    evaluate_artifact_recovery,
)
from app.schemas.evaluation import EvaluationCase
from app.services.documents.artifacts import (
    ArtifactTableBlock,
    ArtifactTableCell,
    ArtifactTableRow,
    ArtifactTextBlock,
    build_canonical_artifact,
)
from app.services.documents.parsers.base import SourceLocator

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"
REPORT_TEMPLATE_PATH = (
    ROOT / "data" / "evals" / "m2_cross_border_parser_report_template_v1.json"
)


def _cases() -> list[EvaluationCase]:
    return [
        EvaluationCase.model_validate_json(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
    ]


def test_default_fixture_registry_resolves_every_frozen_reference() -> None:
    registry = build_default_fixture_registry()
    cases = _cases()

    assert registry.registry_version == "m2-eval-fixtures-v1"
    assert {case.trusted_user_fixture_id for case in cases} <= {
        fixture.fixture_id for fixture in registry.users
    }
    assert {case.acl_fixture_id for case in cases} <= {
        fixture.fixture_id for fixture in registry.acl
    }
    assert {case.version_fixture_id for case in cases} <= {
        fixture.fixture_id for fixture in registry.versions
    }
    assert len(registry.users) == 6
    assert len(registry.acl) == 6
    assert len(registry.versions) == 3


def test_recovery_matches_normalized_text_table_rows_and_formulas() -> None:
    artifact = build_canonical_artifact(
        source_type="xlsx",
        source_sha256="1" * 64,
        parser_name="openpyxl",
        parser_version="3.1.5",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text="OSS records must be kept\nfor 10 years.",
                locator=SourceLocator(block_number=1),
            ),
            ArtifactTableBlock(
                block_id="b000002",
                source_kind="worksheet",
                title="报价",
                locator=SourceLocator(sheet_name="报价"),
                sheet_state="visible",
                rows=[
                    ArtifactTableRow(
                        row_number=1,
                        is_empty=False,
                        locator=SourceLocator(
                            sheet_name="报价",
                            cell_range="A1:B1",
                            row_start=1,
                            row_end=1,
                        ),
                        cells=[
                            ArtifactTableCell(
                                column_number=1,
                                coordinate="A1",
                                value="供应商B",
                                display_text="供应商B",
                                data_type="text",
                                locator=SourceLocator(
                                    sheet_name="报价",
                                    row_number=1,
                                    column_number=1,
                                    cell_range="A1",
                                ),
                            ),
                            ArtifactTableCell(
                                column_number=2,
                                coordinate="B1",
                                value=None,
                                display_text="",
                                data_type="formula",
                                formula="=F1+G1",
                                cached_value=None,
                                locator=SourceLocator(
                                    sheet_name="报价",
                                    row_number=1,
                                    column_number=2,
                                    cell_range="B1",
                                ),
                            ),
                        ],
                    )
                ],
            ),
        ],
        warnings=[],
        source_character_count=41,
    )
    cases = [
        case
        for case in _cases()
        if case.case_id
        in {"smoke-ext-024-record-retention", "smoke-syn-008-landed-formula"}
    ]
    cases[0] = cases[0].model_copy(
        update={
            "expected_document_ids": ["test-document"],
            "expected_evidence_spans": [
                cases[0]
                .expected_evidence_spans[0]
                .model_copy(
                    update={
                        "document_id": "test-document",
                        "exact_text": "records must be kept for 10 years",
                    }
                )
            ],
        }
    )
    cases[1] = cases[1].model_copy(
        update={
            "expected_document_ids": ["test-document"],
            "expected_evidence_spans": [
                cases[1]
                .expected_evidence_spans[0]
                .model_copy(
                    update={"document_id": "test-document", "exact_text": "=F1+G1"}
                )
            ],
        }
    )

    result = evaluate_artifact_recovery(
        logical_document_id="test-document",
        artifact=artifact,
        cases=cases,
    )

    assert result.expected_case_ids == [
        "smoke-syn-008-landed-formula",
        "smoke-ext-024-record-retention",
    ]
    assert result.recovered_case_ids == result.expected_case_ids
    assert result.missing_case_ids == []
    assert result.recovery_rate == 1.0


def test_recovery_counts_one_case_missing_without_using_answer_variants() -> None:
    artifact = build_canonical_artifact(
        source_type="pdf",
        source_sha256="2" * 64,
        parser_name="pymupdf",
        parser_version="1.26.4",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text="No Golden evidence is present.",
                locator=SourceLocator(page_number=1),
            )
        ],
        warnings=[],
        source_character_count=26,
        page_count=1,
    )
    source_case = next(
        case for case in _cases() if case.case_id == "smoke-syn-001-voltage"
    )
    case = source_case.model_copy(
        update={
            "expected_document_ids": ["test-document"],
            "expected_evidence_spans": [
                source_case.expected_evidence_spans[0].model_copy(
                    update={"document_id": "test-document"}
                )
            ],
            "acceptable_answer_variants": ["No Golden evidence is present."],
        }
    )

    result = evaluate_artifact_recovery(
        logical_document_id="test-document",
        artifact=artifact,
        cases=[case],
    )

    assert result.recovered_case_ids == []
    assert result.missing_case_ids == ["smoke-syn-001-voltage"]
    assert result.recovery_rate == 0.0


def test_planned_report_template_is_strict_and_contains_no_private_paths() -> None:
    payload = json.loads(REPORT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    report = ParserEvaluationReport.model_validate(payload)

    assert report.run_status == "planned"
    assert report.documents == []
    assert report.aggregate.documents_total == 0
    serialized = report.model_dump_json()
    for forbidden in ("storage_key", "tenant_id", "password", "D:\\\\", "/home/"):
        assert forbidden not in serialized


def test_completed_report_cannot_claim_an_unfinished_run() -> None:
    payload = json.loads(REPORT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload["run_status"] = "completed"

    with pytest.raises(ValidationError):
        ParserEvaluationReport.model_validate(payload)


def test_chunk_report_gate_needs_one_selected_candidate_not_every_experiment() -> None:
    entries = [
        SimpleNamespace(base_config_id="chunk-large", quality_gate_passed=False),
        SimpleNamespace(base_config_id="chunk-large", quality_gate_passed=True),
        SimpleNamespace(base_config_id="chunk-current", quality_gate_passed=False),
    ]

    assert _selected_candidate_quality_gate_passed(["chunk-large"], entries) is True
    assert _selected_candidate_quality_gate_passed(["chunk-current"], entries) is False
    assert _selected_candidate_quality_gate_passed([], entries) is False
