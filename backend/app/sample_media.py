"""A short synthetic episode so the app can demo the cutter without an upload."""

from __future__ import annotations

from pathlib import Path

from app.media import run_ffmpeg
from app.transcript import Word

SAMPLE_LINES = [
    (0.4, "hello everyone welcome back to the channel today we are just getting settled in"),
    (8.2, "stop scrolling the biggest mistake is hiring too early it quietly kills your runway"),
    (16.4, "wait the secret nobody tells you is to stay small until the work repeats"),
    (24.2, "anyway thanks for watching I will see you next week"),
]


def sample_words(lines: list[tuple[float, str]] | None = None) -> list[Word]:
    words: list[Word] = []
    for origin, text in lines or SAMPLE_LINES:
        cursor = origin
        for token in text.split():
            words.append(Word(token, round(cursor, 3), round(cursor + 0.30, 3)))
            cursor += 0.34
    # A filler and a pause inside the strongest claim, so the cut jumps.
    words.append(Word("um", 13.55, 13.75))
    words.sort(key=lambda word: word.start)
    return words


def find_font() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent / "assets" / "fonts" / "Inter-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def generate_sample_video(path: Path, duration: float = 28.0, travel: float = 900.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    speed = travel / max(duration, 0.1)
    font = find_font()
    draw = ""
    if font is not None:
        cards = [
            (0.2, 7.6, "getting settled"),
            (8.0, 15.8, "the biggest mistake"),
            (16.2, 23.6, "the secret"),
            (24.0, 27.8, "see you next week"),
        ]
        fontfile = str(font).replace("\\", "/").replace(":", "\\:")
        bits = []
        for start, end, text in cards:
            bits.append(
                "drawtext="
                f"fontfile='{fontfile}':text='{text}':x=72:y=78:fontsize=54:"
                "fontcolor=white:borderw=4:bordercolor=0x14150f:"
                f"enable='between(t\\,{start}\\,{end})'"
            )
        draw = "," + ",".join(bits)
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x14150f:s=1280x720:d={duration:.2f}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0xdff56a:s=200x280:d={duration:.2f}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=196:sample_rate=48000:duration={duration:.2f}",
            "-filter_complex",
            (
                f"[0:v][1:v]overlay=x='36+{speed:.4f}*t':y=230:shortest=1"
                f"{draw}[v]"
            ),
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(path),
        ]
    )
