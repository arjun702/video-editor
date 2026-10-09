"""Highlight JSON from an LLM, plus the local heuristic used when no key is set."""

from app.highlights import heuristic_highlights, parse_highlight_response
from app.providers import resolve_provider
from app.transcript import Word


FENCED = """
Sure — here are the cuts:
```json
{
  "clips": [
    {
      "start": -2,
      "end": 18,
      "hook_score": 140,
      "reason": "sharp claim",
      "title": "Stop hiring early",
      "mood": "Dramatic"
    },
    {
      "start_time": 40,
      "end_time": 42,
      "hookScore": 10,
      "reason": "too short",
      "title": "nope",
      "mood": "weird"
    }
  ]
}
```
"""


def test_parse_fenced_json_clamps_score_time_and_mood():
    clips = parse_highlight_response(FENCED, duration=30, min_len=8, max_len=60, limit=5)
    assert len(clips) == 1
    clip = clips[0]
    assert clip.start == 0
    assert clip.end == 18
    assert clip.hook_score == 100
    assert clip.mood == "dramatic"
    assert clip.title == "Stop hiring early"
    assert clip.reason == "sharp claim"


def test_parse_rejects_prose_without_json():
    assert parse_highlight_response("I think the best part is the middle.", duration=30, min_len=5, max_len=60, limit=3) == []


def test_parse_keeps_higher_score_when_windows_overlap():
    raw = """
    {"highlights": [
      {"start": 0, "end": 20, "hook_score": 40, "reason": "slow open", "title": "Hello", "mood": "informative"},
      {"start": 5, "end": 25, "hook_score": 91, "reason": "the turn", "title": "The turn", "mood": "hype"}
    ]}
    """
    clips = parse_highlight_response(raw, duration=40, min_len=8, max_len=60, limit=5)
    assert len(clips) == 1
    assert clips[0].title == "The turn"
    assert clips[0].hook_score == 91


def _spoken(script: list[tuple[str, float]]) -> list[Word]:
    words: list[Word] = []
    for text, cursor in script:
        for token in text.split():
            words.append(Word(token, cursor, cursor + 0.32))
            cursor += 0.36
    return words


def test_heuristic_prefers_the_hook_over_the_intro():
    words = []
    words += _spoken([("hello everyone welcome back to the channel today we talk", 0.0)])
    words += _spoken([("stop scrolling the biggest mistake is hiring too early it kills runway", 12.0)])
    words += _spoken([("um yeah so anyway thanks for watching bye", 24.0)])
    duration = words[-1].end + 0.2
    clips = heuristic_highlights(words, duration=duration, min_len=6, max_len=12, count=1)
    assert len(clips) == 1
    clip = clips[0]
    assert any(w.text == "mistake" and clip.start <= w.start < clip.end for w in words)
    assert not any(w.text == "welcome" and clip.start <= w.start < clip.end for w in words)
    assert clip.hook_score >= 40
    assert clip.mood in {"dramatic", "hype", "informative", "funny", "emotional", "inspiring"}
    assert clip.title
    assert clip.reason


def test_heuristic_returns_non_overlapping_clips_sorted_by_score():
    chunks = []
    t = 0.0
    lines = [
        "welcome back everybody thanks for being here today",
        "stop now the secret nobody tells founders about pricing",
        "and then we kind of continued with the regular update",
        "wait this one mistake quietly kills your runway fast",
        "thanks again see you next week goodbye everyone",
    ]
    for line in lines:
        for token in line.split():
            chunks.append(Word(token, t, t + 0.3))
            t += 0.34
    clips = heuristic_highlights(chunks, duration=t, min_len=4, max_len=8, count=2)
    assert 1 <= len(clips) <= 2
    assert clips == sorted(clips, key=lambda c: c.hook_score, reverse=True)
    ordered = sorted(clips, key=lambda c: c.start)
    for left, right in zip(ordered, ordered[1:]):
        assert left.end <= right.start + 0.05


def test_short_video_still_returns_one_clip():
    words = [Word("stop", 0.0, 0.4), Word("now", 0.4, 0.9)]
    clips = heuristic_highlights(words, duration=0.9, min_len=15, max_len=60, count=3)
    assert len(clips) == 1
    assert clips[0].end - clips[0].start == pytest_approx_range(0.9)


def pytest_approx_range(value: float):
    import pytest

    return pytest.approx(value, abs=0.05)


def test_scene_and_energy_signals_raise_the_score():
    words = _spoken([("here is a plain update about the roadmap and the team", 0.0)])
    duration = words[-1].end
    plain = heuristic_highlights(words, duration=duration, min_len=3, max_len=20, count=1)
    boosted = heuristic_highlights(
        words,
        duration=duration,
        min_len=3,
        max_len=20,
        count=1,
        energy=[(0.0, 0.9)],
        scenes=[0.2],
    )
    assert boosted[0].hook_score > plain[0].hook_score


def test_resolve_provider_prefers_a_configured_key_then_heuristic():
    assert resolve_provider("auto", gemini="", openai="sk-test", anthropic="") == "openai"
    assert resolve_provider("auto", gemini="g", openai="sk", anthropic="") == "gemini"
    assert resolve_provider("auto", gemini="", openai="", anthropic="") == "heuristic"
    assert resolve_provider("anthropic", gemini="g", openai="sk", anthropic="") == "anthropic"
