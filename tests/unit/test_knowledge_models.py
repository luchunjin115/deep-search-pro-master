import warnings
from typing import cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    Constraint,
    ForeignKeyConstraint,
    Index,
    Table,
    UniqueConstraint,
)
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import configure_mappers

import app.models as exported_models
from app.db.base import Base
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)


def named_constraint(table: Table, name: str) -> Constraint:
    return next(
        constraint for constraint in table.constraints if constraint.name == name
    )


def test_knowledge_mappers_configure_without_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()


def test_metadata_contains_chunk_set_and_chunk_rows() -> None:
    assert {
        "files",
        "documents",
        "document_versions",
        "document_acl",
        "document_chunk_sets",
        "document_chunks",
    } <= set(Base.metadata.tables)


def test_metadata_contains_document_index_sets() -> None:
    assert "document_index_sets" in Base.metadata.tables


def test_document_index_set_is_exported_for_migrations() -> None:
    assert getattr(exported_models, "DocumentIndexSet", None) is DocumentIndexSet


def test_index_set_keeps_full_identity_lifecycle_and_statistics() -> None:
    table = cast(Table, DocumentIndexSet.__table__)
    columns = set(table.columns.keys())
    constraint_names = {constraint.name for constraint in table.constraints}
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    index_names = {str(index.name) for index in table.indexes}

    assert {
        "tenant_id",
        "document_id",
        "document_version_id",
        "document_chunk_set_id",
        "index_schema_version",
        "embedding_identity_json",
        "embedding_identity_sha256",
        "embedding_model",
        "embedding_version",
        "embedding_purpose",
        "fts_builder_version",
        "status",
        "attempt_count",
        "chunk_count",
        "text_chunk_count",
        "table_chunk_count",
        "total_token_count",
        "error_message",
        "created_at",
        "started_at",
        "completed_at",
    } <= columns
    assert {
        "ck_document_index_sets_identity_format",
        "ck_document_index_sets_identity_json_object",
        "ck_document_index_sets_status_allowed",
        "ck_document_index_sets_attempt_timestamps_match_status",
        "ck_document_index_sets_result_matches_status",
        "ck_document_index_sets_statistics_consistent",
    } <= constraint_names
    assert (
        "tenant_id",
        "document_version_id",
        "document_chunk_set_id",
        "index_schema_version",
        "embedding_identity_sha256",
        "embedding_purpose",
        "fts_builder_version",
    ) in unique_column_sets
    assert "ix_document_index_sets_tenant_version_status" in index_names


