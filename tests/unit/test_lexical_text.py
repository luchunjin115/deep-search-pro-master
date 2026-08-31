from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from app.services.retrieval.lexical_text import (
    FTS_BUILDER_VERSION,
    FTS_TEXT_BUILDER_CONTRACT_VERSION,
    JIEBA_DICTIONARY_SHA256,
    JIEBA_VERSION,
    FtsTextBuilderError,
    FtsTextPurpose,
    build_fts_text,
    get_fts_text_builder,
)


def test_builder_identity_freezes_jieba_dictionary_and_rules() -> None:
    identity = get_fts_text_builder().identity

    assert asdict(identity) == {
        "contract_version": FTS_TEXT_BUILDER_CONTRACT_VERSION,
        "builder_version": FTS_BUILDER_VERSION,
        "tokenizer": "jieba",
        "tokenizer_version": JIEBA_VERSION,
        "dictionary_sha256": JIEBA_DICTIONARY_SHA256,
        "mode": "search",
        "hmm": False,
        "normalization": "nfkc-casefold-v1",
        "token_filter": "unicode-alnum-v1",
    }
    assert FTS_BUILDER_VERSION == "m2-fts-jieba-search-v1"
    assert JIEBA_VERSION == "0.42.1"
    assert JIEBA_DICTIONARY_SHA256 == (
        "7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8"
    )


def test_runtime_dependency_pins_the_same_jieba_version() -> None:
    requirements = {
        requirement.name.lower(): requirement
        for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for requirement in (Requirement(line),)
    }

    assert str(requirements["jieba"].specifier) == "==0.42.1"


def test_document_and_query_use_the_same_chinese_search_tokens() -> None:
    source = "蘑菇灯亮度调节说明"

    document = build_fts_text(source, purpose=FtsTextPurpose.DOCUMENT)
    query = build_fts_text(source, purpose=FtsTextPurpose.QUERY)

    assert document.text == "蘑菇 灯 亮度 调节 说明"
    assert query.text == document.text
    assert document.identity == query.identity
    assert document.purpose is FtsTextPurpose.DOCUMENT
    assert query.purpose is FtsTextPurpose.QUERY


def test_builder_preserves_searchable_english_sku_model_and_clause_parts() -> None:
    built = build_fts_text(
        "Ｍｕｓｈｒｏｏｍ lamp LR-TL-MUSH-OR01 220V 12W Amazon.de 条款 5.2",
        purpose=FtsTextPurpose.DOCUMENT,
    )

    assert built.text == ("mushroom lamp lr tl mush or01 220v 12w amazon de 条款 5 2")


def test_builder_removes_punctuation_but_keeps_order_and_term_frequency() -> None:
    built = build_fts_text(
        "库存，库存；DE-FRA！",
        purpose=FtsTextPurpose.QUERY,
    )

    assert built.text == "库存 库存 de fra"


def test_builder_is_deterministic_without_using_jieba_hmm_discovery() -> None:
    source = "超能蘑菇灯XQZ9988售后条款"

    first = build_fts_text(source, purpose=FtsTextPurpose.DOCUMENT)
    repeated = build_fts_text(source, purpose=FtsTextPurpose.DOCUMENT)

    assert first == repeated


@pytest.mark.parametrize("text", ("", " \t\r\n ", 123, True))
def test_builder_rejects_blank_or_non_string_input(text: object) -> None:
    with pytest.raises(FtsTextBuilderError, match="FTS input"):
        build_fts_text(text, purpose=FtsTextPurpose.QUERY)  # type: ignore[arg-type]


def test_builder_rejects_input_or_output_outside_storage_bound() -> None:
    with pytest.raises(FtsTextBuilderError, match="FTS input"):
        build_fts_text("文" * 2_000_001, purpose=FtsTextPurpose.DOCUMENT)
