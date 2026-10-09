"""LLM providers for highlight picking. Network stays behind this module."""

from __future__ import annotations

import logging
import time
from typing import Protocol

import httpx

from app.highlights import Highlight, frame_highlights, heuristic_highlights, parse_highlight_response
from app.transcript import Word

log = logging.getLogger(__name__)


def resolve_provider(
    choice: str,
    *,
    gemini: str = "",
    openai: str = "",
    anthropic: str = "",
) -> str:
    picked = (choice or "auto").strip().lower()
    if picked != "auto":
        return picked
    if gemini.strip():
        return "gemini"
    if openai.strip():
        return "openai"
    if anthropic.strip():
        return "anthropic"
    return "heuristic"


class HighlightModel(Protocol):
    name: str

    def complete(self, prompt: str) -> str: ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str) -> str:
        models = [self.model]
        for extra in ("gemini-flash-latest", "gemini-3.5-flash-lite"):
            if extra not in models:
                models.append(extra)
        last_error = "Gemini request failed"
        for model in models:
            try:
                return self._generate(prompt, model)
            except RuntimeError as exc:
                last_error = str(exc)
                log.warning("%s; trying the next Gemini model", last_error)
        raise RuntimeError(last_error)

    def _generate(self, prompt: str, model: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=90) as client:
            last_error = "Gemini request failed"
            for attempt in range(6):
                response = client.post(url, headers=headers, json=body)
                if response.status_code in {429, 503}:
                    last_error = f"Gemini {response.status_code}: {response.text[:400]}"
                    time.sleep(3 * (attempt + 1))
                    continue
                if (
                    response.status_code == 400
                    and "thinkingConfig" in body["generationConfig"]
                ):
                    body["generationConfig"].pop("thinkingConfig", None)
                    continue
                if response.is_error:
                    raise RuntimeError(f"Gemini {response.status_code}: {response.text[:800]}")
                data = response.json()
                candidate = (data.get("candidates") or [{}])[0]
                parts = (candidate.get("content") or {}).get("parts") or []
                text = "".join(
                    part.get("text", "")
                    for part in parts
                    if isinstance(part, dict) and not part.get("thought")
                )
                if not text.strip():
                    raise RuntimeError(
                        f"Gemini returned an empty reply ({candidate.get('finishReason')})"
                    )
                return text
        raise RuntimeError(last_error)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You reply with JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        with httpx.Client(timeout=90) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=90) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        chunks = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        return "\n".join(chunks)


def transcript_for_prompt(words: list[Word], bucket: float = 8.0) -> str:
    if not words:
        return "(no speech)"
    lines: list[str] = []
    group: list[Word] = []
    origin = words[0].start
    for word in words:
        if group and word.start - origin > bucket:
            lines.append(
                f"[{origin:.2f}-{group[-1].end:.2f}] " + " ".join(item.text for item in group)
            )
            group = []
            origin = word.start
        group.append(word)
    if group:
        lines.append(f"[{origin:.2f}-{group[-1].end:.2f}] " + " ".join(item.text for item in group))
    return "\n".join(lines)


def build_highlight_prompt(
    words: list[Word],
    *,
    count: int,
    min_len: float,
    max_len: float,
    duration: float,
) -> str:
    return f"""You are a short-form editor cutting TikTok, Reels, and Shorts from a long video.

Pick the {count} best moments. Aim for about {min_len:.0f}–{max_len:.0f} seconds, but go longer if you need a complete thought.
Include the setup and the landing in the timestamps yourself. Cut on a pause or the end of a sentence, not mid-word. The open matters as much as the close.
The video is {duration:.1f} seconds long. Times are in seconds from the start.

Return JSON only, with this shape:
{{"clips":[{{"start":0,"end":20,"hook_score":80,"reason":"why this will stop a scroll","title":"short hook","mood":"dramatic"}}]}}

mood must be one of: funny, dramatic, informative, hype, emotional, inspiring.
hook_score is an integer 0-100. title is at most 8 words. reason is one sentence.
Clips must not overlap.

Transcript:
{transcript_for_prompt(words)}
"""


def pick_highlights(
    words: list[Word],
    *,
    duration: float,
    count: int,
    min_len: float,
    max_len: float,
    provider_name: str,
    gemini_key: str = "",
    gemini_model: str = "gemini-3.8-flash",
    openai_key: str = "",
    openai_model: str = "gpt-4o-mini",
    anthropic_key: str = "",
    anthropic_model: str = "claude-3-5-haiku-latest",
    energy: list[tuple[float, float]] | None = None,
    scenes: list[float] | None = None,
) -> tuple[list[Highlight], str]:
    """Return highlights and the provider that actually produced them."""
    client = _client_for(
        provider_name,
        gemini_key=gemini_key,
        gemini_model=gemini_model,
        openai_key=openai_key,
        openai_model=openai_model,
        anthropic_key=anthropic_key,
        anthropic_model=anthropic_model,
    )
    if client is not None:
        prompt = build_highlight_prompt(
            words, count=count, min_len=min_len, max_len=max_len, duration=duration
        )
        attempt = 0
        while True:
            attempt += 1
            try:
                raw = client.complete(prompt)
                parsed = parse_highlight_response(
                    raw, duration=duration, min_len=min_len, max_len=max_len, limit=count
                )
                if parsed:
                    return (
                        frame_highlights(
                            parsed,
                            words,
                            duration=duration,
                            min_len=min_len,
                            max_len=max_len,
                        ),
                        client.name,
                    )
                log.warning(
                    "Gemini reply was not usable (attempt %s). Retrying. raw=%s",
                    attempt,
                    (raw or "")[:500],
                )
            except Exception as exc:
                log.warning("Gemini attempt %s failed: %s. Retrying.", attempt, exc)
            time.sleep(min(20.0, 2.0 * attempt))

    local = heuristic_highlights(
        words,
        duration=duration,
        min_len=min_len,
        max_len=max_len,
        count=count,
        energy=energy,
        scenes=scenes,
    )
    return local, "heuristic"


def _client_for(
    provider_name: str,
    *,
    gemini_key: str,
    gemini_model: str,
    openai_key: str,
    openai_model: str,
    anthropic_key: str,
    anthropic_model: str,
) -> HighlightModel | None:
    if provider_name == "gemini" and gemini_key.strip():
        return GeminiProvider(gemini_key.strip(), gemini_model)
    if provider_name == "openai" and openai_key.strip():
        return OpenAIProvider(openai_key.strip(), openai_model)
    if provider_name == "anthropic" and anthropic_key.strip():
        return AnthropicProvider(anthropic_key.strip(), anthropic_model)
    return None
