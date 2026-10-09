"""Cut, reframe, punch in, transition, and burn captions with FFmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.captions import build_ass
from app.edit import emphasis_windows, punch_chain, transition_for_mood, xfade_offsets
from app.highlights import Highlight
from app.media import MediaError, probe, run_ffmpeg
from app.mlt import build_mlt
from app.reframe import crop_size, crop_x_expression, crop_y_expression
from app.transcript import Word

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def output_size(quality: str) -> tuple[int, int]:
    if quality == "fast":
        return (720, 1280)
    return (1080, 1920)


def render_clip(
    source: Path,
    words: list[Word],
    highlight: Highlight,
    out_path: Path,
    *,
    caption_style: str,
    width: int,
    height: int,
    track: list[tuple[float, float]] | None = None,
) -> float:
    """Render one vertical clip. Returns the output duration in seconds."""
    source_info = probe(source)
    # ponytail: jump cuts off; restore trim_fillers_and_silence if we want them back
    pad = 0.5
    start = max(0.0, highlight.start - pad)
    end = min(source_info.duration, highlight.end + pad)
    if end <= start:
        start, end = highlight.start, highlight.end
    segments = [(start, end)]

    work = out_path.parent / f".work-{out_path.stem}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        parts: list[Path] = []
        planned: list[float] = []
        for index, (start, end) in enumerate(segments):
            part = work / f"part-{index:02d}.mp4"
            _render_part(
                source,
                part,
                start=start,
                end=end,
                frame_w=source_info.width,
                frame_h=source_info.height,
                has_audio=source_info.has_audio,
                width=width,
                height=height,
                words=words,
                track=track or [],
                highlight_start=highlight.start,
            )
            parts.append(part)
            planned.append(end - start)

        xfade = _xfade_seconds(highlight.mood)
        transition = transition_for_mood(highlight.mood)
        joined = work / "joined.mp4"
        xfade_used = _join(parts, joined, transition, xfade, planned)
        ass_path = out_path.with_suffix(".ass")
        ass_path.write_text(
            build_ass(
                words,
                segments=segments,
                xfade=xfade_used,
                style=caption_style,
                title=highlight.title,
                width=width,
                height=height,
            ),
            encoding="utf-8",
        )
        _burn(joined, ass_path, out_path, width, height)
        project = out_path.with_suffix(".mlt")
        project.write_text(
            build_mlt(
                source=str(source.resolve()),
                segments=segments,
                width=width,
                height=height,
                fps=30,
                title=highlight.title,
            ),
            encoding="utf-8",
        )
        return probe(out_path).duration
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_part(
    source: Path,
    dest: Path,
    *,
    start: float,
    end: float,
    frame_w: int,
    frame_h: int,
    has_audio: bool,
    width: int,
    height: int,
    words: list[Word],
    track: list[tuple[float, float]],
    highlight_start: float,
) -> None:
    crop_w, crop_h = crop_size(frame_w, frame_h)
    relative = [(highlight_start + moment - start, center) for moment, center in track]
    x_expr = crop_x_expression(relative, crop_w, frame_w)
    y_expr = crop_y_expression(frame_h, crop_h)
    filters = [
        "setpts=PTS-STARTPTS",
        f"crop={crop_w}:{crop_h}:x='{x_expr}':y='{y_expr}'",
        f"scale={width}:{height}:flags=bicubic",
        "fps=30",
        "setsar=1",
    ]
    punches = emphasis_windows(words, start, end)
    punch = punch_chain(punches, width, height)
    if punch:
        filters.append(punch)
    filters.append("format=yuv420p")
    video_filter = ",".join(filters)
    duration = max(0.12, end - start)
    if has_audio:
        run_ffmpeg(
            [
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(source),
                "-vf",
                video_filter,
                "-af",
                "aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS",
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(dest),
            ]
        )
        return

    run_ffmpeg(
        [
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-t",
            f"{duration:.3f}",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-filter_complex",
            f"[0:v]{video_filter}[v]",
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def _join(
    parts: list[Path],
    dest: Path,
    transition: str,
    xfade: float,
    planned: list[float],
) -> float:
    if len(parts) == 1:
        shutil.copy(parts[0], dest)
        return 0.0
    durations = [_duration(path) or planned[index] for index, path in enumerate(parts)]
    if all(item > xfade + 0.2 for item in durations):
        try:
            _xfade_join(parts, dest, transition, xfade, durations)
            return xfade
        except MediaError:
            pass
    _concat_join(parts, dest)
    return 0.0


def _xfade_join(
    parts: list[Path],
    dest: Path,
    transition: str,
    xfade: float,
    durations: list[float],
) -> None:
    offsets = xfade_offsets(durations, xfade)
    video_bits = []
    audio_bits = []
    video_in = "[0:v]"
    audio_in = "[0:a]"
    for index, offset in enumerate(offsets):
        video_out = "[vout]" if index == len(offsets) - 1 else f"[v{index}]"
        audio_out = "[aout]" if index == len(offsets) - 1 else f"[a{index}]"
        video_bits.append(
            f"{video_in}[{index + 1}:v]xfade=transition={transition}:duration={xfade:.3f}:offset={offset:.3f}{video_out}"
        )
        audio_bits.append(
            f"{audio_in}[{index + 1}:a]acrossfade=d={xfade:.3f}:c1=tri:c2=tri{audio_out}"
        )
        video_in = video_out
        audio_in = audio_out
    graph = ";".join(video_bits + audio_bits)
    args: list[str] = []
    for part in parts:
        args.extend(["-i", str(part)])
    args.extend(
        [
            "-filter_complex",
            graph,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    run_ffmpeg(args)


def _concat_join(parts: list[Path], dest: Path) -> None:
    graph_inputs = "".join(f"[{index}:v][{index}:a]" for index in range(len(parts)))
    graph = f"{graph_inputs}concat=n={len(parts)}:v=1:a=1[v][a]"
    args: list[str] = []
    for part in parts:
        args.extend(["-i", str(part)])
    args.extend(
        [
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    run_ffmpeg(args)


def _burn(source: Path, ass_path: Path, dest: Path, width: int, height: int) -> None:
    subtitle = _escape_filter_path(ass_path)
    fonts = _escape_filter_path(FONTS_DIR)
    run_ffmpeg(
        [
            "-i",
            str(source),
            "-vf",
            f"ass={subtitle}:fontsdir={fonts},scale={width}:{height},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def _xfade_seconds(mood: str) -> float:
    if mood in {"hype", "funny"}:
        return 0.12
    if mood == "dramatic":
        return 0.20
    return 0.16


def _duration(path: Path) -> float:
    try:
        return probe(path).duration
    except MediaError:
        return 0.0


def _escape_filter_path(path: Path) -> str:
    text = str(path.resolve()).replace("\\", "/")
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False
