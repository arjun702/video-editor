"""HTTP API for Spool."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.jobs import get_runner
from app.pipeline import CutSettings
from app.providers import resolve_provider
from app.render import ffmpeg_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Spool", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STYLES = {"hormozi", "pop", "clean"}
MODELS = {"tiny", "base", "small", "medium"}
PROVIDERS = {"auto", "gemini", "openai", "anthropic", "heuristic"}
QUALITIES = {"fast", "sharp"}
CLIP_ID = re.compile(r"clip-\d{2}")


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    provider = resolve_provider(
        settings.llm_provider,
        gemini=settings.gemini_api_key,
        openai=settings.openai_api_key,
        anthropic=settings.anthropic_api_key,
    )
    return {
        "ok": True,
        "ffmpeg": ffmpeg_available(),
        "provider": provider,
        "whisper_model": settings.whisper_model,
        "keys": {
            "gemini": bool(settings.gemini_api_key.strip()),
            "openai": bool(settings.openai_api_key.strip()),
            "anthropic": bool(settings.anthropic_api_key.strip()),
        },
    }


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": get_runner().list_recent()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    record = get_runner().get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No cut with that id.")
    return record


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    clip_count: int = Form(4),
    min_len: float = Form(15),
    max_len: float = Form(45),
    caption_style: str = Form("hormozi"),
    whisper_model: str = Form("base"),
    llm_provider: str = Form("auto"),
    quality: str = Form("sharp"),
    use_signals: str = Form("true"),
) -> dict:
    settings = _settings(
        clip_count, min_len, max_len, caption_style, whisper_model, llm_provider, quality, use_signals
    )
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose a video file.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix or ".mp4") as handle:
        temp_path = Path(handle.name)
        total = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            total += len(chunk)
    if total == 0:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="That file is empty.")
    return get_runner().create_from_upload(file.filename, temp_path, settings)


@app.post("/api/sample")
def create_sample(
    clip_count: int = Form(3),
    min_len: float = Form(8),
    max_len: float = Form(18),
    caption_style: str = Form("hormozi"),
    whisper_model: str = Form("tiny"),
    llm_provider: str = Form("heuristic"),
    quality: str = Form("fast"),
    use_signals: str = Form("false"),
) -> dict:
    settings = _settings(
        clip_count, min_len, max_len, caption_style, whisper_model, llm_provider, quality, use_signals
    )
    # The sample ships with a transcript so the demo does not download a Whisper model.
    settings.llm_provider = "heuristic" if settings.llm_provider == "auto" else settings.llm_provider
    return get_runner().create_sample(settings)


@app.get("/api/jobs/{job_id}/clips/{clip_id}/preview")
def preview_clip(job_id: str, clip_id: str):
    path = _clip_path(job_id, clip_id, ".mp4")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/clips/{clip_id}/download")
def download_clip(job_id: str, clip_id: str):
    path = _clip_path(job_id, clip_id, ".mp4")
    return FileResponse(path, media_type="video/mp4", filename=f"spool-{clip_id}.mp4")


@app.get("/api/jobs/{job_id}/clips/{clip_id}/project")
def download_project(job_id: str, clip_id: str):
    path = _clip_path(job_id, clip_id, ".mlt")
    return FileResponse(path, media_type="application/xml", filename=f"spool-{clip_id}.mlt")


def _clip_path(job_id: str, clip_id: str, suffix: str) -> Path:
    if not CLIP_ID.fullmatch(clip_id):
        raise HTTPException(status_code=400, detail="Unknown clip.")
    path = get_runner().clip_file(job_id, clip_id, suffix)
    if path is None:
        raise HTTPException(status_code=404, detail="That clip is not ready.")
    return path


def _settings(
    clip_count: int,
    min_len: float,
    max_len: float,
    caption_style: str,
    whisper_model: str,
    llm_provider: str,
    quality: str,
    use_signals: str,
) -> CutSettings:
    if not 1 <= clip_count <= 8:
        raise HTTPException(status_code=400, detail="Clip count has to be between 1 and 8.")
    if not 5 <= min_len <= 90 or not 8 <= max_len <= 120 or min_len >= max_len:
        raise HTTPException(status_code=400, detail="Length range is invalid.")
    style = caption_style.strip().lower()
    model = whisper_model.strip().lower()
    provider = llm_provider.strip().lower()
    picture = quality.strip().lower()
    if style not in STYLES:
        raise HTTPException(status_code=400, detail="Unknown caption style.")
    if model not in MODELS:
        raise HTTPException(status_code=400, detail="Unknown Whisper model.")
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown highlight provider.")
    if picture not in QUALITIES:
        raise HTTPException(status_code=400, detail="Unknown quality.")
    return CutSettings(
        clip_count=clip_count,
        min_len=float(min_len),
        max_len=float(max_len),
        caption_style=style,
        whisper_model=model,
        llm_provider=provider,
        quality=picture,
        use_signals=_flag(use_signals),
    )


def _flag(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
