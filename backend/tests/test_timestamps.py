"""Timestamp arithmetic used by jump cuts, captions, and highlight windows."""

import pytest

from app.transcript import Word, clamp, merge_ranges, shift_words, snap_range_to_words, words_in_range


def test_clamp_keeps_values_inside_bounds():
    assert clamp(5, 0, 3) == 3
    assert clamp(-1, 0, 3) == 0
    assert clamp(1.5, 0, 3) == 1.5


def test_merge_ranges_joins_overlaps_and_small_gaps():
    ranges = [(0.0, 1.0), (0.9, 2.0), (2.2, 3.0), (5.0, 6.0)]
    assert merge_ranges(ranges, gap=0.25) == [(0.0, 3.0), (5.0, 6.0)]


def test_merge_ranges_is_order_independent():
    assert merge_ranges([(5, 6), (0, 1), (0.5, 1.2)]) == [(0.0, 1.2), (5.0, 6.0)]


def test_words_in_range_uses_half_open_overlap():
    words = [Word("a", 0.0, 0.4), Word("b", 0.5, 0.9), Word("c", 1.2, 1.5)]
    got = words_in_range(words, 0.4, 1.2)
    assert [w.text for w in got] == ["a", "b"]


def test_snap_range_expands_to_whole_words_inside_the_window():
    words = [
        Word("hello", 1.05, 1.4),
        Word("there", 1.4, 1.9),
        Word("friend", 3.0, 3.4),
    ]
    start, end = snap_range_to_words(1.2, 1.7, words)
    assert start == pytest.approx(1.05)
    assert end == pytest.approx(1.9)


def test_snap_range_returns_input_when_no_words_overlap():
    words = [Word("later", 8.0, 8.4)]
    assert snap_range_to_words(1.0, 2.0, words) == (1.0, 2.0)


def test_shift_words_moves_the_clock_without_changing_text():
    shifted = shift_words([Word("hi", 10.0, 10.4)], -10)
    assert shifted[0].text == "hi"
    assert shifted[0].start == pytest.approx(0.0)
    assert shifted[0].end == pytest.approx(0.4)
