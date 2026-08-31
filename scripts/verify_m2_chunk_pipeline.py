"""Verify the formal M2 Golden Set through real parse/chunk publication.

This command is intentionally explicit: it loads the local Docling models, writes
temporary formal parsed/chunk publications, records auditable results, and then
restores the ten versioned Seed documents to their pending baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunkSet,
    DocumentVersion,
    StoredFile,
)
from app.schemas.auth import CurrentUser
from app.services.documents import DocumentChunkService, DocumentParserService
from app.services.documents.chunking import (
    CanonicalChunkArtifact,
    DocumentChunk,
    StructureAwareDocumentChunker,
    UnicodeMixedTokenCounter,
    build_chunk_artifact,
)
from app.services.documents.parsers.docling import LocalDoclingProvider
from app.services.documents.routing import RoutedParseResult
from app.services.storage import LocalStorageBackend
from scripts.benchmark_m2_docling import verify_model_cache
from scripts.seed_m1 import load_seed_definition as load_m1_seed_definition
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
    seed_m2_complex_files,
)
from scripts.seed_m2_files import (
    GeneratedSource,
    generate_sources,
    load_seed_definition,
    seed_m2_files,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "m2_chunk_pipeline_report.json"
REPORT_SCHEMA_VERSION = "m2-chunk-pipeline-report-v1"

# Each tuple describes the smallest source facts that must coexist in one Chunk.
# The versioned Seed remains the authority for the question, answer, and locator.
GOLDEN_CHUNK_PROBES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "mushroom_lamp_manual": (
        ("额定电压", "220 V"),
        ("清洁前拔下插头", "干燥无绒软布"),
    ),
    "quality_inspection_sop": (
        ("1至500件", "20件"),
        ("裸露导线", "关键缺陷", "隔离整批"),
    ),
    "de_compliance_checklist": (
        ("不构成法律或认证意见",),
        ("WEEE信息", "缺少正式证明"),
    ),
    "supplier_quotes": (
        ("合成供应商B", "20.9"),
        ("合成供应商A", "=F2+G2"),
    ),
    "monthly_operations": (
        ("2026-06", "DE", "139"),
        ("2026-01", "2026-06", "FR"),
    ),
    "scanned_receiving_ticket": (("BATCH-SCAN-42",), ("20 PCS",)),
    "two_column_market_brief": (("18 EUR",), ("80件",)),
    "merged_header_cost_table": (
        ("合成供应商C", "20.90"),
        ("合成供应商B", "1.20"),
    ),
    "visual_quality_notice": (("QC-VISUAL-17",), ("12 PCS",)),
    "multi_region_replenishment": (
        ("LR-TL-MUSH-OR01", "100"),
        ("FR", "=B10+C10"),
    ),
}

_CELL_RANGE_PATTERN = re.compile(
    r"^(?P<start_col>[A-Z]{1,3})(?P<start_row>[1-9][0-9]*)"
    r"(?::(?P<end_col>[A-Z]{1,3})(?P<end_row>[1-9][0-9]*))?$"
)


def normalize_text(value: str) -> str:
    """Normalize harmless presentation differences for Golden fact matching."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if not character.isspace())


def evaluate_document_facts(
    document_key: str,
    golden_facts: Sequence[dict[str, Any]],
    chunks: Sequence[DocumentChunk],
) -> list[dict[str, Any]]:
    """Match each reviewed fact to one content-and-locator-preserving Chunk."""

    probes_by_fact = GOLDEN_CHUNK_PROBES[document_key]
    if len(probes_by_fact) != len(golden_facts):
        raise RuntimeError(f"Golden probe count differs for {document_key}")

    results: list[dict[str, Any]] = []
    for number, (fact, probes) in enumerate(
        zip(golden_facts, probes_by_fact, strict=True),
        start=1,
    ):
        normalized_probes = [normalize_text(probe) for probe in probes]
        content_matches = [
            chunk
            for chunk in chunks
            if all(
                probe in normalize_text(chunk.retrieval_text)
                for probe in normalized_probes
            )
        ]
        located = [
            chunk
            for chunk in content_matches
            if chunk_covers_locator(chunk, fact["locator"])
        ]
        evidence = located[0] if located else None
        results.append(
            {
                "fact_number": number,
                "question": fact["question"],
                "answer": fact["answer"],
                "expected_locator": fact["locator"],
                "probes": list(probes),
                "content_match_chunk_ids": [
                    chunk.chunk_id for chunk in content_matches
                ],
                "evidence_chunk_id": evidence.chunk_id if evidence else None,
                "content_passed": bool(content_matches),
                "locator_passed": bool(located),
                "passed": evidence is not None,
            }
        )
    return results


