"""Pure edit decisions: transitions, punch-ins, and the caption clock."""

from __future__ import annotations

from app.transcript import Word, normalize_token

TRANSITIONS = {
    "funny": "slideright",
    "dramatic": "fadewhite",
    "informative": "smoothleft",
    "hype": "wipeleft",
    "emotional": "fade",
    "inspiring": "smoothup",
}

EMPHASIS = {
    "stop",
    "never",
    "secret",
    "biggest",
    "mistake",
    "wait",
    "dont",
    "don't",
    "always",
    "money",
    "dead",
    "insane",
    "crazy",
    "exactly",
    "worst",
    "kills",
    "kill",
    "warning",
    "nobody",
    "wrong",
    "lie",
}


def transition_for_mood(mood: str) -> str:
    return TRANSITIONS.get((mood or "").strip().lower(), "fade")


def xfade_offsets(durations: list[float], xfade: float) -> list[float]:
    offsets: list[float] = []
    for index in range(len(durations) - 1):
        offsets.append(sum(durations[: index + 1]) - xfade * (index + 1))
    return offsets


def emphasis_windows(
    words: list[Word],
    segment_start: float,
    segment_end: float,
) -> list[tuple[float, float]]:
    """Punch windows in seconds relative to the segment start. At most three."""
    span = segment_end - segment_start
    if span <= 0.2:
        return []
    windows: list[tuple[float, float]] = []
    for word in words:
        if word.end <= segment_start or word.start >= segment_end:
            continue
        token = normalize_token(word.text)
        if token not in EMPHASIS and "!" not in word.text:
            continue
        local = max(0.0, word.start - segment_start)
        punch = max(0.28, min(0.55, span - local))
        end = min(span, local + punch)
        if end - local >= 0.12:
            windows.append((round(local, 3), round(end, 3)))
    merged = _merge_windows(windows)
    return merged[:3]


def punch_chain(
    punches: list[tuple[float, float]],
    width: int,
    height: int,
    amount: float = 0.12,
) -> str:
    """FFmpeg filters that punch in and crop back to the frame size."""
    if not punches:
        return ""
    parts: list[str] = []
    for start, end in punches:
        span = max(0.05, end - start)
        parts.append(f"sin(PI*clip((t-{start:.3f})/{span:.3f}\\,0\\,1))")
    zoom = f"1+{amount}*({'+'.join(parts)})"
    return (
        f"scale=w='trunc(iw*({zoom})/2)*2':h='trunc(ih*({zoom})/2)*2':eval=frame,"
        f"crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2"
    )


def remap_words(
    words: list[Word],
    segments: list[tuple[float, float]],
    xfade: float,
) -> list[Word]:
    """Move source-time words onto the jump-cut output clock."""
    durations = [end - start for start, end in segments]
    remapped: list[Word] = []
    for index, (start, end) in enumerate(segments):
        origin = sum(durations[:index]) - xfade * index
        duration = durations[index]
        for word in words:
            midpoint = (word.start + word.end) / 2
            if not (start <= midpoint < end):
                continue
            local_start = max(0.0, word.start - start)
            local_end = min(duration, word.end - start)
            if local_end - local_start < 0.01:
                continue
            remapped.append(Word(word.text, origin + local_start, origin + local_end))
    remapped.sort(key=lambda word: (word.start, word.end))
    return remapped


def _merge_windows(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not windows:
        return []
    ordered = sorted(windows)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + 0.08:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]
