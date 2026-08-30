"""Generate and seed the deterministic m2-complex-v1 evaluation corpus."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.services.storage import LocalStorageBackend, StorageBackend
from scripts.m2_complex_seed_content import (
    M2ComplexSeedContentError,
    build_complex_source_bytes,
)
from scripts.seed_m1 import DEFAULT_MANIFEST_PATH as DEFAULT_M1_MANIFEST_PATH
from scripts.seed_m1 import seed_m1
from scripts.seed_m2_files import (
    _MIME_TYPES,
    GeneratedSource,
    M2SeedDataMismatchError,
    M2SeedResult,
    _m1_tenant_id,
    _seed_database,
    _verify_storage_source,
    deterministic_id,
    seed_definition_hash,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPLEX_SEED_PATH = PROJECT_ROOT / "data" / "seed" / "m2_complex_seed.json"
DEFAULT_COMPLEX_MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "seed" / "m2_complex_manifest.json"
)
_VERSION = "m2-complex-v1"
_EXPECTED_KEYS = {
    "scanned_receiving_ticket",
    "two_column_market_brief",
    "merged_header_cost_table",
    "visual_quality_notice",
    "multi_region_replenishment",
}
_EXPECTED_FORMATS = ["docx", "pdf", "pdf", "pdf", "xlsx"]
_ALLOWED_ACCESS_LEVELS = {"private", "tenant", "restricted"}
_ALLOWED_SUBJECT_TYPES = {"role", "user", "market"}
_ALLOWED_ROUTES = {"native", "docling"}
_FORBIDDEN_DEFINITION_TERMS = ("api_key", "private_key", "access_token", "password")


class M2ComplexSeedDataMismatchError(M2SeedDataMismatchError):
    """The complex definition, object, or database row violates its contract."""


def load_complex_seed_definition(
    path: Path = DEFAULT_COMPLEX_SEED_PATH,
) -> dict[str, Any]:
    """Load the reviewed five-document complex evaluation definition."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed definition cannot be loaded"
        ) from None
    if data.get("version") != _VERSION:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed version must be m2-complex-v1"
        )
    if data.get("data_classification") != "synthetic_demo_data":
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed must be marked as synthetic demo data"
        )
    disclaimer = data.get("disclaimer")
    if not isinstance(disclaimer, str) or "不构成法律" not in disclaimer:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed requires the non-legal-advice marker"
        )
    serialized = json.dumps(data, ensure_ascii=False).lower()
    if any(term in serialized for term in _FORBIDDEN_DEFINITION_TERMS):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed definition must not contain secrets"
        )

    documents = data.get("documents")
    if not isinstance(documents, list) or len(documents) != 5:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed requires exactly five documents"
        )
    keys: set[str] = set()
    names: set[str] = set()
    formats: list[str] = []
    for document in documents:
        _validate_document_definition(document)
        key = document["key"]
        name = document["original_name"]
        if key in keys or name in names:
            raise M2ComplexSeedDataMismatchError(
                "M2 complex document keys and names must be unique"
            )
        keys.add(key)
        names.add(name)
        formats.append(document["format"])
    if keys != _EXPECTED_KEYS or sorted(formats) != _EXPECTED_FORMATS:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed format or scenario coverage is incomplete"
        )
    if sum(len(document["golden_facts"]) for document in documents) != 10:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed requires exactly ten golden facts"
        )
    return data


def _validate_document_definition(document: object) -> None:
    if not isinstance(document, dict):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed document must be an object"
        )
    required = {
        "key",
        "original_name",
        "format",
        "title",
        "document_type",
        "language",
        "market",
        "link_product",
        "access_level",
        "acl",
        "expected_route",
        "requires_ocr",
        "complexity_tags",
        "content",
        "golden_facts",
    }
    if set(document) != required:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex document fields do not match contract"
        )
    source_format = document["format"]
    if source_format not in _MIME_TYPES:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex source format is not supported"
        )
    if not document["original_name"].endswith(f".{source_format}"):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex filename does not match format"
        )
    if document["access_level"] not in _ALLOWED_ACCESS_LEVELS:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex access level is invalid"
        )
    if document["expected_route"] not in _ALLOWED_ROUTES:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex expected route is invalid"
        )
    if not isinstance(document["requires_ocr"], bool):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex OCR marker must be boolean"
        )
    tags = document["complexity_tags"]
    if not isinstance(tags, list) or len(tags) < 2 or any(
        not isinstance(tag, str) or not tag for tag in tags
    ):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex document requires complexity tags"
        )
    facts = document["golden_facts"]
    if not isinstance(facts, list) or len(facts) != 2:
        raise M2ComplexSeedDataMismatchError(
            "M2 complex document requires exactly two golden facts"
        )
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != {"question", "answer", "locator"}:
            raise M2ComplexSeedDataMismatchError(
                "M2 complex golden fact fields do not match contract"
            )
        if not all(isinstance(fact[field], str) and fact[field] for field in ("question", "answer")):
            raise M2ComplexSeedDataMismatchError(
                "M2 complex golden fact text is invalid"
            )
        if not isinstance(fact["locator"], dict) or not fact["locator"]:
            raise M2ComplexSeedDataMismatchError(
                "M2 complex golden fact locator is invalid"
            )
    acl_entries = document["acl"]
    if not isinstance(acl_entries, list):
        raise M2ComplexSeedDataMismatchError("M2 complex ACL must be a list")
    for acl in acl_entries:
        if not isinstance(acl, dict) or acl.get("subject_type") not in (
            _ALLOWED_SUBJECT_TYPES
        ):
            raise M2ComplexSeedDataMismatchError("M2 complex ACL entry is invalid")


def generate_complex_sources(data: dict[str, Any]) -> list[GeneratedSource]:
    """Generate stable source bytes, identities, hashes, and Storage keys."""

    version = data["version"]
    storage_year, storage_month, _day = data["storage_date"].split("-")
    tenant_id = _m1_tenant_id(data["tenant_name"])
    sources: list[GeneratedSource] = []
    try:
        for definition in data["documents"]:
            key = definition["key"]
            extension = f".{definition['format']}"
            content = build_complex_source_bytes(definition, data["disclaimer"])
            if not content:
                raise M2ComplexSeedDataMismatchError(
                    "M2 complex seed generated an empty source file"
                )
            file_id = deterministic_id(version, "file", key)
            sources.append(
                GeneratedSource(
                    definition=definition,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                    file_id=file_id,
                    document_id=deterministic_id(version, "document", key),
                    version_id=deterministic_id(version, "document_version", key),
                    storage_key=(
                        f"{tenant_id}/uploads/{storage_year}/{storage_month}/"
                        f"{file_id}{extension}"
                    ),
                )
            )
    except (KeyError, TypeError, ValueError, M2ComplexSeedContentError):
        raise M2ComplexSeedDataMismatchError(
            "M2 complex seed content cannot be generated"
        ) from None
    return sources


def build_complex_manifest(
    data: dict[str, Any],
    sources: list[GeneratedSource],
) -> dict[str, Any]:
    """Build the formal manifest used by later Native/Docling comparisons."""

    documents: list[dict[str, Any]] = []
    for source in sources:
        definition = source.definition
        documents.append(
            {
                "key": definition["key"],
                "file_id": str(source.file_id),
                "document_id": str(source.document_id),
                "version_id": str(source.version_id),
                "original_name": definition["original_name"],
                "format": definition["format"],
                "mime_type": _MIME_TYPES[definition["format"]],
                "size_bytes": len(source.content),
                "sha256": source.sha256,
                "title": definition["title"],
                "document_type": definition["document_type"],
                "language": definition["language"],
                "market": definition["market"],
                "access_level": definition["access_level"],
                "acl": definition["acl"],
                "expected_route": definition["expected_route"],
                "requires_ocr": definition["requires_ocr"],
                "complexity_tags": definition["complexity_tags"],
                "structure": _structure_summary(definition),
                "golden_facts": definition["golden_facts"],
            }
        )
    return {
        "version": data["version"],
        "random_seed": data["random_seed"],
        "data_classification": data["data_classification"],
        "disclaimer": data["disclaimer"],
        "seed_definition_hash": seed_definition_hash(data),
        "seeded_row_counts": {
            "files": len(sources),
            "documents": len(sources),
            "document_versions": len(sources),
            "document_acl": sum(len(source.definition["acl"]) for source in sources),
        },
        "documents": documents,
    }


def _structure_summary(definition: dict[str, Any]) -> dict[str, Any]:
    content = definition["content"]
    if definition["format"] == "pdf":
        if "pages" in content:
            return {"page_count": len(content["pages"])}
        return {"page_count": 1, "table_count": 1, "header_rows": 2}
    if definition["format"] == "docx":
        return {
            "section_count": len(content["sections"]),
            "visual_regions": ["header", "footer", "body_image"],
        }
    return {
        "sheet_names": [sheet["name"] for sheet in content["sheets"]],
        "row_counts": {
            sheet["name"]: len(sheet["rows"]) for sheet in content["sheets"]
        },
        "merged_ranges": {
            sheet["name"]: sheet["merged_ranges"] for sheet in content["sheets"]
        },
        "formula_cells": ["补货测算!D3", "补货测算!G3", "补货测算!D4", "补货测算!G4", "补货测算!D9", "补货测算!D10"],
    }


def seed_m2_complex_files(
    settings: Settings | None = None,
    *,
    seed_path: Path = DEFAULT_COMPLEX_SEED_PATH,
    manifest_path: Path = DEFAULT_COMPLEX_MANIFEST_PATH,
    m1_manifest_path: Path = DEFAULT_M1_MANIFEST_PATH,
    storage: StorageBackend | None = None,
) -> M2SeedResult:
    """Create prerequisites, immutable complex sources, and idempotent metadata."""

    resolved_settings = settings or Settings()
    data = load_complex_seed_definition(seed_path)
    sources = generate_complex_sources(data)
    manifest = build_complex_manifest(data, sources)
    seed_m1(resolved_settings, manifest_path=m1_manifest_path)
    resolved_storage = storage or LocalStorageBackend(
        resolved_settings.local_storage_root,
        chunk_size_bytes=resolved_settings.upload_stream_chunk_size_bytes,
    )
    created_keys: list[str] = []
    try:
        for source in sources:
            if resolved_storage.exists(source.storage_key):
                try:
                    _verify_storage_source(resolved_storage, source)
                except M2SeedDataMismatchError as exc:
                    raise M2ComplexSeedDataMismatchError(str(exc)) from None
                continue
            stored = resolved_storage.put(
                source.storage_key,
                io.BytesIO(source.content),
                _MIME_TYPES[source.definition["format"]],
            )
            if stored.sha256 != source.sha256 or stored.size_bytes != len(source.content):
                raise M2ComplexSeedDataMismatchError(
                    "Stored M2 complex source does not match manifest"
                )
            created_keys.append(source.storage_key)
        runtime = create_database_runtime(resolved_settings)
        try:
            with runtime.session_factory.begin() as session:
                _seed_database(session, data, sources)
        finally:
            runtime.engine.dispose()
    except Exception:
        for key in reversed(created_keys):
            resolved_storage.delete(key)
        raise

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return M2SeedResult(manifest=manifest, manifest_path=manifest_path)


def main() -> None:
    result = seed_m2_complex_files()
    print("M2 complex synthetic evaluation files are ready.")
    print(f"Manifest: {result.manifest_path}")
    print(
        "Sources: "
        f"{len(result.manifest['documents'])} deterministic complex files; "
        "Docling and Parser Router are not executed by this step."
    )


if __name__ == "__main__":
    main()
