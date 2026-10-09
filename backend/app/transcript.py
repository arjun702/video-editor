"""Word timings and small pieces of timestamp math."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", token.lower())


def merge_ranges(
    ranges: list[tuple[float, float]],
    gap: float = 0.0,
) -> list[tuple[float, float]]:
    if not ranges:
        return []
    ordered = sorted((float(a), float(b)) for a, b in ranges)
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def words_in_range(words: list[Word], start: float, end: float) -> list[Word]:
    """Words that overlap [start, end). A word ending on start still counts; one starting on end does not."""
    return [word for word in words if word.start < end and word.end >= start]


def snap_range_to_words(
    start: float,
    end: float,
    words: list[Word],
) -> tuple[float, float]:
    inside = words_in_range(words, start, end)
    if not inside:
        return (start, end)
    return (min(word.start for word in inside), max(word.end for word in inside))


def shift_words(words: list[Word], delta: float) -> list[Word]:
    return [Word(word.text, word.start + delta, word.end + delta) for word in words]
