from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import (
    ApplicationError,
    CitationValidationError,
    KnowledgeEvidencePersistenceError,
)
from app.schemas.context import (
    CONTEXT_BUNDLE_CONTRACT_VERSION,
    CONTEXT_SEGMENT_HARD_MAX,
    CONTEXT_TOKEN_COUNTER_VERSION,
    CitationValidationResult,
    ContextBundle,
    ContextCitation,
    ContextSegment,
    ContextSegmentRole,
)
from app.schemas.evidence import DocumentEvidenceDetail, DocumentEvidenceSummary
from app.schemas.retrieval import (
    PdfRetrievalSourceLocator,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
)
from app.services.retrieval.errors import (
    ContextBuildError,
    ContextDataContractError,
    ContextInputError,
)


def settings_without_env(**overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        **overrides,  # type: ignore[arg-type]
    )


def segment(
    ordinal: int = 1,
    *,
    role: ContextSegmentRole = "anchor",
    chunk_id: UUID | None = None,
    evidence_id: UUID | None = None,
    neighbor_of_chunk_id: UUID | None = None,
) -> ContextSegment:
    identity = RetrievalCandidateIdentity(
        document_id=uuid4(),
        version_id=uuid4(),
        index_set_id=uuid4(),
        chunk_id=chunk_id or uuid4(),
    )
    return ContextSegment(
        citation_label=f"[E{ordinal}]",
        evidence_id=evidence_id or uuid4(),
        source_type="knowledge",
        role=role,
        neighbor_of_chunk_id=neighbor_of_chunk_id,
        reranker_rank=1,
        identity=identity,
        document=RetrievalDocumentMetadata(
            title="蘑菇灯使用手册",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        source_locator=PdfRetrievalSourceLocator(
            page_number=2,
            block_number=4,
            heading_path=["维护", "清洁"],
        ),
        text="清洁蘑菇灯前请先断开电源。",
        text_sha256="1" * 64,
        token_count=17,
        overlap_trimmed=False,
    )


def bundle(*segments: ContextSegment, supported: bool = True) -> ContextBundle:
    total_tokens = sum(item.token_count for item in segments)
    return ContextBundle(
        context_id=uuid4(),
        query_sha256="2" * 64,
        context_sha256="3" * 64,
        max_tokens=4000,
        total_tokens=total_tokens,
        supported=supported,
        segments=list(segments),
    )


def test_context_settings_are_server_owned_and_bounded() -> None:
    settings = settings_without_env()

    assert settings.context_max_tokens == 4000
    assert settings.context_max_segments == 12
    assert settings.context_neighbor_window == 1

    for overrides in (
        {"context_max_tokens": 699},
        {"context_max_tokens": 16_001},
        {"context_max_segments": 7},
        {"context_max_segments": 13},
        {"context_neighbor_window": -1},
        {"context_neighbor_window": 2},
        {"chunk_max_tokens": 900, "context_max_tokens": 800},
    ):
        with pytest.raises(ValidationError):
            settings_without_env(**overrides)


def test_supported_context_bundle_has_versioned_contiguous_evidence() -> None:
    first = segment(1)
    second = segment(
        2,
        role="next_neighbor",
        neighbor_of_chunk_id=first.identity.chunk_id,
    )
    result = bundle(first, second)

    assert result.contract_version == CONTEXT_BUNDLE_CONTRACT_VERSION
    assert result.token_counter_version == CONTEXT_TOKEN_COUNTER_VERSION
    assert result.supported is True
    assert [item.citation_label for item in result.segments] == ["[E1]", "[E2]"]
    assert len(result.segments) <= CONTEXT_SEGMENT_HARD_MAX


def test_empty_context_is_an_explicit_unsupported_result() -> None:
    result = bundle(supported=False)

    assert result.supported is False
    assert result.total_tokens == 0
    assert result.segments == []

    with pytest.raises(ValidationError, match="unsupported"):
        bundle(segment(), supported=False)
    with pytest.raises(ValidationError, match="supported"):
        bundle(supported=True)


def test_context_rejects_fake_labels_duplicates_and_budget_contradictions() -> None:
    first = segment(1)

    with pytest.raises(ValidationError, match="contiguous"):
        bundle(first, segment(3))
    with pytest.raises(ValidationError, match="Evidence IDs"):
        bundle(first, segment(2, evidence_id=first.evidence_id))
    with pytest.raises(ValidationError, match="Chunk IDs"):
        bundle(first, segment(2, chunk_id=first.identity.chunk_id))
    over_budget = bundle(first).model_dump()
    over_budget["max_tokens"] = 700
    over_budget["total_tokens"] = 701
    with pytest.raises(ValidationError, match="budget"):
        ContextBundle.model_validate(over_budget)
    with pytest.raises(ValidationError):
        ContextSegment.model_validate(first.model_dump() | {"citation_label": "[E13]"})


def test_neighbor_roles_require_an_anchor_identity() -> None:
    with pytest.raises(ValidationError, match="neighbor"):
        segment(role="previous_neighbor")
    with pytest.raises(ValidationError, match="anchor"):
        segment(role="anchor", neighbor_of_chunk_id=uuid4())


def test_context_contract_rejects_sensitive_or_unknown_fields() -> None:
    valid = bundle(segment())
    dumped = valid.model_dump(mode="json")
    rendered = valid.model_dump_json()
    forbidden = {
        "tenant_id",
        "owner_user_id",
        "acl",
        "access_scope",
        "storage_key",
        "local_path",
        "sql",
    }

    def nested_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                key for child in value.values() for key in nested_keys(child)
            }
        if isinstance(value, list):
            return {key for child in value for key in nested_keys(child)}
        return set()

    assert forbidden.isdisjoint(nested_keys(dumped))
    assert "private/storage/object" not in rendered

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ContextBundle(**valid.model_dump(), tenant_id=str(uuid4()))  # type: ignore[call-arg]


