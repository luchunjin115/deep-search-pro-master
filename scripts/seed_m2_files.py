"""Generate and seed the deterministic m2-v1 synthetic knowledge corpus."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductVariant
from app.models.identity import Tenant, User
from app.models.knowledge import Document, DocumentAcl, DocumentVersion, StoredFile
from app.services.storage import LocalStorageBackend, StorageBackend
from scripts.m2_seed_content import M2SeedContentError, build_source_bytes
from scripts.seed_m1 import DEFAULT_MANIFEST_PATH as DEFAULT_M1_MANIFEST_PATH
from scripts.seed_m1 import seed_m1

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seed" / "m2_seed.json"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "seed" / "m2_manifest.json"
SEED_NAMESPACE = UUID("bc54df4c-f019-4adb-a176-03b686a49fa5")

_MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}
_ALLOWED_ACCESS_LEVELS = {"private", "tenant", "restricted"}
_ALLOWED_SUBJECT_TYPES = {"role", "user", "market"}
_FORBIDDEN_DEFINITION_TERMS = ("api_key", "private_key", "access_token", "password")


class M2SeedDataMismatchError(RuntimeError):
    """Existing data or source objects conflict with the m2-v1 contract."""


@dataclass(frozen=True, slots=True)
class GeneratedSource:
    """One deterministic source file and its stable identities."""

    definition: dict[str, Any]
    content: bytes
    sha256: str
    file_id: UUID
    document_id: UUID
    version_id: UUID
    storage_key: str


@dataclass(frozen=True, slots=True)
class M2SeedResult:
    """Stable summary returned by one successful M2 seed run."""

    manifest: dict[str, Any]
    manifest_path: Path


def deterministic_id(version: str, entity: str, key: str) -> UUID:
    """Create a stable UUID for one versioned M2 seed entity."""

    return uuid5(SEED_NAMESPACE, f"{version}:{entity}:{key}")


def load_seed_definition(path: Path = DEFAULT_SEED_PATH) -> dict[str, Any]:
    """Load and validate the trusted, reviewable m2-v1 JSON definition."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise M2SeedDataMismatchError("M2 seed definition cannot be loaded") from None

    if data.get("version") != "m2-v1":
        raise M2SeedDataMismatchError("M2 seed version must be m2-v1")
    if data.get("data_classification") != "synthetic_demo_data":
        raise M2SeedDataMismatchError("M2 seed must be marked as synthetic demo data")
    disclaimer = data.get("disclaimer")
    if not isinstance(disclaimer, str) or "不构成法律" not in disclaimer:
        raise M2SeedDataMismatchError("M2 seed requires the non-legal-advice marker")
    serialized = json.dumps(data, ensure_ascii=False).lower()
    if any(term in serialized for term in _FORBIDDEN_DEFINITION_TERMS):
        raise M2SeedDataMismatchError("M2 seed definition must not contain secrets")

    documents = data.get("documents")
    if not isinstance(documents, list) or len(documents) != 5:
        raise M2SeedDataMismatchError("M2 seed requires exactly five documents")
    keys: set[str] = set()
    names: set[str] = set()
    formats: list[str] = []
    for document in documents:
        _validate_document_definition(document)
        key = document["key"]
        name = document["original_name"]
        if key in keys or name in names:
            raise M2SeedDataMismatchError("M2 seed document keys and names must be unique")
        keys.add(key)
        names.add(name)
        formats.append(document["format"])
    if sorted(formats) != ["csv", "docx", "docx", "pdf", "xlsx"]:
        raise M2SeedDataMismatchError("M2 seed format coverage is incomplete")
    return data


def _validate_document_definition(document: object) -> None:
    if not isinstance(document, dict):
        raise M2SeedDataMismatchError("M2 seed document must be an object")
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
        "content",
        "golden_facts",
    }
    if set(document) != required:
        raise M2SeedDataMismatchError("M2 seed document fields do not match contract")
    source_format = document["format"]
    if source_format not in _MIME_TYPES:
        raise M2SeedDataMismatchError("M2 seed source format is not supported")
    if not document["original_name"].endswith(f".{source_format}"):
        raise M2SeedDataMismatchError("M2 seed filename does not match format")
    if document["access_level"] not in _ALLOWED_ACCESS_LEVELS:
        raise M2SeedDataMismatchError("M2 seed access level is invalid")
    if not isinstance(document["golden_facts"], list) or not document["golden_facts"]:
        raise M2SeedDataMismatchError("M2 seed document requires golden facts")
    acl_entries = document["acl"]
    if not isinstance(acl_entries, list):
        raise M2SeedDataMismatchError("M2 seed ACL must be a list")
    for acl in acl_entries:
        if not isinstance(acl, dict) or acl.get("subject_type") not in (
            _ALLOWED_SUBJECT_TYPES
        ):
            raise M2SeedDataMismatchError("M2 seed ACL entry is invalid")


