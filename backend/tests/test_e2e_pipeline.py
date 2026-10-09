"""End-to-end cut of a generated video, using the local heuristic (no API key)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import cv2

from app.media import probe
from app.pipeline import CutSettings, process_source
from app.sample_media import generate_sample_video
from app.transcript import Word


def test_pipeline_renders_captioned_vertical_clips(tmp_path):
    source = tmp_path / "episode.mp4"
    # The subject stays in the left third, outside a center crop, so a lime
    # pixel in the vertical frame means tracking followed it.
    generate_sample_video(source, duration=10, travel=80)
    words = _script()
    result = process_source(
        source,
        tmp_path / "clips",
        words=words,
        settings=CutSettings(
            clip_count=1,
            min_len=4,
            max_len=9,
            caption_style="hormozi",
            llm_provider="heuristic",
            quality="fast",
            use_signals=False,
        ),
    )
    assert result.provider == "heuristic"
    assert len(result.clips) == 1
    clip = result.clips[0]
    assert clip.video_path.exists()
    assert clip.project_path.exists()
    info = probe(clip.video_path)
    assert info.height > info.width
    assert abs((info.width / info.height) - (9 / 16)) < 0.02
    assert info.duration > 1.5
    assert clip.hook_score > 0
    assert "mistake" in clip.title.lower() or "stop" in clip.title.lower() or "kills" in clip.title.lower()

    project = ET.fromstring(clip.project_path.read_text(encoding="utf-8"))
    assert project.find("profile").get("height") == "1280"
    assert str(source.resolve()) in clip.project_path.read_text(encoding="utf-8")

    ass = clip.video_path.with_suffix(".ass").read_text(encoding="utf-8")
    assert "Dialogue:" in ass
    assert "STOP" in ass or "MISTAKE" in ass

    assert _frame_has(clip.video_path, bright=True)
    assert _frame_has(clip.video_path, lime=True)


def _script() -> list[Word]:
    lines = [
        (0.2, "hello and welcome back everyone"),
        (3.0, "stop the biggest mistake kills runway fast"),
        (6.6, "um"),
        (8.0, "thanks for watching today"),
    ]
    words: list[Word] = []
    for origin, text in lines:
        cursor = origin
        for token in text.split():
            words.append(Word(token, round(cursor, 3), round(cursor + 0.28, 3)))
            cursor += 0.32
    return words


def _frame_has(path, *, bright: bool = False, lime: bool = False) -> bool:
    capture = cv2.VideoCapture(str(path))
    try:
        for moment in (0.35, 0.7, 1.1, 1.6, 2.2, 2.8):
            capture.set(cv2.CAP_PROP_POS_MSEC, moment * 1000)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            if lime and _lime(frame):
                return True
            if bright and _bright_text(frame):
                return True
    finally:
        capture.release()
    return False


def _lime(frame) -> bool:
    blue, green, red = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
    return int(((green > 180) & (red > 140) & (blue < 140)).sum()) > 30


def _bright_text(frame) -> bool:
    height = frame.shape[0]
    band = frame[int(height * 0.55) :, :, :]
    red, green, blue = band[:, :, 2], band[:, :, 1], band[:, :, 0]
    return int(((red > 210) & (green > 210) & (blue > 210)).sum()) > 25
