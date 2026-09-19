from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "MedDoc AI"
    assert body["version"] == "0.1.0"


def test_health_has_timestamp() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")

    body = response.json()
    assert "time" in body
    # ISO-8601 timestamps parse to a valid datetime
    from datetime import datetime

    assert datetime.fromisoformat(body["time"]) is not None


def test_health_reports_groq_provider_and_configured() -> None:
    client = TestClient(create_app())
    body = client.get("/api/health").json()

    assert body["ai_provider"] == "groq"
    assert isinstance(body["groq_configured"], bool)
    # The offline test fixtures clear the Groq key, so the flag is False here
    # even when backend/.env carries a real key; the flag itself is still a bool.
    assert body["groq_configured"] is False