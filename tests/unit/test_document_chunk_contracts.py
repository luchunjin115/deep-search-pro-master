from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.documents.artifacts import ArtifactTableCell
from app.services.documents.chunking import (
    CanonicalChunkArtifact,
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    UnicodeMixedTokenCounter,
    build_chunk_artifact,
    build_document_chunk,
)
from app.services.documents.chunking.contracts import (
    ChunkOverlap,
    ChunkSourceSpan,
    ChunkTableData,
    ChunkTableRow,
)
from app.services.documents.parsers.base import SourceLocator

_DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
_VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")
_SOURCE_HASH = "1" * 64
_PUBLICATION_HASH = "2" * 64
_ARTIFACT_HASH = "3" * 64


def _input() -> ChunkInputProvenance:
    return ChunkInputProvenance(
        document_id=_DOCUMENT_ID,
        document_version_id=_VERSION_ID,
        source_sha256=_SOURCE_HASH,
        parsed_publication_sha256=_PUBLICATION_HASH,
        selected_artifact_content_sha256=_ARTIFACT_HASH,
    )


def _counter() -> UnicodeMixedTokenCounter:
    return UnicodeMixedTokenCounter()


def _identity() -> ChunkerIdentity:
    counter = _counter()
    return ChunkerIdentity(
        token_counter_name=counter.name,
        token_counter_version=counter.version,
    )


def _text_chunk(
    *,
    chunk_id: str = "c000001",
    chunk_index: int = 1,
    text: str = "安全要求：额定电压为 220 V。",
    token_count: int | None = None,
    overlap: ChunkOverlap | None = None,
):  # type: ignore[no-untyped-def]
    locator = SourceLocator(page_number=1, heading_path=["安全要求"])
    span = ChunkSourceSpan(
        block_id="b000001",
        start_locator=locator,
        end_locator=locator,
        character_start=0,
        character_end=len(text),
    )
    return build_document_chunk(
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        kind="text",
        body_text=text,
        retrieval_text=f"安全要求\n{text}",
        token_count=(
            token_count
            if token_count is not None
            else _counter().count(f"安全要求\n{text}")
        ),
        heading_path=["安全要求"],
        source_block_ids=["b000001"],
        source_spans=[span],
        page_numbers=[1],
        overlap=overlap,
    )


def test_unicode_counter_is_versioned_nfc_normalized_and_deterministic() -> None:
    counter = _counter()
    text = "蘑菇灯 ABCD1234，220 V e\u0301"

    first = counter.spans(text)
    second = counter.spans(text)

    assert counter.name == "unicode_mixed"
    assert counter.version == "m2-unicode-token-counter-v1"
    assert first == second
    assert counter.count(text) == len(first) == 9
    assert [span.text for span in first[:6]] == [
        "蘑",
        "菇",
        "灯",
        "ABCD",
        "1234",
        "，",
    ]
    assert first[-1].text == "é"
    assert counter.count(" \n\t") == 0


def test_chunking_config_is_built_from_central_settings() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    config = ChunkingConfig.from_settings(settings)

    assert config.target_tokens == 600
    assert config.max_tokens == 700
    assert config.overlap_tokens == 100
    assert config.heading_context_max_tokens == 120
    assert config.table_row_overlap == 1
    assert config.repeated_edge_min_pages == 2
    assert config.include_hidden_sheets is True
    assert config.repeat_table_headers is True


def test_text_chunk_and_artifact_are_byte_stable_and_self_validating() -> None:
    chunk = _text_chunk()

    first = build_chunk_artifact(
        input_provenance=_input(),
        chunker=_identity(),
        config=ChunkingConfig(),
        chunks=[chunk],
    )
    second = build_chunk_artifact(
        input_provenance=_input(),
        chunker=_identity(),
        config=ChunkingConfig(),
        chunks=[_text_chunk()],
    )

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first.schema_version == "m2-canonical-chunk-artifact-v1"
    assert first.content_hash_version == "m2-chunk-content-v1"
    assert first.chunks[0].content_sha256 == chunk.content_sha256
    assert first.statistics.chunk_count == 1
    assert first.statistics.text_chunk_count == 1
    assert first.statistics.table_chunk_count == 0
    assert first.statistics.total_token_count == chunk.token_count
    assert CanonicalChunkArtifact.model_validate_json(first.model_dump_json()) == first
    serialized = first.model_dump_json()
    assert "storage_key" not in serialized
    assert "original_name" not in serialized
    assert "D:\\" not in serialized


def test_config_change_creates_a_different_chunk_set_identity_and_output_hash() -> None:
    chunk = _text_chunk()
    first = build_chunk_artifact(
        input_provenance=_input(),
        chunker=_identity(),
        config=ChunkingConfig(target_tokens=600),
        chunks=[chunk],
    )
    changed = build_chunk_artifact(
        input_provenance=_input(),
        chunker=_identity(),
        config=ChunkingConfig(target_tokens=650),
        chunks=[chunk],
    )

    assert first.config_sha256 != changed.config_sha256
    assert first.chunk_set_id != changed.chunk_set_id
    assert first.output_sha256 != changed.output_sha256


