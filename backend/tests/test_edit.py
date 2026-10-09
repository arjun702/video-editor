"""Edit plan: mood transitions, emphasis punches, xfade offsets, word remap."""

import pytest

from app.edit import emphasis_windows, punch_chain, remap_words, transition_for_mood, xfade_offsets
from app.transcript import Word


def test_mood_picks_a_modern_xfade():
    assert transition_for_mood("funny") == "slideright"
    assert transition_for_mood("dramatic") == "fadewhite"
    assert transition_for_mood("informative") == "smoothleft"
    assert transition_for_mood("hype") == "wipeleft"
    assert transition_for_mood("emotional") == "fade"
    assert transition_for_mood("inspiring") == "smoothup"
    assert transition_for_mood("not-a-mood") == "fade"


def test_emphasis_windows_are_relative_to_the_segment():
    words = [
        Word("stop", 10.0, 10.3),
        Word("the", 10.3, 10.5),
        Word("ordinary", 10.5, 11.0),
    ]
    windows = emphasis_windows(words, segment_start=10.0, segment_end=11.0)
    assert windows
    assert windows[0][0] == pytest.approx(0.0, abs=0.05)
    assert windows[0][1] > windows[0][0]
    assert windows[0][1] <= 1.0


def test_plain_words_do_not_punch():
    words = [Word("the", 0.0, 0.2), Word("update", 0.2, 0.6), Word("continues", 0.6, 1.1)]
    assert emphasis_windows(words, 0.0, 1.1) == []


def test_xfade_offsets_shrink_by_the_overlap():
    assert xfade_offsets([2.0, 3.0, 4.0], 0.2) == pytest.approx([1.8, 4.6])


def test_single_segment_has_no_xfade_offset():
    assert xfade_offsets([5.0], 0.2) == []


def test_remap_words_closes_a_jump_cut():
    words = [Word("Alpha", 0.0, 0.4), Word("Beta", 5.0, 5.4)]
    remapped = remap_words(words, [(0.0, 0.4), (5.0, 5.4)], xfade=0.0)
    assert [w.text for w in remapped] == ["Alpha", "Beta"]
    assert remapped[0].start == pytest.approx(0.0)
    assert remapped[1].start == pytest.approx(0.4)
    assert remapped[1].end == pytest.approx(0.8)


def test_remap_words_accounts_for_xfade_overlap():
    remapped = remap_words([Word("Beta", 5.0, 5.4)], [(0.0, 2.0), (5.0, 7.0)], xfade=0.2)
    assert remapped[0].start == pytest.approx(1.8)
    assert remapped[0].end == pytest.approx(2.2)


def test_punch_chain_evaluates_every_frame_and_crops_back():
    chain = punch_chain([(0.2, 0.55)], 720, 1280)
    assert "eval=frame" in chain
    assert "crop=720:1280" in chain
    assert r"\," in chain


def test_punch_chain_is_empty_without_emphasis():
    assert punch_chain([], 720, 1280) == ""
