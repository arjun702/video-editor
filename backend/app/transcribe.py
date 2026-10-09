"""Local transcription with faster-whisper. The model loads once per process."""

from __future__ import annotations

import logging
from pathlib import Path

from app.transcript import Word

log = logging.getLogger(__name__)

_MODEL = None
_MODEL_KEY: tuple[str, str, str] | None = None


def whisper_runtime(device: str) -> tuple[str, str]:
    """Return (device, compute_type). Apple Silicon and CPU use int8."""
    requested = (device or "auto").strip().lower()
    if requested == "cpu":
        return "cpu", "int8"
    if requested == "cuda":
        return "cuda", "float16"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        log.debug("cuda check failed", exc_info=True)
    return "cpu", "int8"


def transcribe(
    path: Path,
    *,
    model_size: str = "base",
    device: str = "auto",
    on_progress=None,
) -> list[Word]:
    runtime_device, compute_type = whisper_runtime(device)
    model = _load_model(model_size, runtime_device, compute_type)
    segments, info = model.transcribe(
        str(path),
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    duration = float(getattr(info, "duration", 0) or 0)
    words: list[Word] = []
    for segment in segments:
        tokens = getattr(segment, "words", None) or []
        for token in tokens:
            text = (getattr(token, "word", "") or "").strip()
            if not text:
                continue
            start = float(getattr(token, "start", segment.start))
            end = float(getattr(token, "end", segment.end))
            if end < start:
                end = start
            words.append(Word(text, start, end))
        if on_progress and duration > 0:
            on_progress(min(1.0, float(segment.end) / duration))
    return words


def _load_model(model_size: str, device: str, compute_type: str):
    global _MODEL, _MODEL_KEY
    key = (model_size, device, compute_type)
    if _MODEL is not None and _MODEL_KEY == key:
        return _MODEL
    from faster_whisper import WhisperModel

    log.info("loading whisper model %s on %s (%s)", model_size, device, compute_type)
    _MODEL = WhisperModel(model_size, device=device, compute_type=compute_type)
    _MODEL_KEY = key
    return _MODEL
