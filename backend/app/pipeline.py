"""Run transcription, hook picking, and rendering for one source file."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Settings, get_settings
from app.highlights import Highlight
from app.media import MediaError, audio_energy, probe, scene_changes, shot_cuts
from app.providers import pick_highlights, resolve_provider
from app.reframe import track_subject
from app.render import output_size, render_clip
from app.transcribe import transcribe
from app.transcript import Word

log = logging.getLogger(__name__)


@dataclass
class CutSettings:
    clip_count: int = 4
    min_len: float = 15
    max_len: float = 45
    caption_style: str = "hormozi"
    whisper_model: str = "base"
    whisper_device: str = "auto"
    llm_provider: str = "auto"
    quality: str = "sharp"
    use_signals: bool = True


@dataclass
class ClipResult:
    id: str
    title: str
    reason: str
    mood: str
    hook_score: float
    start: float
    end: float
    duration: float
    video_path: Path
    project_path: Path


@dataclass
class ProcessResult:
    clips: list[ClipResult] = field(default_factory=list)
    provider: str = "heuristic"
    words: list[Word] = field(default_factory=list)


def process_source(
    source: Path,
    dest_dir: Path,
    *,
    words: list[Word] | None = None,
    settings: CutSettings | None = None,
    config: Settings | None = None,
    on_stage=None,
) -> ProcessResult:
    settings = settings or CutSettings()
    config = config or get_settings()
    dest_dir.mkdir(parents=True, exist_ok=True)

    def stage(name: str, progress: float, detail: str) -> None:
        if on_stage:
            on_stage(name, progress, detail)

    info = probe(source)
    if info.duration <= 0:
        raise MediaError("Could not read a duration for that video.")
    if not info.has_audio:
        raise MediaError("This video has no audio track, so there is nothing to transcribe.")

    stage("transcribing", 0.08, "Listening for words")
    if words is None:
        spoken = transcribe(
            source,
            model_size=settings.whisper_model,
            device=settings.whisper_device,
            on_progress=lambda fraction: stage(
                "transcribing",
                0.08 + 0.42 * fraction,
                "Listening for words",
            ),
        )
    else:
        spoken = list(words)
    if not spoken:
        raise MediaError(
            "No speech detected. Spool needs a spoken soundtrack to find hooks and captions."
        )

    stage("highlighting", 0.55, "Choosing the moments worth posting")
    energy = None
    scenes = None
    if settings.use_signals:
        try:
            energy = audio_energy(source)
        except Exception:
            log.debug("audio energy skipped", exc_info=True)
        try:
            scenes = scene_changes(source)
        except Exception:
            log.debug("scene detection skipped", exc_info=True)

    provider_name = resolve_provider(
        settings.llm_provider,
        gemini=config.gemini_api_key,
        openai=config.openai_api_key,
        anthropic=config.anthropic_api_key,
    )
    highlights, used = pick_highlights(
        spoken,
        duration=info.duration,
        count=settings.clip_count,
        min_len=settings.min_len,
        max_len=settings.max_len,
        provider_name=provider_name,
        gemini_key=config.gemini_api_key,
        gemini_model=config.gemini_model,
        openai_key=config.openai_api_key,
        openai_model=config.openai_model,
        anthropic_key=config.anthropic_api_key,
        anthropic_model=config.anthropic_model,
        energy=energy,
        scenes=scenes,
        on_wait=lambda detail: stage("highlighting", 0.55, detail),
    )
    if not highlights:
        raise MediaError("Nothing in this video scored as a short. Try a wider length range.")

    width, height = output_size(settings.quality)
    clips: list[ClipResult] = []
    total = len(highlights)
    for index, highlight in enumerate(highlights, start=1):
        stage(
            "rendering",
            0.62 + 0.34 * ((index - 1) / total),
            f"Cutting {index} of {total}",
        )
        track = _safe_track(source, highlight)
        clip_id = f"clip-{index:02d}"
        video_path = dest_dir / f"{clip_id}.mp4"
        render_clip(
            source,
            spoken,
            highlight,
            video_path,
            caption_style=settings.caption_style,
            width=width,
            height=height,
            track=track,
        )
        clips.append(
            ClipResult(
                id=clip_id,
                title=highlight.title,
                reason=highlight.reason,
                mood=highlight.mood,
                hook_score=highlight.hook_score,
                start=highlight.start,
                end=highlight.end,
                duration=probe(video_path).duration,
                video_path=video_path,
                project_path=video_path.with_suffix(".mlt"),
            )
        )

    stage("done", 1.0, f"{len(clips)} clip{'s' if len(clips) != 1 else ''} ready")
    return ProcessResult(clips=clips, provider=used, words=spoken)


def _safe_track(source: Path, highlight: Highlight) -> list[tuple[float, float]]:
    try:
        cuts = shot_cuts(source, highlight.start, highlight.end)
    except Exception:
        log.debug("shot detection skipped", exc_info=True)
        cuts = []
    try:
        return track_subject(str(source), highlight.start, highlight.end, cuts=cuts)
    except Exception:
        log.debug("subject tracking skipped", exc_info=True)
        return []
