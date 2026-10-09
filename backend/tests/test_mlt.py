"""Kdenlive / Shotcut project export."""

import xml.etree.ElementTree as ET

from app.mlt import build_mlt


def test_mlt_profile_is_vertical_and_entries_match_the_cuts():
    xml = build_mlt(
        source="/tmp/source.mp4",
        segments=[(1.0, 2.0), (5.0, 6.5)],
        width=1080,
        height=1920,
        fps=30,
        title="Stop hiring early",
    )
    root = ET.fromstring(xml)
    profile = root.find("profile")
    assert profile is not None
    assert profile.get("width") == "1080"
    assert profile.get("height") == "1920"
    assert profile.get("display_aspect_num") == "9"
    assert profile.get("display_aspect_den") == "16"
    entries = root.findall(".//entry")
    assert len(entries) == 2
    assert entries[0].get("in") == "30"
    assert entries[0].get("out") == "59"
    # 1.5s * 30fps = 45 frames, inclusive out = in + 45 - 1
    assert entries[1].get("in") == "150"
    assert entries[1].get("out") == "194"
    assert "/tmp/source.mp4" in xml
    assert "Stop hiring early" in xml
    assert "avformat" in xml
