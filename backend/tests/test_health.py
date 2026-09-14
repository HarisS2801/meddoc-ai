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