from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import EvidenceNotFoundError, EvidenceReadError
from app.models.runtime import Evidence
from app.repositories.evidence import AuthorizedDocumentEvidence
from app.schemas.auth import CurrentUser
from app.schemas.evidence import GetEvidenceDetailInput, ToolDocumentEvidenceDetail
from app.services.evidence import EvidenceQueryService

_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="evidence-reader@example.com",
        display_name="Evidence Reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def _database_row(user: CurrentUser, evidence_id: UUID | None = None) -> Evidence:
    snapshot_id = uuid4()
    return Evidence(
        id=evidence_id or uuid4(),
        tenant_id=user.tenant_id,
        agent_run_id=uuid4(),
        tool_call_id=uuid4(),
        evidence_schema_version="m1-database-evidence-v1",
        source_type="database",
        source_name="synthetic_inventory",
        source_locator=f"inventory_snapshots/{snapshot_id}",
        title="德国仓合成库存",
        excerpt="SKU LR-TL-MUSH-OR01可售库存125件",
        query_summary={
            "sku": "LR-TL-MUSH-OR01",
            "market_code": "DE",
            "warehouse_code": "DE-FRA",
        },
        structured_data={
            "sku": "LR-TL-MUSH-OR01",
            "product_name": "合成蘑菇灯",
            "market_code": "DE",
            "warehouse_code": "DE-FRA",
            "warehouse_name": "德国法兰克福合成仓",
            "on_hand": 150,
            "reserved": 20,
            "unsellable": 5,
            "available": 125,
            "inbound": 10,
            "safety_stock": 30,
            "snapshot_at": _NOW.isoformat(),
            "synthetic_data": True,
        },
        observed_at=_NOW,
        confidence=Decimal("1.000"),
        trust_level="internal_demo",
        access_scope={"tenant_id": str(user.tenant_id), "market_codes": ["DE"]},
        synthetic_data=True,
        created_at=_NOW,
    )


def _document_row(user: CurrentUser, evidence_id: UUID | None = None) -> Evidence:
    return Evidence(
        id=evidence_id or uuid4(),
        tenant_id=user.tenant_id,
        evidence_schema_version="m2-document-evidence-v1",
        source_type="knowledge",
        source_name="document_chunk",
        title="合成说明书",
        excerpt="清洁前必须断开电源。",
        observed_at=_NOW,
        trust_level="document_snapshot",
        context_artifact_id=uuid4(),
        citation_ordinal=1,
        file_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_chunk_set_id=uuid4(),
        document_index_set_id=uuid4(),
        document_chunk_id=uuid4(),
        source_content_sha256="a" * 64,
        context_text_sha256="b" * 64,
        source_locator_json={"source_type": "pdf", "page_number": 2},
        synthetic_data=True,
        created_at=_NOW,
    )


def _authorized_document(
    user: CurrentUser,
    evidence_id: UUID | None = None,
    *,
    source_locator: dict[str, object] | None = None,
) -> AuthorizedDocumentEvidence:
    return AuthorizedDocumentEvidence(
        id=evidence_id or uuid4(),
        source_type="knowledge",
        file_id=uuid4(),
        context_id=uuid4(),
        citation_ordinal=1,
        document_id=uuid4(),
        document_version_id=uuid4(),
        document_index_set_id=uuid4(),
        document_chunk_id=uuid4(),
        title="合成说明书",
        excerpt="清洁前必须断开电源。",
        observed_at=_NOW,
        document_title="合成说明书",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        source_locator=source_locator or {"source_type": "pdf", "page_number": 2},
        source_content_sha256="a" * 64,
        context_text_sha256="b" * 64,
        created_at=_NOW,
    )


class FakeEvidenceReader:
    def __init__(
        self,
        row: Evidence | None,
        document: AuthorizedDocumentEvidence | None = None,
        *,
        find_failure: Exception | None = None,
        document_failure: Exception | None = None,
    ) -> None:
        self.row = row
        self.document = document
        self.find_failure = find_failure
        self.document_failure = document_failure
        self.find_calls: list[dict[str, UUID]] = []
        self.document_calls: list[tuple[CurrentUser, UUID]] = []

    def find_by_id(self, *, tenant_id: UUID, evidence_id: UUID) -> Evidence | None:
        self.find_calls.append({"tenant_id": tenant_id, "evidence_id": evidence_id})
        if self.find_failure is not None:
            raise self.find_failure
        return self.row

    def find_authorized_document_by_id(
        self,
        current_user: CurrentUser,
        evidence_id: UUID,
    ) -> AuthorizedDocumentEvidence | None:
        self.document_calls.append((current_user, evidence_id))
        if self.document_failure is not None:
            raise self.document_failure
        return self.document


