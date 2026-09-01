from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import CitationValidationError, EvidenceReadError
from app.repositories.evidence import AuthorizedCitationContext
from app.schemas.auth import CurrentUser
from app.services.citations import CitationValidatorService


def _user() -> CurrentUser:
    return CurrentUser(
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="citation@example.com",
        display_name="Citation Tester",
        roles=["amazon_operator"],
        market_scopes=["DE"],
    )


class _Reader:
    def __init__(
        self,
        snapshot: AuthorizedCitationContext | None,
        *,
        fail: bool = False,
    ) -> None:
        self.snapshot = snapshot
        self.fail = fail
        self.calls: list[tuple[CurrentUser, object]] = []

    def load_authorized_citation_context(
        self,
        current_user: CurrentUser,
        context_id: object,
    ) -> AuthorizedCitationContext | None:
        self.calls.append((current_user, context_id))
        if self.fail:
            raise SQLAlchemyError("SQL SELECT tenant_id secret")
        return self.snapshot


def test_valid_subset_maps_labels_to_database_evidence_in_answer_order() -> None:
    user = _user()
    context_id = uuid4()
    evidence_ids = (uuid4(), uuid4(), uuid4())
    reader = _Reader(
        AuthorizedCitationContext(
            context_id=context_id,
            evidence_ids=evidence_ids,
        )
    )

    result = CitationValidatorService(reader).validate_answer(
        user,
        context_id,
        "先看限制 [E3]，再看基础规则 [E1]。",
    )

    assert result.context_id == context_id
    assert [item.citation_label for item in result.citations] == ["[E3]", "[E1]"]
    assert [item.evidence_id for item in result.citations] == [
        evidence_ids[2],
        evidence_ids[0],
    ]


@pytest.mark.parametrize(
    "answer",
    (
        "没有引用",
        "重复引用 [E1] 和 [E1]",
        "越界引用 [E0]",
        "越界引用 [E13]",
        "编造引用 [E99]",
        "错误大小写 [e1]",
        "错误空格 [E 1]",
        "全角引用 ［E1］",
        "缺少右括号 [E1",
    ),
)
def test_supported_context_rejects_missing_duplicate_or_malformed_labels(
    answer: str,
) -> None:
    context_id = uuid4()
    reader = _Reader(
        AuthorizedCitationContext(context_id=context_id, evidence_ids=(uuid4(),))
    )

    with pytest.raises(CitationValidationError):
        CitationValidatorService(reader).validate_answer(_user(), context_id, answer)


def test_empty_context_accepts_no_citation_but_rejects_any_claimed_label() -> None:
    context_id = uuid4()
    reader = _Reader(AuthorizedCitationContext(context_id=context_id, evidence_ids=()))
    service = CitationValidatorService(reader)

    result = service.validate_answer(_user(), context_id, "未找到可支持答案的资料。")
    assert result.citations == []

    with pytest.raises(CitationValidationError):
        service.validate_answer(_user(), context_id, "仍然引用 [E1]")


def test_absent_context_and_database_failure_use_safe_typed_errors() -> None:
    user = _user()
    context_id = uuid4()
    with pytest.raises(CitationValidationError):
        CitationValidatorService(_Reader(None)).validate_answer(
            user,
            context_id,
            "引用 [E1]",
        )

    with pytest.raises(EvidenceReadError) as captured:
        CitationValidatorService(_Reader(None, fail=True)).validate_answer(
            user,
            context_id,
            "引用 [E1]",
        )
    assert "SELECT" not in captured.value.to_detail().model_dump_json()


@pytest.mark.parametrize(
    "answer",
    ("", "   ", "x" * 100_001),
    ids=("empty", "whitespace", "too_long"),
)
def test_answer_input_is_bounded(answer: str) -> None:
    with pytest.raises(CitationValidationError):
        CitationValidatorService(_Reader(None)).validate_answer(
            _user(),
            uuid4(),
            answer,
        )
