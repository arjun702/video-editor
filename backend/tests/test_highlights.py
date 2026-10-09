"""Highlight JSON from an LLM, plus the local heuristic used when no key is set."""

from app.highlights import (
    LENGTH_SLACK,
    Highlight,
    frame_highlights,
    heuristic_highlights,
    parse_highlight_response,
)
from app.providers import resolve_provider, transcript_for_prompt
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


def test_long_clip_keeps_some_room_past_max_len_then_is_capped():
    raw = '{"clips":[{"start":0,"end":30,"hook_score":80,"reason":"x","title":"x","mood":"hype"}]}'
    clips = parse_highlight_response(raw, duration=120, min_len=8, max_len=20, limit=1)
    assert clips[0].end == 30

    raw = '{"clips":[{"start":0,"end":90,"hook_score":80,"reason":"x","title":"x","mood":"hype"}]}'
    clips = parse_highlight_response(raw, duration=120, min_len=8, max_len=20, limit=1)
    assert clips[0].end == 20 + LENGTH_SLACK


def test_snapping_never_drops_a_clip_when_neighbours_collide():
    words = [
        Word("One", 10.0, 10.4),
        Word("two", 10.5, 12.0),
        Word("three", 12.1, 14.0),
        Word("four.", 14.1, 16.0),
    ]
    picks = [
        Highlight(10.4, 13.0, 80, "a", "First", "hype"),
        Highlight(13.0, 16.0, 70, "b", "Second", "hype"),
    ]
    framed = frame_highlights(picks, words, duration=30, min_len=2, max_len=20)
    assert [clip.title for clip in framed] == ["First", "Second"]
    assert framed[0].end <= framed[1].start


def test_prompt_transcript_has_one_timed_line_per_sentence():
    words = [
        Word("Hello", 0.0, 0.4),
        Word("there.", 0.5, 0.9),
        Word("Next", 1.0, 1.3),
        Word("bit", 1.4, 1.8),
    ]
    assert transcript_for_prompt(words).splitlines() == [
        "[0.00-0.90] Hello there.",
        "[1.00-1.80] Next bit",
    ]


def test_frame_snaps_to_a_pause_not_a_fixed_pad():
    words = [
        Word("Setup", 8.0, 8.4),
        Word("here.", 8.5, 8.9),
        Word("Stop", 10.2, 10.5),
        Word("now.", 10.6, 11.0),
        Word("Done", 11.1, 11.5),
        Word("talking.", 11.6, 12.1),
        Word("Later", 18.0, 18.4),
    ]
    framed = frame_highlights(
        [Highlight(10.3, 11.05, 80, "claim", "Stop now", "hype")],
        words,
        duration=20,
        min_len=2,
        max_len=20,
    )
    assert framed[0].start == 10.2
    assert framed[0].end == 12.1


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


def test_title_skips_filler_words():
    words = [
        Word("stop", 0.0, 0.3),
        Word("um", 0.35, 0.5),
        Word("scrolling", 0.55, 0.9),
        Word("now", 0.95, 1.2),
    ]
    clips = heuristic_highlights(words, duration=1.3, min_len=1, max_len=2, count=1)
    assert clips
    assert "um" not in clips[0].title.lower()
    assert "stop" in clips[0].title.lower()


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