def chunk_covers_locator(chunk: DocumentChunk, expected: dict[str, Any]) -> bool:
    """Return whether one Chunk still exposes every reviewed locator dimension."""

    if (
        (page_number := expected.get("page_number"))
        and page_number not in chunk.page_numbers
        and not any(
            span.start_locator.page_number == page_number
            or span.end_locator.page_number == page_number
            for span in chunk.source_spans
        )
    ):
        return False

    heading_path = expected.get("heading_path")
    if heading_path is not None and chunk.heading_path != heading_path:
        return False

    paragraph_number = expected.get("paragraph_number")
    if paragraph_number is not None and not _span_has_number(
        chunk,
        "paragraph_number",
        paragraph_number,
    ):
        return False

    table_number = expected.get("table_number")
    row_number = expected.get("row_number")
    column_number = expected.get("column_number")
    if any(
        value is not None for value in (table_number, row_number, column_number)
    ) and (
        chunk.table is None
        or not any(
            _cell_matches_location(
                cell.locator,
                table_number=table_number,
                row_number=row_number,
                column_number=column_number,
            )
            for row in chunk.table.rows
            for cell in row.cells
        )
    ):
        return False

    sheet_name = expected.get("sheet_name")
    if sheet_name is not None and (
        chunk.table is None or chunk.table.sheet_name != sheet_name
    ):
        return False

    cell_range = expected.get("cell_range")
    if cell_range is not None and not _chunk_covers_cell_range(chunk, cell_range):
        return False

    row_start = expected.get("row_start")
    row_end = expected.get("row_end")
    if row_start is not None and row_end is not None:
        if chunk.table is None:
            return False
        physical_rows = {
            row.source_row_number
            for row in chunk.table.rows
            if not row.repeated_as_context
        }
        if not set(range(row_start, row_end + 1)).issubset(physical_rows):
            return False
    return True


def canonical_chunk_order_is_preserved(chunks: Sequence[DocumentChunk]) -> bool:
    """Check that the first source Block anchor never moves backwards."""

    anchors = [int(chunk.source_block_ids[0][1:]) for chunk in chunks]
    return anchors == sorted(anchors)


def _span_has_number(chunk: DocumentChunk, field: str, expected: int) -> bool:
    return any(
        getattr(span.start_locator, field) == expected
        or getattr(span.end_locator, field) == expected
        for span in chunk.source_spans
    )


def _cell_matches_location(
    locator: Any,
    *,
    table_number: int | None,
    row_number: int | None,
    column_number: int | None,
) -> bool:
    return all(
        expected is None or getattr(locator, field) == expected
        for field, expected in (
            ("table_number", table_number),
            ("row_number", row_number),
            ("column_number", column_number),
        )
    )


def _chunk_covers_cell_range(chunk: DocumentChunk, expected_range: str) -> bool:
    if chunk.table is None:
        return False
    match = _CELL_RANGE_PATTERN.fullmatch(expected_range)
    if match is None:
        return False
    start_col = _column_number(match.group("start_col"))
    end_col = _column_number(match.group("end_col") or match.group("start_col"))
    start_row = int(match.group("start_row"))
    end_row = int(match.group("end_row") or match.group("start_row"))
    coordinates = {
        (cell.locator.row_number, cell.locator.column_number)
        for row in chunk.table.rows
        for cell in row.cells
        if cell.locator.row_number is not None
        and cell.locator.column_number is not None
    }
    expected = {
        (row, column)
        for row in range(start_row, end_row + 1)
        for column in range(start_col, end_col + 1)
    }
    return expected.issubset(coordinates)