def seed_definition_hash(data: dict[str, Any]) -> str:
    """Hash the canonical source definition independently of JSON whitespace."""

    canonical = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def generate_sources(data: dict[str, Any]) -> list[GeneratedSource]:
    """Build all five source files with deterministic IDs, keys, and bytes."""

    version = data["version"]
    storage_year, storage_month, _day = data["storage_date"].split("-")
    tenant_id = _m1_tenant_id(data["tenant_name"])
    sources: list[GeneratedSource] = []
    try:
        for definition in data["documents"]:
            document_key = definition["key"]
            extension = f".{definition['format']}"
            file_id = deterministic_id(version, "file", document_key)
            document_id = deterministic_id(version, "document", document_key)
            version_id = deterministic_id(version, "document_version", document_key)
            content = build_source_bytes(definition, data["disclaimer"])
            if not content:
                raise M2SeedDataMismatchError("M2 seed generated an empty source file")
            sources.append(
                GeneratedSource(
                    definition=definition,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                    file_id=file_id,
                    document_id=document_id,
                    version_id=version_id,
                    storage_key=(
                        f"{tenant_id}/uploads/{storage_year}/{storage_month}/"
                        f"{file_id}{extension}"
                    ),
                )
            )
    except (KeyError, TypeError, ValueError, M2SeedContentError):
        raise M2SeedDataMismatchError("M2 seed content cannot be generated") from None
    return sources


def build_manifest(
    data: dict[str, Any],
    sources: list[GeneratedSource],
) -> dict[str, Any]:
    """Build the stable, reviewable file hashes and expected source locators."""

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
            "document_acl": sum(
                len(source.definition["acl"]) for source in sources
            ),
        },
        "m1_guard": {
            "sku": data["product_sku"],
            "warehouse_code": "DE-FRA",
            "available": 125,
            "synthetic_data": True,
        },
        "documents": documents,
    }


def _structure_summary(definition: dict[str, Any]) -> dict[str, Any]:
    source_format = definition["format"]
    content = definition["content"]
    if source_format == "pdf":
        return {"page_count": len(content["pages"])}
    if source_format == "docx":
        sections = content["sections"]
        return {
            "heading_count": len(sections),
            "table_count": sum("table" in section for section in sections),
        }
    if source_format == "xlsx":
        return {
            "sheet_names": [sheet["name"] for sheet in content["sheets"]],
            "row_counts": {
                sheet["name"]: 1 + len(sheet["rows"]) for sheet in content["sheets"]
            },
        }
    return {
        "encoding": "utf-8-sig",
        "row_count": 1 + len(content["rows"]) + 2,
    }


def seed_m2_files(
    settings: Settings | None = None,
    *,
    seed_path: Path = DEFAULT_SEED_PATH,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    m1_manifest_path: Path = DEFAULT_M1_MANIFEST_PATH,
    storage: StorageBackend | None = None,
) -> M2SeedResult:
    """Create M1 prerequisites, immutable sources, and idempotent M2 metadata."""

    resolved_settings = settings or Settings()
    data = load_seed_definition(seed_path)
    sources = generate_sources(data)
    manifest = build_manifest(data, sources)

    seed_m1(resolved_settings, manifest_path=m1_manifest_path)
    resolved_storage = storage or LocalStorageBackend(
        resolved_settings.local_storage_root,
        chunk_size_bytes=resolved_settings.upload_stream_chunk_size_bytes,
    )
    created_keys: list[str] = []
    try:
        for source in sources:
            if resolved_storage.exists(source.storage_key):
                _verify_storage_source(resolved_storage, source)
                continue
            stored = resolved_storage.put(
                source.storage_key,
                io.BytesIO(source.content),
                _MIME_TYPES[source.definition["format"]],
            )
            if stored.sha256 != source.sha256 or stored.size_bytes != len(source.content):
                raise M2SeedDataMismatchError("Stored M2 source does not match manifest")
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


