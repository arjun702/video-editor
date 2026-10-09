"""Render a captioned vertical clip from a generated video. No API key required.

Run from the repo root:

    .venv/bin/python backend/scripts/e2e_sample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.pipeline import CutSettings, process_source  # noqa: E402
from app.sample_media import generate_sample_video, sample_words  # noqa: E402


def main() -> None:
    dest = ROOT / "data" / "e2e"
    dest.mkdir(parents=True, exist_ok=True)
    source = dest / "sample.mp4"
    print("Generating a short test video…")
    generate_sample_video(source, duration=12)
    print("Cutting with the local heuristic…")
    result = process_source(
        source,
        dest / "clips",
        words=sample_words(
            [
                (0.3, "hello everyone welcome back"),
                (3.2, "stop scrolling the biggest mistake kills your runway"),
                (8.4, "thanks for watching"),
            ]
        ),
        settings=CutSettings(
            clip_count=1,
            min_len=5,
            max_len=11,
            caption_style="hormozi",
            llm_provider="heuristic",
            quality="fast",
            use_signals=False,
        ),
    )
    for clip in result.clips:
        print(
            f"{clip.id}  score={clip.hook_score:.0f}  {clip.mood}  "
            f"{clip.duration:.1f}s  {clip.title}"
        )
        print(f"  video   {clip.video_path}")
        print(f"  project {clip.project_path}")
    if not result.clips:
        raise SystemExit("No clips were produced.")


if __name__ == "__main__":
    main()