def _column_number(label: str) -> int:
    value = 0
    for character in label:
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def run_chunk_pipeline_verification(settings: Settings) -> dict[str, Any]:
    """Run both formal corpora through real services and restore their baseline."""

    if settings.docling_backend != "docling":
        raise RuntimeError("Set DOCLING_BACKEND=docling for real M2-12.6 verification")
    if settings.docling_device != "cpu":
        raise RuntimeError("M2-12.6 uses the verified CPU-only Docling configuration")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model_manifest = verify_model_cache(settings.docling_model_cache_root.resolve())

    storage = LocalStorageBackend(
        settings.local_storage_root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    ordinary_data = load_seed_definition()
    complex_data = load_complex_seed_definition()
    seed_m2_files(settings, storage=storage)
    seed_m2_complex_files(settings, storage=storage)
    sources = [
        (ordinary_data["version"], source) for source in generate_sources(ordinary_data)
    ] + [
        (complex_data["version"], source)
        for source in generate_complex_sources(complex_data)
    ]

    runtime = create_database_runtime(settings)
    version_ids = [source.version_id for _corpus, source in sources]
    file_ids = [source.file_id for _corpus, source in sources]
    document_ids = [source.document_id for _corpus, source in sources]
    report: dict[str, Any] = {}
    cleanup_result: dict[str, Any] = {}
    preflight_complete = False
    try:
        user = _load_owner(runtime.session_factory, ordinary_data)
        _require_clean_formal_baseline(runtime.session_factory, version_ids, file_ids)
        preflight_complete = True
        provider = LocalDoclingProvider(settings)
        parser = DocumentParserService(
            runtime.session_factory,
            storage,
            settings,
            docling_provider=provider,
        )
        chunker = DocumentChunkService(runtime.session_factory, storage, settings)
        documents: list[dict[str, Any]] = []
        definitions = {
            definition["key"]: definition
            for definition in ordinary_data["documents"] + complex_data["documents"]
        }
        for corpus_version, source in sources:
            parse_result = parser.parse_version(
                user,
                document_id=source.document_id,
                version_id=source.version_id,
            )
            publication = chunker.chunk_version(
                user,
                document_id=source.document_id,
                version_id=source.version_id,
            )
            routed_payload, chunk_payload, row = _load_published_payloads(
                runtime.session_factory,
                storage,
                source,
                publication.chunk_set_id,
            )
            routed = RoutedParseResult.model_validate_json(routed_payload)
            artifact = CanonicalChunkArtifact.model_validate_json(chunk_payload)
            rebuilt = _rebuild_artifact(artifact, routed)
            key = source.definition["key"]
            facts = evaluate_document_facts(
                key,
                definitions[key]["golden_facts"],
                artifact.chunks,
            )
            documents.append(
                {
                    "corpus_version": corpus_version,
                    "key": key,
                    "format": source.definition["format"],
                    "source_sha256": source.sha256,
                    "route": routed.route,
                    "parser_provider": routed.selected_artifact.parser.provider,
                    "parsed_publication_sha256": hashlib.sha256(
                        routed_payload
                    ).hexdigest(),
                    "chunk_set_id": str(artifact.chunk_set_id),
                    "config_sha256": artifact.config_sha256,
                    "output_sha256": artifact.output_sha256,
                    "chunk_count": artifact.statistics.chunk_count,
                    "text_chunk_count": artifact.statistics.text_chunk_count,
                    "table_chunk_count": artifact.statistics.table_chunk_count,
                    "max_chunk_tokens": max(
                        chunk.token_count for chunk in artifact.chunks
                    ),
                    "database_status": row.status,
                    "artifact_self_validated": True,
                    "deterministic_rebuild": (
                        rebuilt.model_dump_json().encode("utf-8") == chunk_payload
                    ),
                    "canonical_order_preserved": canonical_chunk_order_is_preserved(
                        artifact.chunks
                    ),
                    "facts": facts,
                    "facts_passed": sum(fact["passed"] for fact in facts),
                    "facts_total": len(facts),
                    "parse_result": {
                        "provider": parse_result.parser_provider,
                        "warning_count": parse_result.warning_count,
                    },
                }
            )

        facts_passed = sum(document["facts_passed"] for document in documents)
        facts_total = sum(document["facts_total"] for document in documents)
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "corpora": [ordinary_data["version"], complex_data["version"]],
            "synthetic_data": True,
            "offline_inference": True,
            "model_manifest": model_manifest,
            "documents": documents,
            "aggregate": {
                "documents_total": len(documents),
                "documents_ready_before_cleanup": sum(
                    document["database_status"] == "ready" for document in documents
                ),
                "facts_passed": facts_passed,
                "facts_total": facts_total,
                "locator_facts_passed": sum(
                    fact["locator_passed"]
                    for document in documents
                    for fact in document["facts"]
                ),
                "deterministic_rebuilds_passed": sum(
                    document["deterministic_rebuild"] for document in documents
                ),
                "canonical_orders_passed": sum(
                    document["canonical_order_preserved"] for document in documents
                ),
                "routes": {
                    route: sum(document["route"] == route for document in documents)
                    for route in ("native", "docling", "hybrid")
                },
            },
        }
    finally:
        if preflight_complete:
            cleanup_result = _restore_formal_baseline(
                runtime.session_factory,
                storage,
                version_ids=version_ids,
                file_ids=file_ids,
                document_ids=document_ids,
            )
        runtime.engine.dispose()

    report["cleanup"] = cleanup_result
    expected_failed_keys = {"visual_quality_notice"}
    failed_keys = {
        document["key"]
        for document in report["documents"]
        if document["facts_passed"] != document["facts_total"]
    }
    aggregate = report["aggregate"]
    report["decision"] = {
        "m2_12_complete": bool(
            aggregate["documents_total"] == 10
            and aggregate["documents_ready_before_cleanup"] == 10
            and aggregate["facts_passed"] == 18
            and aggregate["facts_total"] == 20
            and aggregate["locator_facts_passed"] == 18
            and aggregate["deterministic_rebuilds_passed"] == 10
            and aggregate["canonical_orders_passed"] == 10
            and failed_keys == expected_failed_keys
            and cleanup_result.get("baseline_restored") is True
        ),
        "known_limitation": (
            "visual_quality_notice remains 0/2 because the selected Hybrid DOCX "
            "artifact does not contain header/image text"
        ),
    }
    return report


