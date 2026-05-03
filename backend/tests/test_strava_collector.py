import pytest
import httpx

from app.collectors import strava
from app.collectors.strava import _cookies, _fetch_tile


def test_missing_strava_cookies_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRAVA_CF_KEY_PAIR_ID", raising=False)
    monkeypatch.delenv("STRAVA_CF_POLICY", raising=False)
    monkeypatch.delenv("STRAVA_CF_SIGNATURE", raising=False)
    monkeypatch.setattr(strava, "_dotenv_cookie_values", lambda: {})

    with pytest.raises(RuntimeError, match="Missing Strava cookies"):
        _cookies()


async def test_fetch_tile_treats_tiny_png_as_empty() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 100))
    async with httpx.AsyncClient(transport=transport) as client:
        url, blob = await _fetch_tile(client, 13, 123, 456)

    assert "content-a.strava.com" in url
    assert blob is None


async def test_fetch_tile_surfaces_auth_failure() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(403, content=b"forbidden"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(RuntimeError, match="Strava auth failed"):
            await _fetch_tile(client, 13, 123, 456)
