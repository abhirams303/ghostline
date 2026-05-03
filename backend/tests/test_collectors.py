import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.collectors.adsb import ADSBCollector
from app.config import get_settings
from app.main import create_app


def make_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    database_path = tmp_path / "opsec-mirror-test.sqlite3"
    monkeypatch.setenv("OPSEC_MIRROR_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("OPSEC_MIRROR_ADSB_ENABLED", "false")
    monkeypatch.delenv("ADSBEXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("OPSEC_MIRROR_ADSBEXCHANGE_API_KEY", raising=False)
    get_settings.cache_clear()
    return TestClient(create_app()), database_path


def test_healthcheck(tmp_path: Path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_analyze(tmp_path: Path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
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


def test_live_analyze_without_openai_key_uses_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPSEC_MIRROR_OPENAI_API_KEY", raising=False)
    client, database_path = make_client(tmp_path, monkeypatch)

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

    with sqlite3.connect(database_path) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        document_count = connection.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0]

    assert run_count == 1
    assert finding_count == len(body["findings"])
    assert document_count == len(body["findings"])

    get_settings.cache_clear()


def test_repeated_live_runs_dedupe_source_documents(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPSEC_MIRROR_OPENAI_API_KEY", raising=False)
    client, database_path = make_client(tmp_path, monkeypatch)

    payload = {
        "target": {
            "name": "Fort Liberty",
            "lat": 35.1414,
            "lon": -79.006,
            "radius_km": 20,
        },
        "mode": "live",
    }

    first = client.post("/analyze", json=payload)
    second = client.post("/analyze", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200

    with sqlite3.connect(database_path) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        document_count = connection.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0]
        run_document_count = connection.execute("SELECT COUNT(*) FROM run_documents").fetchone()[0]

    assert run_count == 2
    assert finding_count == 6
    assert document_count == 3
    assert run_document_count == 6

    get_settings.cache_clear()


def test_adsb_collector_normalizes_live_payload(tmp_path: Path, monkeypatch) -> None:
    client, database_path = make_client(tmp_path, monkeypatch)
    monkeypatch.setenv("OPSEC_MIRROR_ADSB_ENABLED", "true")
    monkeypatch.setenv("ADSBEXCHANGE_API_KEY", "test-uuid")
    get_settings.cache_clear()

    sample_payload = {
        "ac": [
            {
                "hex": "abc123",
                "flight": "TEST123 ",
                "lat": 35.16,
                "lon": -79.02,
                "alt_baro": 3200,
                "gs": 180,
                "track": 91,
                "seen": 1.2,
            },
            {
                "hex": "def456",
                "flight": "TEST456 ",
                "lat": 35.12,
                "lon": -79.01,
                "alt_baro": "ground",
                "gs": 22,
                "track": 10,
                "seen": 0.5,
            },
        ]
    }

    async def fake_fetch(self, request):
        return sample_payload

    monkeypatch.setattr(ADSBCollector, "_fetch_aircraft_payload", fake_fetch)

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
    adsb_findings = [finding for finding in body["findings"] if finding["source"] == "adsb"]
    adsb_layers = [layer for layer in body["layers"] if layer["id"] == "adsb-live-markers"]

    assert len(adsb_findings) == 2
    assert adsb_layers
    assert adsb_layers[0]["type"] == "marker"
    assert adsb_layers[0]["data"][0]["hex"] == "abc123"

    with sqlite3.connect(database_path) as connection:
        finding_count = connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0]

    assert finding_count == len(body["findings"])

    get_settings.cache_clear()
