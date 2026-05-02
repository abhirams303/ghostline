from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


client = TestClient(app)


def test_healthcheck() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_analyze() -> None:
    response = client.post(
        "/analyze",
        json={
            "target": {
                "name": "Fort Liberty",
                "lat": 35.1414,
                "lon": -79.006,
                "radius_km": 20
            },
            "mode": "demo"
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target"]["name"] == "Fort Liberty"
    assert body["mode"] == "demo"


def test_live_analyze_without_openai_key_uses_fallback(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPSEC_MIRROR_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    response = client.post(
        "/analyze",
        json={
            "target": {
                "name": "Fort Liberty",
                "lat": 35.1414,
                "lon": -79.006,
                "radius_km": 20
            },
            "mode": "live"
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert body["run_id"]
    assert "Fort Liberty" in body["narrative_preview"]

    get_settings.cache_clear()
