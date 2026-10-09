"""ffprobe helpers and optional audio-energy / scene-change signals."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class Probe:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


def probe(path: Path) -> Probe:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError((proc.stderr or "ffprobe failed").strip()[-500:])
    import json

    data = json.loads(proc.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0)
    width = height = 0
    fps = 30.0
    has_audio = False
    for stream in data.get("streams") or []:
        if stream.get("codec_type") == "video" and width == 0:
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            fps = _parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1")
            if not duration:
                duration = float(stream.get("duration") or 0)
        if stream.get("codec_type") == "audio":
            has_audio = True
    if width <= 0 or height <= 0:
        raise MediaError("No video stream in that file.")
    return Probe(duration=duration, width=width, height=height, fps=fps or 30.0, has_audio=has_audio)


def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "ffmpeg failed").strip()[-1200:]
        raise MediaError(tail)


def audio_energy(path: Path, window: float = 1.0, max_duration: float = 20 * 60) -> list[tuple[float, float]]:
    """RMS loudness per window, scaled roughly to 0..1. Empty if it can't be read."""
    info = probe(path)
    if not info.has_audio or info.duration <= 0 or info.duration > max_duration:
        return []
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        "8000",
        "-f",
        "s16le",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return []
    import numpy as np

    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return []
    samples /= 32768.0
    hop = max(1, int(8000 * window))
    series: list[tuple[float, float]] = []
    for index in range(0, samples.size, hop):
        chunk = samples[index : index + hop]
        if chunk.size == 0:
            break
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        series.append((index / 8000.0, min(1.0, rms * 4.0)))
    return series


def scene_changes(path: Path, max_duration: float = 8 * 60, threshold: float = 0.32) -> list[float]:
    info = probe(path)
    if info.duration <= 0 or info.duration > max_duration:
        return []
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(path),
        "-vf",
        f"fps=2,select='gt(scene,{threshold})',showinfo",
        "-an",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    times = []
    for match in re.finditer(r"pts_time:([0-9.]+)", proc.stderr or ""):
        times.append(float(match.group(1)))
    return times


def shot_cuts(path: Path, start: float, end: float, threshold: float = 0.3) -> list[float]:
    """Camera cuts between start and end, in seconds relative to start."""
    span = end - start
    if span <= 0:
        return []
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{span:.3f}",
        "-i",
        str(path),
        "-vf",
        f"scale=320:-2,select='gt(scene,{threshold})',showinfo",
        "-an",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return [float(match.group(1)) for match in re.finditer(r"pts_time:([0-9.]+)", proc.stderr or "")]


def _parse_fps(value: str) -> float:
    if not value or value == "0/0":
        return 30.0
    if "/" in value:
        num, den = value.split("/", 1)
        den_f = float(den or 1)
        if den_f == 0:
            return 30.0
        return float(num) / den_f
    return float(value)
