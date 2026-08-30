"""Deterministic text normalization with Canonical Block offset tracking."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCharacter:
    """One normalized character and its half-open source character range."""

    text: str
    source_start: int
    source_end: int


@dataclass(frozen=True, slots=True)
class NormalizedSourceText:
    """Normalized text whose characters remain traceable to Canonical text."""

    text: str
    characters: tuple[SourceCharacter, ...]

    def source_range(self, start: int, end: int) -> tuple[int, int]:
        if start < 0 or end > len(self.characters) or start >= end:
            raise ValueError("normalized source range must be non-empty and in bounds")
        return (
            self.characters[start].source_start,
            self.characters[end - 1].source_end,
        )


def normalize_source_text(value: str) -> NormalizedSourceText:
    """Normalize Unicode/newlines and insignificant edge whitespace reproducibly.

    The returned source ranges always point into the exact text stored in the
    Canonical Parsed Artifact. This lets later answer citations survive cleaning.
    """

    characters = _normalize_line_endings(value)
    characters = _normalize_unicode_clusters(characters)
    characters = _trim_line_ends(characters)
    characters = _collapse_blank_lines(characters)
    characters = _trim_document_edges(characters)
    return NormalizedSourceText(
        text="".join(character.text for character in characters),
        characters=tuple(characters),
    )


def _normalize_line_endings(value: str) -> list[SourceCharacter]:
    characters: list[SourceCharacter] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\r":
            source_end = index + 2 if value[index : index + 2] == "\r\n" else index + 1
            characters.append(SourceCharacter("\n", index, source_end))
            index = source_end
            continue
        characters.append(
            SourceCharacter(
                " " if character == "\u00a0" else character, index, index + 1
            )
        )
        index += 1
    return characters


def _normalize_unicode_clusters(
    characters: list[SourceCharacter],
) -> list[SourceCharacter]:
    normalized: list[SourceCharacter] = []
    cluster: list[SourceCharacter] = []

    def flush() -> None:
        if not cluster:
            return
        source_start = cluster[0].source_start
        source_end = cluster[-1].source_end
        text = unicodedata.normalize("NFC", "".join(item.text for item in cluster))
        normalized.extend(
            SourceCharacter(character, source_start, source_end) for character in text
        )
        cluster.clear()

    for character in characters:
        if cluster and unicodedata.combining(character.text) == 0:
            flush()
        cluster.append(character)
    flush()
    return normalized


def _trim_line_ends(characters: list[SourceCharacter]) -> list[SourceCharacter]:
    result: list[SourceCharacter] = []
    line: list[SourceCharacter] = []
    for character in characters:
        if character.text != "\n":
            line.append(character)
            continue
        while line and line[-1].text in {" ", "\t"}:
            line.pop()
        result.extend(line)
        result.append(character)
        line = []
    while line and line[-1].text in {" ", "\t"}:
        line.pop()
    result.extend(line)
    return result


def _collapse_blank_lines(
    characters: list[SourceCharacter],
) -> list[SourceCharacter]:
    result: list[SourceCharacter] = []
    consecutive_newlines = 0
    for character in characters:
        if character.text == "\n":
            consecutive_newlines += 1
            if consecutive_newlines > 2:
                continue
        else:
            consecutive_newlines = 0
        result.append(character)
    return result


def _trim_document_edges(
    characters: list[SourceCharacter],
) -> list[SourceCharacter]:
    start = 0
    end = len(characters)
    while start < end and characters[start].text.isspace():
        start += 1
    while end > start and characters[end - 1].text.isspace():
        end -= 1
    return characters[start:end]
