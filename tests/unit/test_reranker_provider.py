from __future__ import annotations

import ast
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path
from typing import cast

import pytest

from app.core.errors import RerankerInputError, RerankerProviderError
from app.schemas.retrieval import RetrievalRerankerIdentity
from app.services.retrieval.reranker_provider import (
    RERANKER_CONTRACT_VERSION,
    RERANKER_MAX_CANDIDATES,
    RERANKER_MAX_PASSAGE_CHARACTERS,
    RERANKER_MAX_QUERY_CHARACTERS,
    FakeRerankerProvider,
    RerankerBatch,
    RerankerPairScore,
    RerankerProvider,
    build_reranker_pair_key,
    validate_reranker_batch,
)

QUERY = "蘑菇灯在德国仓还有多少可售库存？"
PASSAGES = (
    "LR-TL-MUSH-OR01 在 DE-FRA 的可售库存为 125。",
    "这段正文讨论法国站点的补货安排。",
)


def test_fake_reranker_is_deterministic_finite_and_keeps_pair_order() -> None:
    provider = FakeRerankerProvider()

    first = provider.score(QUERY, PASSAGES)
    second = FakeRerankerProvider().score(QUERY, PASSAGES)
    individual_raw_scores = tuple(
        provider.score(QUERY, [passage]).scores[0].raw_score for passage in PASSAGES
    )

    assert first == second
    assert tuple(score.raw_score for score in first.scores) == individual_raw_scores
    assert len(first.scores) == len(PASSAGES)
    assert first.effective_batch_size == len(PASSAGES)
    assert all(math.isfinite(score.raw_score) for score in first.scores)
    assert all(0 < score.normalized_score < 1 for score in first.scores)
    assert all(
        math.isclose(
            score.normalized_score,
            _sigmoid(score.raw_score),
            rel_tol=0,
            abs_tol=1e-12,
        )
        for score in first.scores
    )


def test_fake_reranker_identity_matches_the_public_contract() -> None:
    identity = FakeRerankerProvider().identity

    assert identity.contract_version == RERANKER_CONTRACT_VERSION
    assert identity.provider == "fake"
    assert identity.model_id == "fake/m2-reranker-deterministic"
    assert identity.revision == "m2-fake-reranker-v1"
    assert identity.max_length == 8192
    assert identity.precision == "float32"
    assert identity.score_transform == "sigmoid"
    assert RetrievalRerankerIdentity.model_validate(asdict(identity))


def test_fake_reranker_keeps_the_v1_golden_score_contract() -> None:
    result = FakeRerankerProvider().score(QUERY, PASSAGES)

    assert tuple(score.pair_key for score in result.scores) == (
        "sha256:fbcd3c83eae1d140aa1d6aad3858b92a94dc8d749ae4abd204770b61418fd8ea",
        "sha256:9e1f76fb1d9ab0d1208a0b407bc0c8dc302a9c4b5f85232c708101b874bd2d82",
    )
    assert tuple(score.raw_score for score in result.scores) == (
        7.147274208218585,
        -6.453069090270782,
    )


def test_pair_keys_bind_identity_query_passage_and_original_position() -> None:
    provider = FakeRerankerProvider()
    first = provider.score(QUERY, PASSAGES)
    reversed_result = provider.score(QUERY, tuple(reversed(PASSAGES)))
    duplicates = provider.score(QUERY, [PASSAGES[0], PASSAGES[0]])

    assert tuple(score.pair_key for score in first.scores) == tuple(
        build_reranker_pair_key(provider.identity, QUERY, passage, position)
        for position, passage in enumerate(PASSAGES)
    )
    assert tuple(score.pair_key for score in first.scores) != tuple(
        score.pair_key for score in reversed_result.scores
    )
    assert duplicates.scores[0].raw_score == duplicates.scores[1].raw_score
    assert duplicates.scores[0].pair_key != duplicates.scores[1].pair_key
    assert all(score.pair_key.startswith("sha256:") for score in first.scores)
    assert all(QUERY not in score.pair_key for score in first.scores)
    assert all(
        passage not in score.pair_key for score in first.scores for passage in PASSAGES
    )


def test_fake_reranker_satisfies_the_replaceable_provider_protocol() -> None:
    provider: RerankerProvider = FakeRerankerProvider()

    assert provider.score(QUERY, PASSAGES).identity == provider.identity


@pytest.mark.parametrize(
    "query",
    [
        "",
        " \t\n",
        "x" * (RERANKER_MAX_QUERY_CHARACTERS + 1),
        42,
        b"secret",
    ],
)
def test_fake_reranker_rejects_invalid_or_unbounded_query(query: object) -> None:
    with pytest.raises(RerankerInputError) as captured:
        FakeRerankerProvider().score(query, PASSAGES)  # type: ignore[arg-type]

    assert captured.value.field == "query"


@pytest.mark.parametrize(
    "passages",
    [
        [],
        "one string is not a passage sequence",
        [""],
        [" \t\n"],
        [42],
        [b"secret"],
        ["x"] * (RERANKER_MAX_CANDIDATES + 1),
        ["x" * (RERANKER_MAX_PASSAGE_CHARACTERS + 1)],
    ],
)
def test_fake_reranker_rejects_invalid_or_unbounded_passages(
    passages: object,
) -> None:
    with pytest.raises(RerankerInputError) as captured:
        FakeRerankerProvider().score(QUERY, passages)  # type: ignore[arg-type]

    assert captured.value.field == "passages"


def test_batch_validator_accepts_the_exact_original_pairs() -> None:
    provider = FakeRerankerProvider()
    batch = provider.score(QUERY, PASSAGES)

    assert (
        validate_reranker_batch(
            batch,
            query=QUERY,
            passages=PASSAGES,
            expected_identity=provider.identity,
        )
        == batch
    )


def test_batch_validator_rejects_count_and_order_mismatches() -> None:
    provider = FakeRerankerProvider()
    batch = provider.score(QUERY, PASSAGES)
    missing = replace(batch, scores=batch.scores[:1])
    reversed_scores = replace(batch, scores=tuple(reversed(batch.scores)))

    for malformed in (missing, reversed_scores):
        with pytest.raises(RerankerProviderError):
            validate_reranker_batch(
                malformed,
                query=QUERY,
                passages=PASSAGES,
                expected_identity=provider.identity,
            )


@pytest.mark.parametrize(
    ("raw_score", "normalized_score"),
    [
        (math.nan, 0.5),
        (math.inf, 0.5),
        (0.0, math.nan),
        (0.0, math.inf),
        (0.0, -0.1),
        (0.0, 1.1),
        (0.0, 0.75),
        (True, 0.5),
    ],
)
def test_batch_validator_rejects_nonfinite_or_inconsistent_scores(
    raw_score: object,
    normalized_score: object,
) -> None:
    provider = FakeRerankerProvider()
    valid = provider.score(QUERY, PASSAGES)
    malformed_score = replace(
        valid.scores[0],
        raw_score=raw_score,  # type: ignore[arg-type]
        normalized_score=normalized_score,  # type: ignore[arg-type]
    )
    malformed = replace(valid, scores=(malformed_score, valid.scores[1]))

    with pytest.raises(RerankerProviderError):
        validate_reranker_batch(
            malformed,
            query=QUERY,
            passages=PASSAGES,
            expected_identity=provider.identity,
        )


def test_batch_validator_rejects_wrong_identity_or_shape() -> None:
    provider = FakeRerankerProvider()
    batch = provider.score(QUERY, PASSAGES)

    with pytest.raises(RerankerProviderError):
        validate_reranker_batch(
            replace(batch, identity=replace(batch.identity, revision="wrong")),
            query=QUERY,
            passages=PASSAGES,
            expected_identity=provider.identity,
        )
    malformed_batch = cast(RerankerBatch, object())
    with pytest.raises(RerankerProviderError):
        validate_reranker_batch(
            malformed_batch,
            query=QUERY,
            passages=PASSAGES,
            expected_identity=provider.identity,
        )


def test_provider_batch_and_scores_are_immutable() -> None:
    provider = FakeRerankerProvider()
    batch = provider.score(QUERY, PASSAGES)

    with pytest.raises(FrozenInstanceError):
        batch.effective_batch_size = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        batch.scores[0].raw_score = 99  # type: ignore[misc]


def test_fake_reranker_is_stable_under_concurrent_first_use() -> None:
    provider = FakeRerankerProvider()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda _: provider.score(QUERY, PASSAGES), range(32))
        )

    assert all(result == results[0] for result in results)


def test_reranker_errors_are_fixed_and_do_not_leak_inputs_or_runtime_details() -> None:
    input_error = RerankerInputError(field="query")
    provider_error = RerankerProviderError(retryable=True)

    assert input_error.code == "VALIDATION_ERROR"
    assert input_error.retryable is False
    assert input_error.field == "query"
    assert QUERY not in str(input_error)
    assert provider_error.code == "PROVIDER_ERROR"
    assert provider_error.retryable is True
    assert "CUDA" not in str(provider_error)
    assert "C:\\private\\model" not in str(provider_error)


def test_importing_provider_module_has_no_eager_model_or_network_dependency() -> None:
    source = (
        Path(__file__).parents[2] / "app/services/retrieval/reranker_provider.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level_roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_roots.add(node.module.split(".", 1)[0])

    assert top_level_roots.isdisjoint(
        {
            "FlagEmbedding",
            "transformers",
            "torch",
            "huggingface_hub",
            "requests",
            "httpx",
        }
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)


def _unused_type_examples(
    batch: RerankerBatch,
    score: RerankerPairScore,
) -> tuple[RerankerBatch, RerankerPairScore]:
    """Keep the public dataclasses visible to static analysis in this contract test."""

    return batch, score