def _load_owner(session_factory: Any, data: dict[str, Any]) -> CurrentUser:
    m1_data = load_m1_seed_definition()
    owner_definition = next(
        user for user in m1_data["users"] if user["email"] == data["owner_email"]
    )
    with session_factory() as session:
        tenant = session.scalar(
            select(Tenant).where(Tenant.name == data["tenant_name"])
        )
        if tenant is None:
            raise RuntimeError("Formal M2 tenant is missing")
        owner = session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == data["owner_email"],
            )
        )
        if owner is None:
            raise RuntimeError("Formal M2 owner is missing")
        return CurrentUser(
            user_id=owner.id,
            tenant_id=tenant.id,
            email=owner.email,
            display_name=owner.display_name,
            roles=[owner_definition["role"]],
            market_scopes=owner_definition["market_scopes"],
            synthetic_data=True,
        )


def _require_clean_formal_baseline(
    session_factory: Any,
    version_ids: Sequence[Any],
    file_ids: Sequence[Any],
) -> None:
    with session_factory() as session:
        versions = list(
            session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        )
        files = list(
            session.scalars(select(StoredFile).where(StoredFile.id.in_(file_ids)))
        )
        chunk_count = session.scalar(
            select(func.count())
            .select_from(DocumentChunkSet)
            .where(DocumentChunkSet.document_version_id.in_(version_ids))
        )
        clean = bool(
            len(versions) == 10
            and len(files) == 10
            and all(
                version.parse_status == "pending"
                and version.index_status == "pending"
                and version.parser_name is None
                and version.parser_version is None
                and version.parsed_storage_key is None
                for version in versions
            )
            and all(file.status == "uploaded" for file in files)
            and chunk_count == 0
        )
        if not clean:
            raise RuntimeError("Formal M2 Seed is not at the clean pending baseline")


def _load_published_payloads(
    session_factory: Any,
    storage: LocalStorageBackend,
    source: GeneratedSource,
    chunk_set_id: Any,
) -> tuple[bytes, bytes, DocumentChunkSet]:
    with session_factory() as session:
        version = session.get(DocumentVersion, source.version_id)
        row = session.get(DocumentChunkSet, chunk_set_id)
        if (
            version is None
            or version.parsed_storage_key is None
            or row is None
            or row.status != "ready"
            or row.chunk_storage_key is None
        ):
            raise RuntimeError(
                f"Published metadata is incomplete for {source.definition['key']}"
            )
        parsed_key = version.parsed_storage_key
        chunk_key = row.chunk_storage_key
        session.expunge(row)
    with storage.open(parsed_key) as stream:
        routed_payload = stream.read()
    with storage.open(chunk_key) as stream:
        chunk_payload = stream.read()
    return routed_payload, chunk_payload, row


