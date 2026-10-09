"""Parse model-picked hooks, and rank them locally when no API key is set."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.silence import FILLER_TOKENS
from app.transcript import Word, clamp, normalize_token

MOODS = ("funny", "dramatic", "informative", "hype", "emotional", "inspiring")

HOOK_WEIGHTS = {
    "stop": 2.5,
    "mistake": 3.0,
    "kills": 2.5,
    "kill": 2.5,
    "secret": 3.0,
    "nobody": 2.0,
    "never": 2.0,
    "worst": 2.0,
    "wait": 2.0,
    "warning": 2.0,
    "runway": 1.5,
    "hiring": 1.2,
    "biggest": 1.5,
    "scrolling": 1.0,
    "insane": 2.0,
    "crazy": 1.5,
    "truth": 2.0,
    "wrong": 2.0,
    "lie": 2.0,
    "money": 1.5,
    "don't": 1.5,
    "dont": 1.5,
    "dead": 2.0,
}

MOOD_WORDS = {
    "funny": {"funny", "laugh", "joke", "hilarious", "lol"},
    "hype": {"stop", "wait", "insane", "crazy", "secret", "hack"},
    "dramatic": {"mistake", "kill", "kills", "dead", "worst", "never", "warning", "runway"},
    "emotional": {"love", "cry", "lost", "afraid", "heart"},
    "inspiring": {"dream", "possible", "build", "believe"},
    "informative": {"how", "why", "because", "means"},
}


@dataclass(frozen=True)
class Highlight:
    start: float
    end: float
    hook_score: float
    reason: str
    title: str
    mood: str


def parse_highlight_response(
    text: str,
    *,
    duration: float,
    min_len: float,
    max_len: float,
    limit: int,
) -> list[Highlight]:
    payload = _extract_json(text)
    if payload is None:
        return []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("clips")
            or payload.get("highlights")
            or payload.get("moments")
            or []
        )
    else:
        return []

    parsed: list[Highlight] = []
    for item in items:
        highlight = _coerce_highlight(item, duration=duration, min_len=min_len, max_len=max_len)
        if highlight is not None:
            parsed.append(highlight)
    return _take_non_overlapping(parsed, limit)


def heuristic_highlights(
    words: list[Word],
    *,
    duration: float,
    min_len: float,
    max_len: float,
    count: int,
    energy: list[tuple[float, float]] | None = None,
    scenes: list[float] | None = None,
) -> list[Highlight]:
    if duration <= 0 or count <= 0:
        return []
    if not words:
        return []

    if duration < min_len:
        windows = [(0.0, duration)]
    else:
        windows = _candidate_windows(words, duration, min_len, max_len)

    ranked: list[Highlight] = []
    for start, end in windows:
        chunk = [word for word in words if word.start < end and word.end > start]
        if not chunk:
            continue
        raw = _raw_score(chunk, start, end, energy=energy, scenes=scenes)
        ranked.append(
            Highlight(
                start=round(start, 3),
                end=round(end, 3),
                hook_score=_public_score(raw),
                reason=_reason(chunk, energy=energy, scenes=scenes, start=start),
                title=_title(chunk),
                mood=infer_mood(" ".join(word.text for word in chunk)),
            )
        )
    return _take_non_overlapping(ranked, count)


def infer_mood(text: str) -> str:
    tokens = set(re.findall(r"[a-z']+", text.lower()))
    scores = {mood: len(tokens & bag) for mood, bag in MOOD_WORDS.items()}
    best = max(scores, key=lambda mood: scores[mood])
    if scores[best] == 0:
        return "informative"
    return best


def _candidate_windows(
    words: list[Word],
    duration: float,
    min_len: float,
    max_len: float,
) -> list[tuple[float, float]]:
    step = 2.0 if duration > 600 else 1.25
    starts = {0.0}
    for word in words:
        if 0 <= word.start <= max(0.0, duration - min(min_len, duration)):
            starts.add(word.start)
    grid = 0.0
    while grid < duration:
        starts.add(grid)
        grid += step

    lengths = {min_len, max_len, (min_len + max_len) / 2}
    windows: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for start in sorted(starts):
        for length in lengths:
            end = min(duration, start + length)
            if end - start < min_len - 0.05:
                continue
            key = (round(start, 2), round(end, 2))
            if key in seen:
                continue
            seen.add(key)
            windows.append(key)
    return windows


def _raw_score(
    words: list[Word],
    start: float,
    end: float,
    *,
    energy: list[tuple[float, float]] | None,
    scenes: list[float] | None,
) -> float:
    duration = max(0.05, end - start)
    tokens = [normalize_token(word.text) for word in words]
    hook = sum(HOOK_WEIGHTS.get(token, 0.0) for token in tokens)
    speech = 0.0
    for word in words:
        speech += max(0.0, min(word.end, end) - max(word.start, start))
    silence_ratio = 1.0 - clamp(speech / duration, 0.0, 1.0)
    words_per_second = len(words) / duration
    filler_ratio = sum(1 for token in tokens if token in FILLER_TOKENS) / max(1, len(tokens))
    question = 3.0 if any("?" in word.text for word in words) else 0.0
    exclaim = 2.0 if any("!" in word.text for word in words) else 0.0
    score = (
        hook * 12
        + question
        + exclaim
        + min(words_per_second, 3.5) * 2
        - silence_ratio * 18
        - filler_ratio * 10
    )
    score += _energy_boost(start, end, energy)
    score += _scene_boost(start, scenes)
    return score


def _energy_boost(
    start: float,
    end: float,
    energy: list[tuple[float, float]] | None,
) -> float:
    if not energy:
        return 0.0
    values = [level for moment, level in energy if start - 0.5 <= moment <= end]
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return max(0.0, mean - 0.25) * 16


def _scene_boost(start: float, scenes: list[float] | None) -> float:
    if not scenes:
        return 0.0
    if any(start - 0.1 <= moment <= start + 1.5 for moment in scenes):
        return 8.0
    return 0.0


def _public_score(raw: float) -> float:
    return round(clamp(raw, 0.0, 100.0), 1)


def _title(words: list[Word]) -> str:
    if not words:
        return "Untitled hook"
    size = min(7, len(words))
    best_score = -1.0
    best: list[Word] | None = None
    for index in range(0, len(words) - size + 1):
        chunk = words[index : index + size]
        score = sum(HOOK_WEIGHTS.get(normalize_token(word.text), 0.0) for word in chunk)
        # Prefer an earlier slice when scores tie so the title opens the thought.
        if score > best_score:
            best_score = score
            best = chunk
    chosen = list(best or words[:size])
    while len(chosen) > 3 and HOOK_WEIGHTS.get(normalize_token(chosen[0].text), 0) == 0:
        chosen = chosen[1:]
    text = re.sub(r"\s+", " ", " ".join(word.text.strip() for word in chosen)).strip(" .,-")
    if len(text) > 72:
        text = text[:71].rstrip() + "…"
    if not text:
        return "Untitled hook"
    return text[:1].upper() + text[1:]


def _reason(
    words: list[Word],
    *,
    energy: list[tuple[float, float]] | None,
    scenes: list[float] | None,
    start: float,
) -> str:
    tokens = [normalize_token(word.text) for word in words]
    hits = [token for token in tokens if token in HOOK_WEIGHTS]
    if hits:
        sentence = f"Strong claim around “{hits[0]}”, paced tightly enough to hold a short."
    else:
        sentence = "Continuous speech with little dead air — a workable open for a short."
    if _scene_boost(start, scenes):
        sentence += " A scene change lands on the open."
    if _energy_boost(start, start + 2, energy) > 4:
        sentence += " The audio hits harder here."
    return sentence


def _extract_json(text: str):
    if not text or not text.strip():
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, flags=re.DOTALL)
    blob = fenced.group(1) if fenced else None
    if blob is None:
        obj_start = text.find("{")
        obj_end = text.rfind("}")
        arr_start = text.find("[")
        arr_end = text.rfind("]")
        if obj_start != -1 and obj_end > obj_start and (arr_start == -1 or obj_start < arr_start):
            blob = text[obj_start : obj_end + 1]
        elif arr_start != -1 and arr_end > arr_start:
            blob = text[arr_start : arr_end + 1]
        else:
            return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _coerce_highlight(
    item: object,
    *,
    duration: float,
    min_len: float,
    max_len: float,
) -> Highlight | None:
    if not isinstance(item, dict):
        return None
    try:
        start = float(item.get("start", item.get("start_time", item.get("from"))))
        end = float(item.get("end", item.get("end_time", item.get("to"))))
        score = float(item.get("hook_score", item.get("hookScore", item.get("score", 0))))
    except (TypeError, ValueError):
        return None
    start = clamp(start, 0.0, duration)
    end = clamp(end, 0.0, duration)
    if end <= start:
        return None
    if end - start > max_len:
        end = start + max_len
    if end > duration or end - start < min_len:
        return None
    mood = str(item.get("mood", "informative")).strip().lower()
    if mood not in MOODS:
        mood = "informative"
    title = str(item.get("title") or item.get("hook") or "Untitled hook").strip()
    reason = str(item.get("reason") or item.get("why") or "").strip() or "Model picked this stretch."
    return Highlight(
        start=start,
        end=end,
        hook_score=clamp(score, 0.0, 100.0),
        reason=reason,
        title=title or "Untitled hook",
        mood=mood,
    )


def _take_non_overlapping(highlights: list[Highlight], limit: int) -> list[Highlight]:
    ordered = sorted(highlights, key=lambda item: item.hook_score, reverse=True)
    kept: list[Highlight] = []
    for item in ordered:
        if all(item.end <= other.start + 0.05 or item.start >= other.end - 0.05 for other in kept):
            kept.append(item)
        if len(kept) >= limit:
            break
    return kept
