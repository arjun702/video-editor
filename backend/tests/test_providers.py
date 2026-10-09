"""Highlight model retries: wait out a busy model, fail fast on a bad request."""

import pytest

from app import providers
from app.providers import HighlightModelError, ModelBusy, pick_highlights
from app.transcript import Word

WORDS = [Word(f"word{index}.", index * 1.0, index * 1.0 + 0.8) for index in range(60)]
GOOD = '{"clips":[{"start":10,"end":30,"hook_score":80,"reason":"x","title":"Hook","mood":"hype"}]}'


class FakeModel:
    name = "gemini"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda seconds: None)

    def install(*replies):
        model = FakeModel(replies)
        monkeypatch.setattr(providers, "_client_for", lambda *args, **kwargs: model)
        return model

    return install


def _pick(**kwargs):
    return pick_highlights(
        WORDS,
        duration=60,
        count=1,
        min_len=15,
        max_len=30,
        provider_name="gemini",
        gemini_key="key",
        **kwargs,
    )


def test_busy_model_is_retried_until_it_answers(fake):
    model = fake(ModelBusy("503"), "not json", GOOD)
    waits = []
    clips, source = _pick(on_wait=waits.append)
    assert source == "gemini"
    assert clips[0].title == "Hook"
    assert model.calls == 3
    assert waits == [
        "Gemini is busy. Trying again (2 of 4)",
        "Gemini is busy. Trying again (3 of 4)",
    ]


def test_bad_key_fails_the_job_without_retrying(fake):
    model = fake(RuntimeError("Gemini 403: API key not valid"))
    with pytest.raises(HighlightModelError, match="API key not valid"):
        _pick()
    assert model.calls == 1


def test_gives_up_after_the_last_round(fake):
    model = fake(*[ModelBusy("503 overloaded")] * 4)
    with pytest.raises(HighlightModelError, match="after 4 tries"):
        _pick()
    assert model.calls == 4
