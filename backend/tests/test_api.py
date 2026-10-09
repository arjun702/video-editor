"""API smoke checks. No secrets in the health payload."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ffmpeg_and_hides_keys():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["ffmpeg"] is True
    assert body["provider"] in {"heuristic", "gemini", "openai", "anthropic"}
    blob = str(body)
    assert "sk-" not in blob
    assert "AIza" not in blob
    assert "api_key" not in blob


def test_rejects_an_inverted_length_range():
    response = TestClient(app).post(
        "/api/sample",
        data={"min_len": "40", "max_len": "12", "clip_count": "1"},
    )
    assert response.status_code == 400
