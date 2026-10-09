"""Disk-backed jobs and a single worker. One cut runs at a time."""

from __future__ import annotations

import json
import queue
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings, get_settings
from app.media import MediaError
from app.pipeline import CutSettings, process_source
from app.sample_media import generate_sample_video, sample_words
from app.transcript import Word

_WORKER: "JobRunner | None" = None
_GUARD = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = Path(settings.data_dir) / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name="spool-worker", daemon=True)
        self._thread.start()

    def create_from_upload(self, filename: str, source: Path, settings: CutSettings) -> dict:
        job_id = uuid.uuid4().hex[:12]
        folder = self._folder(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "source.mp4"
        shutil.move(str(source), target)
        record = self._blank(job_id, filename or "video.mp4", settings)
        self._write(record)
        self._queue.put(job_id)
        return record

    def create_sample(self, settings: CutSettings) -> dict:
        job_id = uuid.uuid4().hex[:12]
        folder = self._folder(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        generate_sample_video(folder / "source.mp4")
        words = [word.__dict__ for word in sample_words()]
        (folder / "words.json").write_text(json.dumps(words), encoding="utf-8")
        record = self._blank(job_id, "Sample reel.mp4", settings)
        record["detail"] = "Sample reel is ready to cut"
        self._write(record)
        self._queue.put(job_id)
        return record

    def get(self, job_id: str) -> dict | None:
        path = self._folder(job_id) / "job.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_recent(self, limit: int = 12) -> list[dict]:
        records = []
        if not self.root.exists():
            return []
        for folder in self.root.iterdir():
            path = folder / "job.json"
            if path.exists():
                records.append(json.loads(path.read_text(encoding="utf-8")))
        records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return records[:limit]

    def clip_file(self, job_id: str, clip_id: str, suffix: str) -> Path | None:
        folder = self._folder(job_id) / "clips"
        path = folder / f"{clip_id}{suffix}"
        if path.exists():
            return path
        return None

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._run(job_id)
            except Exception as exc:  # noqa: BLE001 — last-resort job failure
                self._update(
                    job_id,
                    stage="error",
                    error=str(exc) or "The cut failed.",
                    detail="The cut stopped",
                )
            finally:
                self._queue.task_done()

    def _run(self, job_id: str) -> None:
        record = self.get(job_id)
        if record is None:
            return
        folder = self._folder(job_id)
        source = folder / "source.mp4"
        words = None
        words_path = folder / "words.json"
        if words_path.exists():
            words = [Word(**item) for item in json.loads(words_path.read_text(encoding="utf-8"))]
        settings = CutSettings(**record["settings"])

        def on_stage(name: str, progress: float, detail: str) -> None:
            self._update(job_id, stage=name, progress=round(progress, 4), detail=detail, error=None)

        try:
            result = process_source(
                source,
                folder / "clips",
                words=words,
                settings=settings,
                config=self.settings,
                on_stage=on_stage,
            )
        except MediaError as exc:
            self._update(job_id, stage="error", error=str(exc), detail="The cut stopped")
            return

        clips = []
        for clip in result.clips:
            clips.append(
                {
                    "id": clip.id,
                    "title": clip.title,
                    "reason": clip.reason,
                    "mood": clip.mood,
                    "hook_score": clip.hook_score,
                    "start": clip.start,
                    "end": clip.end,
                    "duration": round(clip.duration, 2),
                }
            )
        detail = f"{len(clips)} clip{'s' if len(clips) != 1 else ''} ready"
        self._update(
            job_id,
            stage="done",
            progress=1,
            detail=detail,
            error=None,
            provider=result.provider,
            clips=clips,
        )

    def _blank(self, job_id: str, filename: str, settings: CutSettings) -> dict:
        return {
            "id": job_id,
            "filename": filename,
            "stage": "queued",
            "progress": 0,
            "detail": "Waiting to start",
            "error": None,
            "provider": None,
            "created_at": now_iso(),
            "settings": {
                "clip_count": settings.clip_count,
                "min_len": settings.min_len,
                "max_len": settings.max_len,
                "caption_style": settings.caption_style,
                "whisper_model": settings.whisper_model,
                "whisper_device": settings.whisper_device,
                "llm_provider": settings.llm_provider,
                "quality": settings.quality,
                "use_signals": settings.use_signals,
            },
            "clips": [],
        }

    def _folder(self, job_id: str) -> Path:
        return self.root / job_id

    def _write(self, record: dict) -> None:
        path = self._folder(record["id"]) / "job.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            record = self.get(job_id)
            if record is None:
                return
            record.update(changes)
            self._write(record)


def get_runner() -> JobRunner:
    global _WORKER
    with _GUARD:
        if _WORKER is None:
            _WORKER = JobRunner(get_settings())
        return _WORKER