def test_document_evidence_contract_supports_knowledge_and_user_file() -> None:
    created_at = datetime.now(UTC)
    identity = RetrievalCandidateIdentity(
        document_id=uuid4(),
        version_id=uuid4(),
        index_set_id=uuid4(),
        chunk_id=uuid4(),
    )
    summary = DocumentEvidenceSummary(
        id=uuid4(),
        source_type="user_file",
        title="我的产品说明.pdf",
        excerpt="额定电压为220 V。",
        observed_at=created_at,
        synthetic_data=True,
    )
    detail = DocumentEvidenceDetail(
        **summary.model_dump(),
        context_id=uuid4(),
        citation_label="[E1]",
        identity=identity,
        document=RetrievalDocumentMetadata(
            title="我的产品说明.pdf",
            document_type="product_manual",
            language="zh-CN",
            market=None,
        ),
        source_locator=PdfRetrievalSourceLocator(page_number=1),
        source_content_sha256="4" * 64,
        context_text_sha256="5" * 64,
        trust_level="document_snapshot",
        created_at=created_at,
    )

    assert summary.source_type == "user_file"
    assert detail.citation_label == "[E1]"
    assert detail.identity.chunk_id == identity.chunk_id
    assert "tenant_id" not in detail.model_dump_json()
    assert "access_scope" not in detail.model_dump_json()


def test_successful_citation_validation_contract_has_unique_mapping() -> None:
    context_id = uuid4()
    result = CitationValidationResult(
        context_id=context_id,
        citations=[
            ContextCitation(citation_label="[E1]", evidence_id=uuid4()),
            ContextCitation(citation_label="[E2]", evidence_id=uuid4()),
        ],
    )

    assert result.valid is True
    assert result.context_id == context_id

    with pytest.raises(ValidationError, match="citation labels"):
        CitationValidationResult(
            context_id=context_id,
            citations=[
                ContextCitation(citation_label="[E1]", evidence_id=uuid4()),
                ContextCitation(citation_label="[E1]", evidence_id=uuid4()),
            ],
        )


@pytest.mark.parametrize(
    ("error", "code", "retryable", "field"),
    (
        (ContextInputError(), "VALIDATION_ERROR", False, "context"),
        (ContextDataContractError(), "INTERNAL_ERROR", False, None),
        (ContextBuildError(), "INTERNAL_ERROR", True, None),
        (KnowledgeEvidencePersistenceError(), "INTERNAL_ERROR", True, None),
        (CitationValidationError(), "VALIDATION_ERROR", False, "citations"),
    ),
)
def test_context_errors_are_fixed_and_never_leak_raw_causes(
    error: ApplicationError,
    code: str,
    retryable: bool,
    field: str | None,
) -> None:
    hostile = RuntimeError(
        "tenant_id=secret; storage_key=private/object; SQL=SELECT * FROM evidence"
    )
    try:
        raise error from hostile
    except ApplicationError as captured:
        detail = captured.to_detail()

    assert detail.code == code
    assert detail.retryable is retryable
    assert detail.field == field
    rendered = detail.model_dump_json()
    for secret in ("tenant_id", "storage_key", "SELECT", "private/object"):
        assert secret not in rendered