def test_chunk_and_artifact_hashes_reject_tampering() -> None:
    artifact = build_chunk_artifact(
        input_provenance=_input(),
        chunker=_identity(),
        config=ChunkingConfig(),
        chunks=[_text_chunk()],
    )
    tampered_chunk = artifact.model_dump(mode="json")
    tampered_chunk["chunks"][0]["body_text"] = "被篡改的正文"
    with pytest.raises(ValidationError, match="chunk content hash"):
        CanonicalChunkArtifact.model_validate(tampered_chunk)

    tampered_output = artifact.model_dump(mode="json")
    tampered_output["input"]["parsed_publication_sha256"] = "4" * 64
    with pytest.raises(ValidationError, match="output hash"):
        CanonicalChunkArtifact.model_validate(tampered_output)


def test_table_chunk_retains_sheet_cells_formulas_and_source_locations() -> None:
    header_locator = SourceLocator(
        sheet_name="补货测算",
        cell_range="A1:B1",
        row_start=1,
        row_end=1,
    )
    data_locator = SourceLocator(
        sheet_name="补货测算",
        cell_range="A2:B2",
        row_start=2,
        row_end=2,
    )
    header = ChunkTableRow(
        source_row_number=1,
        role="header",
        repeated_as_context=True,
        cells=[
            ArtifactTableCell(
                column_number=1,
                coordinate="A1",
                value="市场",
                display_text="市场",
                data_type="text",
                column_header=True,
                locator=SourceLocator(
                    sheet_name="补货测算",
                    cell_range="A1",
                    row_number=1,
                    column_number=1,
                ),
            ),
            ArtifactTableCell(
                column_number=2,
                coordinate="B1",
                value="总提前期",
                display_text="总提前期",
                data_type="text",
                column_header=True,
                locator=SourceLocator(
                    sheet_name="补货测算",
                    cell_range="B1",
                    row_number=1,
                    column_number=2,
                ),
            ),
        ],
    )
    data = ChunkTableRow(
        source_row_number=2,
        role="data",
        cells=[
            ArtifactTableCell(
                column_number=1,
                coordinate="A2",
                value="FR",
                display_text="FR",
                data_type="text",
                row_header=True,
                locator=SourceLocator(
                    sheet_name="补货测算",
                    cell_range="A2",
                    row_number=2,
                    column_number=1,
                ),
            ),
            ArtifactTableCell(
                column_number=2,
                coordinate="B2",
                value=None,
                display_text="=C2+D2",
                data_type="formula",
                formula="=C2+D2",
                cached_value=None,
                locator=SourceLocator(
                    sheet_name="补货测算",
                    cell_range="B2",
                    row_number=2,
                    column_number=2,
                ),
            ),
        ],
    )
    span = ChunkSourceSpan(
        block_id="b000001",
        start_locator=header_locator,
        end_locator=data_locator,
    )
    text = "补货测算\n市场 | 总提前期\nFR | =C2+D2"
    chunk = build_document_chunk(
        chunk_id="c000001",
        chunk_index=1,
        kind="table",
        body_text="市场 | 总提前期\nFR | =C2+D2",
        retrieval_text=text,
        token_count=_counter().count(text),
        heading_path=[],
        source_block_ids=["b000001"],
        source_spans=[span],
        page_numbers=[],
        table=ChunkTableData(
            source_kind="worksheet",
            title="补货测算",
            sheet_name="补货测算",
            sheet_state="visible",
            cell_range="A1:B2",
            row_start=1,
            row_end=2,
            rows=[header, data],
        ),
    )
    artifact = build_chunk_artifact(
        input_provenance=_input(),
        chunker=_identity(),
        config=ChunkingConfig(),
        chunks=[chunk],
    )

    table = artifact.chunks[0].table
    assert table is not None
    assert table.sheet_name == "补货测算"
    assert table.cell_range == "A1:B2"
    assert table.rows[0].repeated_as_context is True
    assert table.rows[1].cells[1].formula == "=C2+D2"
    assert table.rows[1].cells[1].locator.cell_range == "B2"


def test_contract_rejects_wrong_sequence_budget_overlap_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ChunkingConfig.model_validate({"target_tokens": 600, "sql": "SELECT 1"})

    oversized = _text_chunk(text="安全要求", token_count=701)
    with pytest.raises(ValidationError, match="hard token maximum"):
        build_chunk_artifact(
            input_provenance=_input(),
            chunker=_identity(),
            config=ChunkingConfig(max_tokens=700),
            chunks=[oversized],
        )

    wrong_sequence = _text_chunk(chunk_id="c000002", chunk_index=2)
    with pytest.raises(ValidationError, match="stable and sequential"):
        build_chunk_artifact(
            input_provenance=_input(),
            chunker=_identity(),
            config=ChunkingConfig(),
            chunks=[wrong_sequence],
        )

    span = _text_chunk().source_spans[0]
    wrong_overlap = _text_chunk(
        chunk_id="c000002",
        chunk_index=2,
        overlap=ChunkOverlap(
            previous_chunk_id="c000001",
            token_count=101,
            source_spans=[span],
        ),
    )
    with pytest.raises(ValidationError, match="overlap exceeds"):
        build_chunk_artifact(
            input_provenance=_input(),
            chunker=_identity(),
            config=ChunkingConfig(overlap_tokens=100),
            chunks=[_text_chunk(), wrong_overlap],
        )