def test_existing_m1_detail_and_summary_behavior_stays_database_only() -> None:
    user = _user()
    row = _database_row(user)
    repository = FakeEvidenceReader(row)
    service = EvidenceQueryService(repository)

    detail = service.get_detail(user, row.id)
    summaries = service.get_summaries(user, [row.id])

    assert detail.id == row.id
    assert detail.source_type == "database"
    assert detail.structured_data.available == 125
    assert summaries[0].id == row.id
    assert repository.document_calls == []


def test_tool_detail_reuses_the_existing_m1_database_contract() -> None:
    user = _user()
    row = _database_row(user)
    service = EvidenceQueryService(FakeEvidenceReader(row))

    result = service.get_tool_detail(
        user,
        GetEvidenceDetailInput(evidence_id=row.id),
    )

    assert result.evidence_id == row.id
    assert result.detail.source_type == "database"
    assert result.detail.structured_data.available == 125


def test_tool_detail_builds_public_document_contract_from_authorized_record() -> None:
    user = _user()
    row = _document_row(user)
    authorized = _authorized_document(user, row.id)
    repository = FakeEvidenceReader(row, authorized)

    result = EvidenceQueryService(repository).get_tool_detail(
        user,
        GetEvidenceDetailInput(evidence_id=row.id),
    )

    assert isinstance(result.detail, ToolDocumentEvidenceDetail)
    assert result.detail.id == row.id
    assert result.detail.file_id == authorized.file_id
    assert result.detail.citation_label == "[E1]"
    assert result.detail.identity.document_id == authorized.document_id
    assert result.detail.identity.version_id == authorized.document_version_id
    assert result.detail.identity.index_set_id == authorized.document_index_set_id
    assert result.detail.identity.chunk_id == authorized.document_chunk_id
    assert result.detail.document.title == authorized.document_title
    serialized = result.model_dump_json()
    for private_value in (str(user.tenant_id), "owner", "storage_key", "sql"):
        assert private_value not in serialized.lower()


def test_existing_m1_detail_hides_document_evidence_from_the_http_path() -> None:
    user = _user()
    row = _document_row(user)
    repository = FakeEvidenceReader(row, _authorized_document(user, row.id))

    with pytest.raises(EvidenceNotFoundError):
        EvidenceQueryService(repository).get_detail(user, row.id)

    assert repository.document_calls == []


def test_missing_or_unauthorized_document_is_indistinguishable() -> None:
    user = _user()
    evidence_id = uuid4()
    row = _document_row(user, evidence_id)

    with pytest.raises(EvidenceNotFoundError):
        EvidenceQueryService(FakeEvidenceReader(None)).get_tool_detail(
            user,
            GetEvidenceDetailInput(evidence_id=evidence_id),
        )
    with pytest.raises(EvidenceNotFoundError):
        EvidenceQueryService(FakeEvidenceReader(row, None)).get_tool_detail(
            user,
            GetEvidenceDetailInput(evidence_id=evidence_id),
        )


def test_invalid_authorized_document_facts_become_safe_read_error() -> None:
    user = _user()
    row = _document_row(user)
    malformed = _authorized_document(
        user,
        row.id,
        source_locator={"source_type": "pdf"},
    )

    with pytest.raises(EvidenceReadError) as captured:
        EvidenceQueryService(FakeEvidenceReader(row, malformed)).get_tool_detail(
            user,
            GetEvidenceDetailInput(evidence_id=row.id),
        )

    assert captured.value.code == "INTERNAL_ERROR"
    assert "locator" not in captured.value.message.lower()


@pytest.mark.parametrize("failure_at", ("lookup", "document"))
def test_database_failures_are_sanitized(failure_at: str) -> None:
    user = _user()
    row = _document_row(user)
    private_error = SQLAlchemyError("password=secret SQL=SELECT * FROM evidences")
    repository = FakeEvidenceReader(
        row,
        _authorized_document(user, row.id),
        find_failure=private_error if failure_at == "lookup" else None,
        document_failure=private_error if failure_at == "document" else None,
    )

    with pytest.raises(EvidenceReadError) as captured:
        EvidenceQueryService(repository).get_tool_detail(
            user,
            GetEvidenceDetailInput(evidence_id=row.id),
        )

    assert "secret" not in captured.value.message
    assert "SELECT" not in captured.value.message
