"""Drop filler words and long pauses so a clip can jump-cut."""

from __future__ import annotations

from app.transcript import Word, clamp, merge_ranges, normalize_token

FILLER_TOKENS = {"um", "uh", "er", "ah", "uhm", "umm", "hmm", "mhm", "uhh"}
FILLER_PHRASES = {("you", "know"), ("i", "mean"), ("kind", "of"), ("sort", "of")}


def trim_fillers_and_silence(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    *,
    max_gap: float = 0.4,
    pad: float = 0.04,
    min_keep: float = 0.12,
    hold: float = 0.0,
    protect: float = 0.0,
) -> list[tuple[float, float]]:
    """Return source-time ranges to keep inside [clip_start, clip_end]."""
    selected = [
        word
        for word in words
        if word.start < clip_end and word.end > clip_start
    ]
    selected.sort(key=lambda word: word.start)

    kept: list[Word] = []
    index = 0
    while index < len(selected):
        current = normalize_token(selected[index].text)
        if index + 1 < len(selected):
            nxt = selected[index + 1]
            pair = (current, normalize_token(nxt.text))
            gap = nxt.start - selected[index].end
            if pair in FILLER_PHRASES and gap <= 0.35:
                index += 2
                continue
        if current in FILLER_TOKENS:
            index += 1
            continue
        kept.append(selected[index])
        index += 1

    if not kept:
        return []

    ranges: list[tuple[float, float]] = []
    start = kept[0].start
    end = kept[0].end
    for prev, nxt in zip(kept, kept[1:]):
        if nxt.start - prev.end > max_gap:
            ranges.append((start, end))
            start = nxt.start
        end = nxt.end
    ranges.append((start, end))

    padded: list[tuple[float, float]] = []
    for start, end in ranges:
        if end - start < min_keep:
            continue
        left = clamp(start - pad, clip_start, clip_end)
        right = clamp(end + pad, clip_start, clip_end)
        if right - left > 0:
            padded.append((left, right))
    if hold > 0 and padded:
        left, right = padded[-1]
        padded[-1] = (left, clamp(right + hold, clip_start, clip_end))
    if protect > 0:
        head_end = min(clip_end, clip_start + protect)
        tail_start = max(clip_start, clip_end - protect)
        padded = [(clip_start, head_end), *padded, (tail_start, clip_end)]
    return merge_ranges(padded, gap=0.0)