def _verify_storage_source(storage: StorageBackend, source: GeneratedSource) -> None:
    try:
        with storage.open(source.storage_key) as stream:
            existing = stream.read()
    except Exception:  # noqa: BLE001 - custom Storage streams may fail arbitrarily.
        raise M2SeedDataMismatchError("Existing M2 Storage object cannot be read") from None
    if existing != source.content:
        raise M2SeedDataMismatchError("Existing M2 Storage object differs from seed")


def _seed_database(
    session: Session,
    data: dict[str, Any],
    sources: list[GeneratedSource],
) -> None:
    tenant = session.scalar(select(Tenant).where(Tenant.name == data["tenant_name"]))
    if tenant is None:
        raise M2SeedDataMismatchError("M1 prerequisites are missing for M2 seed")
    owner = session.scalar(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == data["owner_email"],
        )
    )
    product = session.scalar(
        select(Product)
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .where(
            Product.tenant_id == tenant.id,
            ProductVariant.sku == data["product_sku"],
        )
    )
    if owner is None or product is None:
        raise M2SeedDataMismatchError("M1 prerequisites are missing for M2 seed")

    for source in sources:
        definition = source.definition
        extension = f".{definition['format']}"
        file_values = {
            "tenant_id": tenant.id,
            "owner_user_id": owner.id,
            "original_name": definition["original_name"],
            "storage_key": source.storage_key,
            "extension": extension,
            "mime_type": _MIME_TYPES[definition["format"]],
            "size_bytes": len(source.content),
            "sha256": source.sha256,
            "category": "uploads",
        }
        stored_file = _get_or_create(
            session,
            StoredFile,
            source.file_id,
            file_values,
            f"file {definition['key']}",
        )

        document_values = {
            "tenant_id": tenant.id,
            "owner_user_id": owner.id,
            "title": definition["title"],
            "document_type": definition["document_type"],
            "language": definition["language"],
            "market": definition["market"],
            "product_id": product.id if definition["link_product"] else None,
            "access_level": definition["access_level"],
        }
        document = _get_or_create(
            session,
            Document,
            source.document_id,
            document_values,
            f"document {definition['key']}",
        )

        version_values = {
            "tenant_id": tenant.id,
            "document_id": document.id,
            "file_id": stored_file.id,
            "version_no": 1,
            "content_hash": source.sha256,
        }
        _get_or_create(
            session,
            DocumentVersion,
            source.version_id,
            version_values,
            f"document version {definition['key']}",
        )
        _seed_acl(session, data["version"], tenant.id, document, definition["acl"])


def _get_or_create(
    session: Session,
    model: type[Any],
    entity_id: UUID,
    expected: dict[str, Any],
    label: str,
) -> Any:
    existing = session.get(model, entity_id)
    if existing is None:
        existing = model(id=entity_id, **expected)
        session.add(existing)
        session.flush()
        return existing
    mismatches = [
        field for field, expected_value in expected.items()
        if getattr(existing, field) != expected_value
    ]
    if mismatches:
        raise M2SeedDataMismatchError(
            f"Existing {label} differs in: {', '.join(sorted(mismatches))}"
        )
    return existing


def _seed_acl(
    session: Session,
    version: str,
    tenant_id: UUID,
    document: Document,
    acl_entries: list[dict[str, Any]],
) -> None:
    for acl in acl_entries:
        subject_type = acl["subject_type"]
        role_name = acl.get("role_name")
        user_id = UUID(acl["user_id"]) if acl.get("user_id") else None
        market_code = acl.get("market_code")
        identity = role_name or market_code or str(user_id)
        acl_id = deterministic_id(
            version,
            "document_acl",
            f"{document.id}:{subject_type}:{identity}",
        )
        _get_or_create(
            session,
            DocumentAcl,
            acl_id,
            {
                "tenant_id": tenant_id,
                "document_id": document.id,
                "subject_type": subject_type,
                "role_name": role_name,
                "user_id": user_id,
                "market_code": market_code,
                "permission": "read",
            },
            f"ACL {document.id}:{subject_type}:{identity}",
        )


def _m1_tenant_id(tenant_name: str) -> UUID:
    from scripts.seed_m1 import deterministic_id as m1_deterministic_id

    return m1_deterministic_id("m1-v1", "tenant", tenant_name)


def main() -> None:
    """CLI entry point for local M2 source-data preparation."""

    result = seed_m2_files()
    print("M2 synthetic knowledge files are ready.")
    print(f"Manifest: {result.manifest_path}")
    print(
        "Sources: "
        f"{len(result.manifest['documents'])} deterministic files; "
        "parse and index states remain pending."
    )


if __name__ == "__main__":
    main()
