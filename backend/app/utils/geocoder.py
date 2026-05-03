import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.models.location import LocationInput

NOMINATIM_MIN_INTERVAL_SECONDS = 1.0
DEFAULT_GEOCODE_RADIUS_KM = 15


class GeocodeError(RuntimeError):
    """Raised when Nominatim cannot be reached or returns malformed data."""


@dataclass(frozen=True)
class GeocodeCacheEntry:
    target: LocationInput
    expires_at: float


_cache: dict[str, GeocodeCacheEntry] = {}
_rate_limit_lock = asyncio.Lock()
_last_request_at = 0.0


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def clear_geocode_cache() -> None:
    _cache.clear()


async def geocode_location(query: str) -> LocationInput | None:
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return None

    now = time.monotonic()
    cached = _cache.get(normalized_query)
    if cached and cached.expires_at > now:
        return cached.target

    settings = get_settings()
    payload = await _fetch_nominatim_results(normalized_query, settings)
    target = _parse_first_result(payload)
    if target:
        _cache[normalized_query] = GeocodeCacheEntry(
            target=target,
            expires_at=now + settings.cache_ttl_seconds,
        )
    return target


async def _fetch_nominatim_results(
    normalized_query: str, settings: Settings
) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {
        "q": normalized_query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 0,
    }
    if settings.nominatim_email:
        params["email"] = settings.nominatim_email

    headers = {"User-Agent": settings.nominatim_user_agent}
    url = f"{settings.nominatim_base_url.rstrip('/')}/search"

    try:
        response = await _request_nominatim(
            url=url,
            params=params,
            headers=headers,
            timeout=settings.nominatim_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodeError("Nominatim geocoding request failed.") from exc

    if not isinstance(payload, list):
        raise GeocodeError("Nominatim returned an unexpected response shape.")

    return [item for item in payload if isinstance(item, dict)]


async def _request_nominatim(
    *,
    url: str,
    params: dict[str, str | int],
    headers: dict[str, str],
    timeout: float,
) -> httpx.Response:
    global _last_request_at

    async with _rate_limit_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < NOMINATIM_MIN_INTERVAL_SECONDS:
            await asyncio.sleep(NOMINATIM_MIN_INTERVAL_SECONDS - elapsed)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params, headers=headers)
        _last_request_at = time.monotonic()
        return response


def _parse_first_result(payload: list[dict[str, Any]]) -> LocationInput | None:
    if not payload:
        return None

    result = payload[0]
    try:
        lat = float(result["lat"])
        lon = float(result["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise GeocodeError("Nominatim result did not include valid coordinates.") from exc

    display_name = result.get("display_name")
    name = display_name.strip() if isinstance(display_name, str) else ""
    if not name:
        name = str(result.get("name") or "Resolved location")

    return LocationInput(
        name=name,
        lat=lat,
        lon=lon,
        radius_km=DEFAULT_GEOCODE_RADIUS_KM,
    )