def test_index_set_foreign_keys_cannot_cross_version_or_chunk_set() -> None:
    table = cast(Table, DocumentIndexSet.__table__)
    foreign_keys = {
        constraint.name: constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    version_fk = foreign_keys["fk_document_index_sets_tenant_version_document"]
    chunk_set_fk = foreign_keys["fk_document_index_sets_tenant_set_version_document"]

    assert tuple(version_fk.column_keys) == (
        "tenant_id",
        "document_version_id",
        "document_id",
    )
    assert tuple(element.target_fullname for element in version_fk.elements) == (
        "document_versions.tenant_id",
        "document_versions.id",
        "document_versions.document_id",
    )
    assert version_fk.ondelete == "CASCADE"
    assert tuple(chunk_set_fk.column_keys) == (
        "tenant_id",
        "document_chunk_set_id",
        "document_version_id",
        "document_id",
    )
    assert tuple(element.target_fullname for element in chunk_set_fk.elements) == (
        "document_chunk_sets.tenant_id",
        "document_chunk_sets.id",
        "document_chunk_sets.document_version_id",
        "document_chunk_sets.document_id",
    )
    assert chunk_set_fk.ondelete == "CASCADE"


def test_active_index_pointer_requires_same_ready_index_set() -> None:
    version_table = cast(Table, DocumentVersion.__table__)
    index_table = cast(Table, DocumentIndexSet.__table__)
    active_fk = named_constraint(
        version_table,
        "fk_document_versions_active_index_set",
    )
    index_unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in index_table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "active_index_set_id" in version_table.columns
    assert isinstance(active_fk, ForeignKeyConstraint)
    assert tuple(active_fk.column_keys) == (
        "tenant_id",
        "active_index_set_id",
        "id",
        "document_id",
        "index_status",
    )
    assert tuple(element.target_fullname for element in active_fk.elements) == (
        "document_index_sets.tenant_id",
        "document_index_sets.id",
        "document_index_sets.document_version_id",
        "document_index_sets.document_id",
        "document_index_sets.status",
    )
    assert active_fk.use_alter is True
    assert (
        "tenant_id",
        "id",
        "document_version_id",
        "document_id",
        "status",
    ) in index_unique_sets
    assert "ck_document_versions_active_index_set_matches_status" in {
        constraint.name for constraint in version_table.constraints
    }


def test_chunk_rows_belong_to_one_index_set_generation() -> None:
    table = cast(Table, DocumentChunk.__table__)
    columns = set(table.columns.keys())
    foreign_keys = {
        constraint.name: constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    index_fk = foreign_keys[
        "fk_document_chunks_tenant_index_set_chunk_set_version_document"
    ]

    assert {"document_index_set_id", "embedding_cache_key"} <= columns
    assert table.c.document_index_set_id.nullable is False
    assert table.c.embedding_cache_key.nullable is False
    assert tuple(index_fk.column_keys) == (
        "tenant_id",
        "document_index_set_id",
        "document_chunk_set_id",
        "document_version_id",
        "document_id",
    )
    assert tuple(element.target_fullname for element in index_fk.elements) == (
        "document_index_sets.tenant_id",
        "document_index_sets.id",
        "document_index_sets.document_chunk_set_id",
        "document_index_sets.document_version_id",
        "document_index_sets.document_id",
    )
    assert index_fk.ondelete == "CASCADE"
    assert ("tenant_id", "document_index_set_id", "chunk_id") in unique_column_sets
    assert (
        "tenant_id",
        "document_index_set_id",
        "chunk_index",
    ) in unique_column_sets
    assert ("tenant_id", "document_chunk_set_id", "chunk_id") not in unique_column_sets
    assert (
        "tenant_id",
        "document_chunk_set_id",
        "chunk_index",
    ) not in unique_column_sets


def test_document_active_version_foreign_key_stays_inside_same_document() -> None:
    table = cast(Table, Document.__table__)
    constraint = named_constraint(table, "fk_documents_active_version")

    assert isinstance(constraint, ForeignKeyConstraint)
    assert constraint.use_alter is True
    assert tuple(constraint.column_keys) == (
        "tenant_id",
        "active_version_id",
        "id",
    )
    assert tuple(element.target_fullname for element in constraint.elements) == (
        "document_versions.tenant_id",
        "document_versions.id",
        "document_versions.document_id",
    )


def test_version_uniqueness_covers_number_hash_and_physical_file() -> None:
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in cast(Table, DocumentVersion.__table__).constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("tenant_id", "document_id", "version_no") in unique_column_sets
    assert ("tenant_id", "document_id", "content_hash") in unique_column_sets
    assert ("tenant_id", "file_id") in unique_column_sets


def test_acl_uses_separate_role_user_and_market_grants() -> None:
    table = cast(Table, DocumentAcl.__table__)
    columns = set(table.columns.keys())
    unique_acl_indexes = {index.name for index in table.indexes if index.unique}

    assert {"subject_type", "role_name", "user_id", "market_code"} <= columns
    assert unique_acl_indexes == {
        "uq_document_acl_market",
        "uq_document_acl_role",
        "uq_document_acl_user",
    }


def test_soft_delete_and_internal_path_boundaries_are_explicit() -> None:
    file_columns = set(cast(Table, StoredFile.__table__).columns.keys())
    document_columns = set(cast(Table, Document.__table__).columns.keys())

    assert {"status", "deleted_at"} <= file_columns
    assert "deleted_at" in document_columns
    assert "storage_key" in file_columns
    assert "absolute_path" not in file_columns
    assert "original_path" not in file_columns


def test_chunk_set_identity_matches_the_canonical_chunk_artifact_contract() -> None:
    table = cast(Table, DocumentChunkSet.__table__)
    columns = set(table.columns.keys())

    assert {
        "artifact_schema_version",
        "content_hash_version",
        "routed_schema_version",
        "canonical_schema_version",
        "source_sha256",
        "parsed_publication_sha256",
        "selected_artifact_content_sha256",
        "chunker_name",
        "chunker_version",
        "token_counter_name",
        "token_counter_version",
        "normalization_version",
        "config_json",
        "config_sha256",
        "output_sha256",
    } <= columns


def test_chunk_set_foreign_key_cannot_cross_tenant_version_or_document() -> None:
    table = cast(Table, DocumentChunkSet.__table__)
    constraint = named_constraint(
        table,
        "fk_document_chunk_sets_tenant_version_document",
    )

    assert isinstance(constraint, ForeignKeyConstraint)
    assert tuple(constraint.column_keys) == (
        "tenant_id",
        "document_version_id",
        "document_id",
    )
    assert tuple(element.target_fullname for element in constraint.elements) == (
        "document_versions.tenant_id",
        "document_versions.id",
        "document_versions.document_id",
    )
    assert constraint.ondelete == "CASCADE"


def test_chunk_row_keeps_canonical_contract_fields_and_embedding_metadata() -> None:
    table = cast(Table, DocumentChunk.__table__)
    columns = set(table.columns.keys())

    assert {
        "tenant_id",
        "document_id",
        "document_version_id",
        "document_chunk_set_id",
        "chunk_id",
        "chunk_index",
        "kind",
        "body_text",
        "retrieval_text",
        "fts_text",
        "token_count",
        "content_sha256",
        "heading_path",
        "page_numbers",
        "source_block_ids",
        "source_spans",
        "bounding_boxes",
        "overlap_json",
        "table_json",
        "warnings",
        "search_vector",
        "embedding",
        "embedding_model",
        "embedding_version",
    } <= columns
    assert isinstance(table.c.search_vector.computed, Computed)
    assert isinstance(table.c.embedding.type, Vector)
    assert table.c.embedding.type.dim == 1024


def test_chunk_row_foreign_keys_prevent_wrong_attachment() -> None:
    table = cast(Table, DocumentChunk.__table__)
    foreign_keys = {
        constraint.name: constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    set_fk = foreign_keys["fk_document_chunks_tenant_set_version_document"]
    version_fk = foreign_keys["fk_document_chunks_tenant_version_document"]

    assert tuple(set_fk.column_keys) == (
        "tenant_id",
        "document_chunk_set_id",
        "document_version_id",
        "document_id",
    )
    assert tuple(element.target_fullname for element in set_fk.elements) == (
        "document_chunk_sets.tenant_id",
        "document_chunk_sets.id",
        "document_chunk_sets.document_version_id",
        "document_chunk_sets.document_id",
    )
    assert set_fk.ondelete == "CASCADE"
    assert version_fk.ondelete == "CASCADE"


def test_chunk_row_has_fts_vector_and_filter_indexes() -> None:
    table = cast(Table, DocumentChunk.__table__)
    indexes: dict[str, Index] = {
        str(index.name): index for index in table.indexes if index.name is not None
    }

    assert {
        "ix_document_chunks_tenant_document_version_index_set_index",
        "ix_document_chunks_search_vector_gin",
        "ix_document_chunks_embedding_hnsw_cosine",
    } <= indexes.keys()
    assert (
        indexes["ix_document_chunks_search_vector_gin"].dialect_options["postgresql"][
            "using"
        ]
        == "gin"
    )
    vector_index = indexes["ix_document_chunks_embedding_hnsw_cosine"]
    assert vector_index.dialect_options["postgresql"]["using"] == "hnsw"
    assert vector_index.dialect_options["postgresql"]["ops"] == {
        "embedding": "vector_cosine_ops"
    }


def test_chunk_set_keeps_status_results_statistics_and_safe_storage_key() -> None:
    table = cast(Table, DocumentChunkSet.__table__)
    columns = set(table.columns.keys())
    constraint_names = {constraint.name for constraint in table.constraints}

    assert {
        "status",
        "attempt_count",
        "chunk_storage_key",
        "chunk_count",
        "text_chunk_count",
        "table_chunk_count",
        "total_token_count",
        "excluded_span_count",
        "error_message",
        "started_at",
        "completed_at",
    } <= columns
    assert {
        "ck_document_chunk_sets_attempt_timestamps_match_status",
        "ck_document_chunk_sets_chunk_storage_key_format",
        "ck_document_chunk_sets_result_matches_status",
        "ck_document_chunk_sets_statistics_consistent",
    } <= constraint_names
    assert "absolute_path" not in columns
