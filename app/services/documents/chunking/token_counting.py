"""Deterministic, model-free token counting for M2 structure-aware chunking."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

TOKEN_COUNTER_NAME = "unicode_mixed"
TOKEN_COUNTER_VERSION = "m2-unicode-token-counter-v1"
_WORD_PIECE_LENGTH = 4


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """One counted unit and its offsets in NFC-normalized text."""

    text: str
    start: int
    end: int


@runtime_checkable
class TokenCounter(Protocol):
    """Versioned boundary used by chunking without loading an embedding model."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def spans(self, text: str) -> tuple[TokenSpan, ...]: ...

    def count(self, text: str) -> int: ...


class UnicodeMixedTokenCounter:
    """Count CJK characters, bounded word pieces, and punctuation deterministically.

    This is an explicit chunk-size unit, not a claim about BGE-M3's tokenizer.
    M2-14 may introduce a new counter version and regenerate a new Chunk Set.
    """

    @property
    def name(self) -> str:
        return TOKEN_COUNTER_NAME

    @property
    def version(self) -> str:
        return TOKEN_COUNTER_VERSION

    def spans(self, text: str) -> tuple[TokenSpan, ...]:
        normalized = unicodedata.normalize("NFC", text)
        tokens: list[TokenSpan] = []
        index = 0
        while index < len(normalized):
            character = normalized[index]
            if character.isspace():
                index += 1
                continue
            if _is_cjk_character(character):
                tokens.append(TokenSpan(character, index, index + 1))
                index += 1
                continue
            if _is_word_character(character):
                run_end = index + 1
                while run_end < len(normalized) and _is_word_character(
                    normalized[run_end]
                ):
                    run_end += 1
                piece_start = index
                while piece_start < run_end:
                    piece_end = min(piece_start + _WORD_PIECE_LENGTH, run_end)
                    tokens.append(
                        TokenSpan(
                            normalized[piece_start:piece_end],
                            piece_start,
                            piece_end,
                        )
                    )
                    piece_start = piece_end
                index = run_end
                continue
            tokens.append(TokenSpan(character, index, index + 1))
            index += 1
        return tuple(tokens)

    def count(self, text: str) -> int:
        return len(self.spans(text))


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _is_cjk_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )
