import warnings
from typing import cast

from sqlalchemy import Constraint, ForeignKeyConstraint, Table, UniqueConstraint
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.models.knowledge import Document, DocumentAcl, DocumentVersion, StoredFile


def named_constraint(table: Table, name: str) -> Constraint:
    return next(
        constraint for constraint in table.constraints if constraint.name == name
    )


def test_knowledge_mappers_configure_without_warnings() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        configure_mappers()


def test_metadata_contains_only_m2_04_knowledge_tables() -> None:
    assert {"files", "documents", "document_versions", "document_acl"} <= set(
        Base.metadata.tables
    )
    assert "document_chunks" not in Base.metadata.tables


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
