"""Jump-cut planning: drop filler words and long pauses, keep the speech."""

from app.silence import trim_fillers_and_silence
from app.transcript import Word


def w(text: str, start: float, end: float) -> Word:
    return Word(text, start, end)


def test_drops_fillers_and_splits_on_long_gaps():
    words = [
        w("Stop", 0.0, 0.3),
        w("scrolling", 0.32, 0.7),
        w("um", 0.75, 0.95),
        w("this", 2.4, 2.7),
        w("matters", 2.72, 3.2),
    ]
    ranges = trim_fillers_and_silence(words, 0.0, 4.0, max_gap=0.45, pad=0.0)
    assert ranges == [(0.0, 0.7), (2.4, 3.2)]


def test_drops_you_know_as_a_phrase():
    words = [
        w("Wait", 0.0, 0.3),
        w("you", 0.4, 0.55),
        w("know,", 0.55, 0.8),
        w("listen", 1.6, 2.1),
    ]
    ranges = trim_fillers_and_silence(words, 0.0, 3.0, max_gap=0.4, pad=0.0)
    assert ranges == [(0.0, 0.3), (1.6, 2.1)]


def test_pad_stays_inside_the_clip_and_does_not_overlap():
    words = [w("Hello", 1.0, 1.2), w("again", 2.0, 2.2)]
    ranges = trim_fillers_and_silence(words, 1.0, 2.3, max_gap=0.3, pad=0.2)
    assert ranges[0][0] == 1.0
    assert ranges[-1][1] == 2.3
    assert ranges[0][1] <= ranges[1][0]


def test_only_fillers_produces_no_ranges():
    words = [w("um", 0.1, 0.3), w("uh", 0.4, 0.6), w("you", 0.7, 0.9), w("know", 0.9, 1.1)]
    assert trim_fillers_and_silence(words, 0.0, 2.0) == []


def test_protect_keeps_the_open_and_close_uncut():
    words = [
        w("Hello", 1.0, 1.3),
        w("there", 3.0, 3.4),
        w("now", 8.0, 8.4),
        w("bye", 10.5, 11.0),
    ]
    ranges = trim_fillers_and_silence(
        words, 0.0, 12.0, max_gap=0.4, pad=0.0, protect=2.0
    )
    assert ranges[0][0] == 0.0
    assert ranges[0][1] >= 2.0
    assert ranges[-1][1] == 12.0
    assert ranges[-1][0] <= 10.0


def test_hold_keeps_air_after_the_last_word():
    words = [w("Stop", 0.0, 0.3), w("now", 0.4, 0.8)]
    ranges = trim_fillers_and_silence(words, 0.0, 3.0, max_gap=0.4, pad=0.0, hold=0.7)
    assert ranges == [(0.0, 1.5)]


def test_words_outside_the_clip_are_ignored():
    words = [w("before", 0.0, 0.4), w("inside", 5.0, 5.4), w("after", 9.0, 9.3)]
    ranges = trim_fillers_and_silence(words, 4.5, 6.0, max_gap=0.4, pad=0.0)
    assert ranges == [(5.0, 5.4)]
