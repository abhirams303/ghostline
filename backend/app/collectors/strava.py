from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import httpx
from dotenv import dotenv_values

try:
    import mercantile
except ModuleNotFoundError:
    mercantile = None

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload

TILE_URL = (
    "https://content-a.strava.com/identified/globalheat/"
    "{activity}/{color}/{z}/{x}/{y}@2x.png?v=19"
)
EMPTY_TILE_BYTES = 500
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0"
    ),
    "Referer": "https://www.strava.com/maps/global-heatmap",
}


@lru_cache(maxsize=1)
def _dotenv_cookie_values() -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return {}
    return {
        key: value
        for key, value in dotenv_values(env_path).items()
        if isinstance(value, str) and value
    }


def _cookie_env(name: str) -> str | None:
    return os.environ.get(name) or _dotenv_cookie_values().get(name)


def _cookies() -> dict[str, str]:
    required = ["STRAVA_CF_KEY_PAIR_ID", "STRAVA_CF_POLICY", "STRAVA_CF_SIGNATURE"]
    missing = [key for key in required if not _cookie_env(key)]
    if missing:
        raise RuntimeError(
            f"Missing Strava cookies: {missing}. "
            "Grab them from https://www.strava.com/maps/global-heatmap "
            "using browser dev tools for content-a.strava.com."
        )

    cookies = {
        "CloudFront-Key-Pair-Id": _cookie_env("STRAVA_CF_KEY_PAIR_ID"),
        "CloudFront-Policy": _cookie_env("STRAVA_CF_POLICY"),
        "CloudFront-Signature": _cookie_env("STRAVA_CF_SIGNATURE"),
    }

    optional_cookies = {
        "_strava_idcf": _cookie_env("STRAVA_IDCF"),
        "_strava_CloudFront-Expires": _cookie_env("STRAVA_CF_EXPIRES"),
    }
    cookies.update(
        {name: value for name, value in optional_cookies.items() if value}
    )
    return cookies


async def _fetch_tile(
    client: httpx.AsyncClient,
    z: int,
    x: int,
    y: int,
    activity: str = "all",
    color: str = "blue",
) -> tuple[str, bytes | None]:
    url = TILE_URL.format(activity=activity, color=color, z=z, x=x, y=y)
    response = await client.get(url)

    if response.status_code in (401, 403):
        raise RuntimeError(
            f"Strava auth failed ({response.status_code}). Cookies expired or wrong domain."
        )
    if response.status_code != 200 or len(response.content) < EMPTY_TILE_BYTES:
        return url, None
    return url, response.content


async def collect_strava_heatmap(lat: float, lon: float, zoom: int = 13) -> dict:
    if mercantile is None:
        raise RuntimeError(
            "Strava collection requires the optional 'mercantile' dependency. "
            "Install backend dependencies with `python -m pip install -e .[dev]` from `backend/`."
        )

    center = mercantile.tile(lon, lat, zoom)
    coords = [
        (center.x + dx, center.y + dy)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
    ]

    async with httpx.AsyncClient(cookies=_cookies(), headers=HEADERS, timeout=15) as client:
        results = await asyncio.gather(
            *[_fetch_tile(client, zoom, x, y) for x, y in coords]
        )

    hits = [(url, blob) for url, blob in results if blob is not None]

    if len(hits) >= 7:
        severity = "high"
    elif len(hits) >= 4:
        severity = "medium"
    elif hits:
        severity = "low"
    else:
        severity = "low"

    return {
        "source": "strava",
        "severity": severity,
        "title": f"Public fitness activity in {len(hits)}/9 surrounding tiles",
        "summary": (
            f"Aggregated Strava activity is publicly visible at zoom {zoom} "
            f"around ({lat:.4f}, {lon:.4f}). Patterns may reveal PT routes, "
            "perimeters, or routine movement."
        ),
        "evidence_urls": [url for url, _ in hits[:3]],
        "tile_count": len(hits),
        "tile_total": 9,
        "zoom": zoom,
        "tiles": [{"url": url} for url, _ in hits],
    }


class StravaCollector(BaseCollector):
    source = "strava"

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        settings = get_settings()
        if not settings.strava_enabled:
            return self._stub_response(request)

        result = await collect_strava_heatmap(request.target.lat, request.target.lon)
        finding = Finding(
            source="strava",
            title=result["title"],
            severity=result["severity"],
            summary=result["summary"],
            evidence_url=(result["evidence_urls"][0] if result["evidence_urls"] else None),
            geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
            ts=datetime.now(timezone.utc),
            metadata={
                "collector": self.source,
                "mode": "live",
                "tile_count": result["tile_count"],
                "tile_total": result["tile_total"],
                "zoom": result["zoom"],
                "evidence_urls": result["evidence_urls"],
            },
        )
        layer = MapLayerPayload(
            id="strava-heatmap",
            type="heatmap",
            data=[
                {
                    "position": [request.target.lon, request.target.lat],
                    "weight": min(1, result["tile_count"] / result["tile_total"]),
                    "tile_count": result["tile_count"],
                    "tile_total": result["tile_total"],
                    "zoom": result["zoom"],
                    "tiles": result["tiles"],
                }
            ],
        )
        return [finding], [layer]

    def _stub_response(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        finding = Finding(
            source="strava",
            title="Mobility heat signature near target perimeter",
            severity="high",
            summary="Exercise traces indicate repeated movement corridors adjacent to the target area.",
            geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
            ts=datetime.now(timezone.utc),
            metadata={"status": "stub", "collector": self.source},
        )
        layer = MapLayerPayload(
            id="strava-heatmap",
            type="heatmap",
            data=[
                {
                    "position": [request.target.lon, request.target.lat],
                    "weight": 0.9,
                }
            ],
        )
        return [finding], [layer]
