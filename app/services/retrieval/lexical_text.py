"""Versioned deterministic jieba text preparation shared by indexing and queries."""

from __future__ import annotations

import hashlib
import importlib.metadata
import threading
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final

import jieba  # type: ignore[import-untyped]

FTS_TEXT_BUILDER_CONTRACT_VERSION: Final = "m2-fts-text-builder-v1"
FTS_BUILDER_VERSION: Final = "m2-fts-jieba-search-v1"
JIEBA_VERSION: Final = "0.42.1"
JIEBA_DICTIONARY_SHA256: Final = (
    "7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8"
)
FTS_MAX_TEXT_CHARACTERS: Final = 2_000_000


class FtsTextPurpose(StrEnum):
    """Document and query text intentionally share one tokenization rule."""

    DOCUMENT = "document"
    QUERY = "query"


@dataclass(frozen=True, slots=True)
class FtsTextBuilderIdentity:
    """Every fixed setting capable of changing the generated FTS text."""

    contract_version: str
    builder_version: str
    tokenizer: str
    tokenizer_version: str
    dictionary_sha256: str
    mode: str
    hmm: bool
    normalization: str
    token_filter: str


@dataclass(frozen=True, slots=True)
class BuiltFtsText:
    """Prepared text plus the purpose and builder identity used to create it."""

    text: str
    purpose: FtsTextPurpose
    identity: FtsTextBuilderIdentity


class FtsTextBuilderError(ValueError):
    """Input or local tokenizer files cannot satisfy the frozen FTS contract."""


class JiebaFtsTextBuilder:
    """Isolated search-mode tokenizer with no global words or HMM discovery."""

    def __init__(self) -> None:
        dictionary_path = _validated_dictionary_path()
        self._tokenizer = jieba.Tokenizer(str(dictionary_path))
        self._lock = threading.Lock()
        self._identity = FtsTextBuilderIdentity(
            contract_version=FTS_TEXT_BUILDER_CONTRACT_VERSION,
            builder_version=FTS_BUILDER_VERSION,
            tokenizer="jieba",
            tokenizer_version=JIEBA_VERSION,
            dictionary_sha256=JIEBA_DICTIONARY_SHA256,
            mode="search",
            hmm=False,
            normalization="nfkc-casefold-v1",
            token_filter="unicode-alnum-v1",
        )

    @property
    def identity(self) -> FtsTextBuilderIdentity:
        return self._identity

    def build(self, text: str, *, purpose: FtsTextPurpose) -> BuiltFtsText:
        """Normalize, tokenize, filter punctuation, and preserve token order."""

        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > FTS_MAX_TEXT_CHARACTERS
            or not isinstance(purpose, FtsTextPurpose)
        ):
            raise FtsTextBuilderError("FTS input is outside the bounded contract")

        normalized = unicodedata.normalize("NFKC", text).casefold().strip()
        with self._lock:
            raw_tokens = tuple(self._tokenizer.cut_for_search(normalized, HMM=False))
        tokens = tuple(
            token.strip()
            for token in raw_tokens
            if token.strip() and any(character.isalnum() for character in token)
        )
        built = " ".join(tokens)
        if not built or len(built) > FTS_MAX_TEXT_CHARACTERS:
            raise FtsTextBuilderError("FTS output is outside the bounded contract")
        return BuiltFtsText(text=built, purpose=purpose, identity=self.identity)


@lru_cache
def get_fts_text_builder() -> JiebaFtsTextBuilder:
    """Reuse one verified isolated tokenizer instead of rebuilding its trie."""

    return JiebaFtsTextBuilder()


def build_fts_text(text: str, *, purpose: FtsTextPurpose) -> BuiltFtsText:
    """Shared entry point for both document indexing and future query building."""

    return get_fts_text_builder().build(text, purpose=purpose)


def _validated_dictionary_path() -> Path:
    try:
        installed_version = importlib.metadata.version("jieba")
        module_path = Path(jieba.__file__).resolve()
        dictionary_path = module_path.with_name("dict.txt")
        dictionary_sha256 = hashlib.sha256(dictionary_path.read_bytes()).hexdigest()
    except (OSError, TypeError, importlib.metadata.PackageNotFoundError):
        raise FtsTextBuilderError("FTS tokenizer files are unavailable") from None
    if installed_version != JIEBA_VERSION:
        raise FtsTextBuilderError("FTS tokenizer version does not match the contract")
    if dictionary_sha256 != JIEBA_DICTIONARY_SHA256:
        raise FtsTextBuilderError("FTS dictionary does not match the contract")
    return dictionary_path
