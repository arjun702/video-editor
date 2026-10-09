"""ASS captions: word-by-word highlight, hook title, and jump-cut clock."""

from app.captions import build_ass
from app.transcript import Word


def test_hormozi_preset_is_uppercase_with_a_yellow_active_word_and_title():
    words = [
        Word("Stop", 5.0, 5.3),
        Word("scrolling", 5.3, 5.8),
        Word("now", 5.85, 6.2),
    ]
    ass = build_ass(
        words,
        segments=[(5.0, 6.2)],
        xfade=0.0,
        style="hormozi",
        title="Stop scrolling",
        width=720,
        height=1280,
    )
    assert "PlayResX: 720" in ass
    assert "PlayResY: 1280" in ass
    assert "STOP SCROLLING" in ass
    assert "STOP" in ass
    assert "&H0000FFFF&" in ass
    assert "Dialogue:" in ass
    assert "Style: Title" in ass
    assert "Anton" in ass


def test_jump_cut_moves_later_words_onto_the_output_clock():
    words = [Word("Alpha", 0.0, 0.4), Word("Beta", 5.0, 5.4)]
    ass = build_ass(
        words,
        segments=[(0.0, 0.4), (5.0, 5.4)],
        xfade=0.0,
        style="clean",
        title="Hi",
        width=720,
        height=1280,
    )
    assert "Beta" in ass
    assert "0:00:05" not in ass
    assert "0:00:00.40" in ass


def test_clean_preset_keeps_sentence_case_and_uses_inter():
    words = [Word("Hello", 0.0, 0.5), Word("there", 0.5, 0.9)]
    ass = build_ass(
        words,
        segments=[(0.0, 0.9)],
        xfade=0.0,
        style="clean",
        title="Hello there",
        width=1080,
        height=1920,
    )
    assert "Hello" in ass
    assert "HELLO" not in ass
    assert "Inter" in ass
    assert "&H004AFFD6&" in ass


def test_pop_preset_uses_coral_for_the_active_word():
    words = [Word("Wait", 0.0, 0.4)]
    ass = build_ass(
        words,
        segments=[(0.0, 0.4)],
        xfade=0.0,
        style="pop",
        title="Wait",
        width=720,
        height=1280,
    )
    assert "&H00365AFF&" in ass
    assert "WAIT" in ass


def test_xfade_overlap_pulls_the_next_word_earlier():
    words = [Word("Beta", 5.0, 5.4)]
    ass = build_ass(
        words,
        segments=[(0.0, 2.0), (5.0, 7.0)],
        xfade=0.2,
        style="clean",
        title="Beta",
        width=720,
        height=1280,
    )
    # Segment 1 begins at 2.0 - 0.2 on the output clock.
    assert "0:00:01.80" in ass
