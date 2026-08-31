from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

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
    ChunkSourceSpan,
    ChunkTableData,
    ChunkTableRow,
)
from app.services.documents.indexing import (
    DocumentIndexMappingError,
    DocumentIndexSetIdentity,
    build_document_index_set_identity,
    map_document_chunk_rows,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.retrieval import (
    EmbeddingBatch,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
)

_TENANT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
_VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def _artifact() -> CanonicalChunkArtifact:
    counter = UnicodeMixedTokenCounter()
    text_locator = SourceLocator(page_number=1, heading_path=["安全要求"])
    text = "安全要求：额定电压为 220 V。"
    text_retrieval = f"安全要求\n{text}"
    text_chunk = build_document_chunk(
        chunk_id="c000001",
        chunk_index=1,
        kind="text",
        body_text=text,
        retrieval_text=text_retrieval,
        token_count=counter.count(text_retrieval),
        heading_path=["安全要求"],
        source_block_ids=["b000001"],
        source_spans=[
            ChunkSourceSpan(
                block_id="b000001",
                start_locator=text_locator,
                end_locator=text_locator,
                character_start=0,
                character_end=len(text),
            )
        ],
        page_numbers=[1],
    )

    table_locator = SourceLocator(
        table_number=1,
        row_number=1,
        column_number=1,
    )
    table_retrieval = "参数表\n字段 | 数值\n额定功率 | 12 W"
    table_chunk = build_document_chunk(
        chunk_id="c000002",
        chunk_index=2,
        kind="table",
        body_text="字段 | 数值\n额定功率 | 12 W",
        retrieval_text=table_retrieval,
        token_count=counter.count(table_retrieval),
        heading_path=[],
        source_block_ids=["b000002"],
        source_spans=[
            ChunkSourceSpan(
                block_id="b000002",
                start_locator=table_locator,
                end_locator=table_locator,
            )
        ],
        page_numbers=[],
        table=ChunkTableData(
            source_kind="document_table",
            title="参数表",
            rows=[
                ChunkTableRow(
                    source_row_number=1,
                    role="data",
                    cells=[
                        ArtifactTableCell(
                            column_number=1,
                            value="额定功率",
                            display_text="额定功率",
                            data_type="text",
                            row_header=True,
                            locator=table_locator,
                        )
                    ],
                )
            ],
        ),
    )
    return build_chunk_artifact(
        input_provenance=ChunkInputProvenance(
            document_id=_DOCUMENT_ID,
            document_version_id=_VERSION_ID,
            source_sha256="1" * 64,
            parsed_publication_sha256="2" * 64,
            selected_artifact_content_sha256="3" * 64,
        ),
        chunker=ChunkerIdentity(
            token_counter_name=counter.name,
            token_counter_version=counter.version,
        ),
        config=ChunkingConfig(),
        chunks=[text_chunk, table_chunk],
    )


def _embedding_batch() -> EmbeddingBatch:
    artifact = _artifact()
    provider = FakeEmbeddingProvider()
    return provider.embed(
        [chunk.retrieval_text for chunk in artifact.chunks],
        purpose=EmbeddingPurpose.DOCUMENT,
    )


def test_index_identity_is_stable_and_covers_the_full_embedding_identity() -> None:
    artifact = _artifact()
    provider = FakeEmbeddingProvider()

    first = build_document_index_set_identity(artifact, provider.identity)
    repeated = build_document_index_set_identity(artifact, provider.identity)
    changed = build_document_index_set_identity(
        artifact,
        replace(provider.identity, revision="m2-fake-v2"),
    )

    assert first == repeated
    assert first.index_set_id != changed.index_set_id
    assert first.index_schema_version == "m2-document-index-set-v1"
    assert first.fts_builder_version == "m2-fts-raw-retrieval-v1"
    assert first.embedding_purpose == "document"
    assert first.embedding_model == "fake/m2-deterministic"
    assert first.embedding_version == "m2-fake-v1"
    assert first.embedding_identity_json.model_dump(mode="json") == {
        "contract_version": "m2-embedding-provider-v1",
        "provider": "fake",
        "model_id": "fake/m2-deterministic",
        "revision": "m2-fake-v1",
        "pooling": "sha256-shake-v1",
        "max_length": 8192,
        "normalize": True,
        "precision": "float32",
        "dimensions": 1024,
    }
    assert len(first.embedding_identity_sha256) == 64


def test_index_identity_contract_rejects_hash_and_id_tampering() -> None:
    identity = build_document_index_set_identity(
        _artifact(),
        FakeEmbeddingProvider().identity,
    )

    wrong_hash = identity.model_dump(mode="json")
    wrong_hash["embedding_identity_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="embedding identity hash"):
        DocumentIndexSetIdentity.model_validate(wrong_hash)

    wrong_id = identity.model_dump(mode="json")
    wrong_id["index_set_id"] = "99999999-9999-4999-8999-999999999999"
    with pytest.raises(ValidationError, match="index set ID"):
        DocumentIndexSetIdentity.model_validate(wrong_id)


def test_mapper_preserves_chunk_order_json_and_embedding_audit_fields() -> None:
    artifact = _artifact()
    batch = _embedding_batch()
    identity = build_document_index_set_identity(artifact, batch.identity)

    first = map_document_chunk_rows(
        tenant_id=_TENANT_ID,
        artifact=artifact,
        index_identity=identity,
        embeddings=batch,
    )
    repeated = map_document_chunk_rows(
        tenant_id=_TENANT_ID,
        artifact=artifact,
        index_identity=identity,
        embeddings=batch,
    )

    assert first == repeated
    assert [row.chunk_id for row in first] == ["c000001", "c000002"]
    assert [row.chunk_index for row in first] == [1, 2]
    assert first[0].id != first[1].id
    assert all(row.tenant_id == _TENANT_ID for row in first)
    assert all(row.document_index_set_id == identity.index_set_id for row in first)
    assert all(row.document_chunk_set_id == artifact.chunk_set_id for row in first)
    assert all(row.fts_text == row.retrieval_text for row in first)
    assert all(row.embedding_model == "fake/m2-deterministic" for row in first)
    assert all(row.embedding_version == "m2-fake-v1" for row in first)
    assert [row.embedding_cache_key for row in first] == list(batch.cache_keys)
    assert first[0].heading_path == ["安全要求"]
    assert first[0].table_json is None
    assert first[1].table_json is not None
    table_json = cast(dict[str, Any], first[1].table_json)
    assert table_json["source_kind"] == "document_table"
    assert table_json["rows"][0]["cells"][0]["value"] == "额定功率"
    assert first[0].embedding == list(batch.vectors[0])
    assert first[1].embedding == list(batch.vectors[1])


def test_mapper_rejects_count_order_purpose_identity_and_vector_tampering() -> None:
    artifact = _artifact()
    batch = _embedding_batch()
    identity = build_document_index_set_identity(artifact, batch.identity)

    cases = [
        (
            replace(
                batch,
                vectors=batch.vectors[:1],
                cache_keys=batch.cache_keys[:1],
            ),
            "count",
        ),
        (replace(batch, cache_keys=tuple(reversed(batch.cache_keys))), "cache key"),
        (replace(batch, purpose=EmbeddingPurpose.QUERY), "purpose"),
        (
            replace(
                batch,
                identity=replace(batch.identity, revision="m2-fake-v2"),
            ),
            "identity",
        ),
        (
            replace(
                batch,
                vectors=((float("nan"),) + batch.vectors[0][1:], batch.vectors[1]),
            ),
            "vector",
        ),
    ]

    for tampered, expected in cases:
        with pytest.raises(DocumentIndexMappingError, match=expected):
            map_document_chunk_rows(
                tenant_id=_TENANT_ID,
                artifact=artifact,
                index_identity=identity,
                embeddings=tampered,
            )


def test_mapper_rejects_cross_document_identity_and_mutated_artifact_hash() -> None:
    artifact = _artifact()
    batch = _embedding_batch()
    identity = build_document_index_set_identity(artifact, batch.identity)

    wrong_boundary = identity.model_copy(
        update={"document_id": UUID("44444444-4444-4444-8444-444444444444")}
    )
    with pytest.raises(DocumentIndexMappingError, match="identity"):
        map_document_chunk_rows(
            tenant_id=_TENANT_ID,
            artifact=artifact,
            index_identity=wrong_boundary,
            embeddings=batch,
        )

    artifact.chunks[0].__dict__["body_text"] = "被篡改但没有重算Hash"
    with pytest.raises(DocumentIndexMappingError, match="artifact"):
        map_document_chunk_rows(
            tenant_id=_TENANT_ID,
            artifact=artifact,
            index_identity=identity,
            embeddings=batch,
        )


def test_mapper_rejects_query_embedding_even_when_its_cache_keys_are_consistent() -> (
    None
):
    artifact = _artifact()
    provider = FakeEmbeddingProvider()
    query_batch = provider.embed(
        [chunk.retrieval_text for chunk in artifact.chunks],
        purpose=EmbeddingPurpose.QUERY,
    )
    identity = build_document_index_set_identity(artifact, provider.identity)

    with pytest.raises(DocumentIndexMappingError, match="purpose"):
        map_document_chunk_rows(
            tenant_id=_TENANT_ID,
            artifact=artifact,
            index_identity=identity,
            embeddings=query_batch,
        )