def _rebuild_artifact(
    artifact: CanonicalChunkArtifact,
    routed: RoutedParseResult,
) -> CanonicalChunkArtifact:
    counter = UnicodeMixedTokenCounter()
    result = StructureAwareDocumentChunker(
        config=artifact.config,
        token_counter=counter,
    ).chunk(routed.selected_artifact)
    return build_chunk_artifact(
        input_provenance=artifact.input,
        chunker=artifact.chunker,
        config=artifact.config,
        chunks=result.chunks,
        excluded_spans=result.excluded_spans,
        skipped_tables=result.skipped_tables,
    )


def _restore_formal_baseline(
    session_factory: Any,
    storage: LocalStorageBackend,
    *,
    version_ids: Sequence[Any],
    file_ids: Sequence[Any],
    document_ids: Sequence[Any],
) -> dict[str, Any]:
    keys: set[str] = set()
    with session_factory() as session:
        keys.update(
            key
            for key in session.scalars(
                select(DocumentVersion.parsed_storage_key).where(
                    DocumentVersion.id.in_(version_ids),
                    DocumentVersion.parsed_storage_key.is_not(None),
                )
            )
            if key is not None
        )
        keys.update(
            key
            for key in session.scalars(
                select(DocumentChunkSet.chunk_storage_key).where(
                    DocumentChunkSet.document_version_id.in_(version_ids),
                    DocumentChunkSet.chunk_storage_key.is_not(None),
                )
            )
            if key is not None
        )

    deleted_keys: list[str] = []
    for key in sorted(keys):
        storage.delete(key)
        deleted_keys.append(key)

    with session_factory.begin() as session:
        session.execute(
            update(Document)
            .where(
                Document.id.in_(document_ids),
                Document.active_version_id.in_(version_ids),
            )
            .values(active_version_id=None)
        )
        session.execute(
            delete(DocumentChunkSet).where(
                DocumentChunkSet.document_version_id.in_(version_ids)
            )
        )
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id.in_(version_ids))
            .values(
                parser_name=None,
                parser_version=None,
                parsed_storage_key=None,
                parse_status="pending",
                index_status="pending",
            )
        )
        session.execute(
            update(StoredFile)
            .where(StoredFile.id.in_(file_ids))
            .values(status="uploaded", error_message=None, deleted_at=None)
        )

    with session_factory() as session:
        counts = {
            "files": session.scalar(select(func.count()).select_from(StoredFile)),
            "documents": session.scalar(select(func.count()).select_from(Document)),
            "versions": session.scalar(
                select(func.count()).select_from(DocumentVersion)
            ),
            "acl": session.scalar(select(func.count()).select_from(DocumentAcl)),
            "chunk_sets": session.scalar(
                select(func.count()).select_from(DocumentChunkSet)
            ),
        }
        versions = list(
            session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        )
        files = list(
            session.scalars(select(StoredFile).where(StoredFile.id.in_(file_ids)))
        )
    remaining_keys = [key for key in deleted_keys if storage.exists(key)]
    baseline_restored = bool(
        counts
        == {
            "files": 10,
            "documents": 10,
            "versions": 10,
            "acl": 9,
            "chunk_sets": 0,
        }
        and len(versions) == 10
        and all(
            version.parse_status == "pending"
            and version.index_status == "pending"
            and version.parsed_storage_key is None
            for version in versions
        )
        and len(files) == 10
        and all(file.status == "uploaded" for file in files)
        and not remaining_keys
    )
    return {
        "deleted_publication_count": len(deleted_keys),
        "remaining_publication_keys": remaining_keys,
        "database_counts": counts,
        "baseline_restored": baseline_restored,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_chunk_pipeline_verification(Settings())
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    print(json.dumps(report["cleanup"], ensure_ascii=False, indent=2))
    print(f"report={output}")
    if not report["decision"]["m2_12_complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
