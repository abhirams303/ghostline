from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.utils import geocoder


def nominatim_response(status_code: int, payload: Any) -> httpx.Response:
    request = httpx.Request("GET", "https://nominatim.test/search")
    return httpx.Response(status_code, json=payload, request=request)


def make_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv(
        "OPSEC_MIRROR_DATABASE_PATH", str(tmp_path / "opsec-mirror-test.sqlite3")
    )
    monkeypatch.setenv("OPSEC_MIRROR_NOMINATIM_BASE_URL", "https://nominatim.test")
    monkeypatch.setenv("OPSEC_MIRROR_NOMINATIM_USER_AGENT", "OPSEC-Mirror-Test/0.1")
    get_settings.cache_clear()
    geocoder.clear_geocode_cache()
    return TestClient(create_app())


def test_geocode_resolves_nominatim_payload(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    captured: dict[str, Any] = {}

    async def fake_request_nominatim(**kwargs):
        captured.update(kwargs)
        return nominatim_response(
            200,
            [
                {
                    "display_name": "Area 51, Lincoln County, Nevada, United States",
                    "lat": "37.2431",
                    "lon": "-115.7930",
                }
            ],
        )

    monkeypatch.setattr(geocoder, "_request_nominatim", fake_request_nominatim)

    response = client.get("/geocode", params={"q": "Area 51"})

    assert response.status_code == 200
    assert response.json() == {
        "name": "Area 51, Lincoln County, Nevada, United States",
        "lat": 37.2431,
        "lon": -115.793,
        "radius_km": 15.0,
    }
    assert captured["url"] == "https://nominatim.test/search"
    assert captured["params"] == {
        "q": "area 51",
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 0,
    }


def test_geocode_rejects_blank_query(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    response = client.get("/geocode", params={"q": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "Geocode query cannot be blank."


def test_geocode_returns_404_for_no_match(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    async def fake_request_nominatim(**kwargs):
        return nominatim_response(200, [])

    monkeypatch.setattr(geocoder, "_request_nominatim", fake_request_nominatim)

    response = client.get("/geocode", params={"q": "not a real place"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Location could not be resolved."


def test_geocode_returns_502_for_upstream_error(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    async def failing_request_nominatim(**kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(geocoder, "_request_nominatim", failing_request_nominatim)

    response = client.get("/geocode", params={"q": "Area 51"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Nominatim geocoding request failed."


def test_geocode_sends_identifying_user_agent(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    captured: dict[str, Any] = {}

    async def fake_request_nominatim(**kwargs):
        captured.update(kwargs)
        return nominatim_response(
            200,
            [
                {
                    "display_name": "Fort Liberty, North Carolina, United States",
                    "lat": "35.1414",
                    "lon": "-79.006",
                }
            ],
        )

    monkeypatch.setattr(geocoder, "_request_nominatim", fake_request_nominatim)

    response = client.get("/geocode", params={"q": "Fort Liberty"})

    assert response.status_code == 200
    assert captured["headers"]["User-Agent"] == "OPSEC-Mirror-Test/0.1"
    assert "python-httpx" not in captured["headers"]["User-Agent"].lower()
