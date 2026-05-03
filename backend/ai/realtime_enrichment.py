"""GHOSTLINE realtime enrichment — lat/lon-keyed live data, no Foundry writes.

Three live sources + a parallel master fetch. Every function:
  - Caches results in-memory for 60s (lat/lon rounded to 4 decimals for key match).
  - Has a 5-second timeout on the upstream call.
  - Returns a graceful {"error": str, "data_available": False} on failure rather
    than raising — the voice agent must always get something back.

The master function `get_full_current_state` runs all three in parallel via a
ThreadPoolExecutor and reports which sub-fetches succeeded.

Run:
    python -m backend.ai.realtime_enrichment --test fort-liberty
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv
from math import cos, radians

# Intra-package reuse: these are "private" by Python convention but live in
# the same backend.ai package. Promoting them later (or extracting to a
# satellite_passes module) is a no-op refactor if a third consumer appears.
from .assessment_writeback import (
    SENTINEL_TLES,
    _compute_passes,
    _fetch_or_cache_tle,
)

load_dotenv()
log = logging.getLogger("ghostline.realtime")

CACHE_TTL_SECONDS = 60.0
HTTP_TIMEOUT = 5.0
GROUND_TRACK_SAMPLE_SECONDS = 30

# FlightRadar24 has no "is military" flag in its public flight records, so we
# use heuristics: callsign prefix list (US military aviation tactical / mission
# call signs) plus US-military hex-block prefixes (AE/AF/AD).
MIL_CALLSIGN_PREFIXES = (
    "RCH", "REACH", "SHADOW", "EAGLE", "NAVY", "EVAC", "PAT", "GUARD", "DUKE",
    "RAGE", "VIPER", "KNIFE", "TOPCAT", "HAVOC", "SAVAGE", "GUNFIGHTER",
    "SAM", "MAGMA", "VAPOR", "WAVE", "GUNFISH", "RAYGUN", "HAMMER", "STRIKE",
    "VANGUARD", "TIGER", "SCREAM", "CONVOY", "TALON", "STING",
)

# ---------------------------------------------------------------------------
# In-memory cache (thread-safe)
# ---------------------------------------------------------------------------

_cache: dict[tuple, tuple[Any, float]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: tuple) -> Any | None:
    with _cache_lock:
        entry = _cache.get(key)
    if entry is None:
        return None
    value, fetched_at = entry
    if time.monotonic() - fetched_at > CACHE_TTL_SECONDS:
        return None
    return value


def _cache_put(key: tuple, value: Any) -> None:
    with _cache_lock:
        _cache[key] = (value, time.monotonic())


def _key_latlon(lat: float, lon: float) -> tuple[float, float]:
    """Round to 4 decimals (~11m precision) so cache hits aren't lost to float jitter."""
    return (round(float(lat), 4), round(float(lon), 4))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Aircraft (FlightRadar24 free Python API)
# ---------------------------------------------------------------------------

def _is_military_callsign(callsign: str | None) -> bool:
    """True if the callsign starts with a known US-military aviation prefix."""
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in MIL_CALLSIGN_PREFIXES)


def _is_military_hex(hex_id: str | None) -> bool:
    """True if the hex code falls inside the US-military allocated block (AE/AF).

    Only AE0000-AFFFFF is military; AD-prefix codes are FAA-assigned civilian
    (verified empirically — AD-prefixed flights observed are AAL/DAL commercial
    with N-number registrations)."""
    if not hex_id:
        return False
    return hex_id.upper().startswith(("AE", "AF"))


def get_live_aircraft(lat: float, lon: float, radius_nm: int = 25) -> dict[str, Any]:
    """Live aircraft within radius_nm of lat/lon via FlightRadar24's free API.

    No API key required. Military detection is heuristic (callsign prefix +
    US-mil hex blocks) since FR24 doesn't expose a `mil` flag.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        radius_nm: Search radius in nautical miles (default 25).

    Returns:
        Dict with keys: center, radius_nm, aircraft_count, military_count, aircraft,
        queried_at, source, data_available. Each entry in `aircraft` has hex,
        callsign, lat, lon, altitude, speed, heading, aircraft_type, is_military.
        On failure: {"error": "...", "data_available": False, ...empty fields}.
    """
    key = ("aircraft", *_key_latlon(lat, lon), int(radius_nm))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        # Lazy-import so a missing FR24 install doesn't break module load
        # (the rest of realtime_enrichment + query_api stays usable).
        from FlightRadar24 import FlightRadar24API
    except ImportError as exc:
        result = _aircraft_error(
            lat, lon, radius_nm,
            f"FlightRadar24 package not installed: {exc} — pip install FlightRadarAPI",
        )
        _cache_put(key, result)
        return result

    try:
        # Convert nm radius to FR24's bounds string. FR24 expects the order
        # "north,south,west,east" (NOT north/south/east/west — verified
        # empirically: a north/south/east/west string returns flights from
        # across the country because FR24 interprets the lon pair as
        # west=more-negative, east=less-negative).
        # 1° lat ≈ 60 nm; longitude scales by cos(latitude) (max(0.01, …)
        # guards against poles).
        delta_lat = radius_nm / 60.0
        delta_lon = radius_nm / (60.0 * max(0.01, cos(radians(lat))))
        bounds = (
            f"{lat + delta_lat:.6f},"
            f"{lat - delta_lat:.6f},"
            f"{lon - delta_lon:.6f},"
            f"{lon + delta_lon:.6f}"
        )
        fr = FlightRadar24API()
        flights = fr.get_flights(bounds=bounds)
    except Exception as exc:  # noqa: BLE001 — collectors must not raise
        log.warning("FlightRadar24 fetch failed: %s", exc)
        result = _aircraft_error(lat, lon, radius_nm, str(exc))
        _cache_put(key, result)
        return result

    aircraft: list[dict[str, Any]] = []
    military_count = 0
    for f in flights or []:
        try:
            callsign = (getattr(f, "callsign", None) or "").strip() or None
            # FR24 exposes both the FR24 internal flight id (`f.id`, 8-char) and
            # the canonical ICAO 24-bit hex (`f.icao_24bit`, 6-char). The hex
            # block heuristic only works on the real ICAO hex.
            icao_hex = (getattr(f, "icao_24bit", None) or "").strip()
            is_mil = _is_military_callsign(callsign) or _is_military_hex(icao_hex)
            if is_mil:
                military_count += 1
            aircraft.append({
                "hex": icao_hex,                                          # ICAO 24-bit hex
                "fr24_id": (getattr(f, "id", None) or "").strip(),         # FR24 internal id
                "callsign": callsign,
                "registration": getattr(f, "registration", "") or "",
                "lat": getattr(f, "latitude", None),
                "lon": getattr(f, "longitude", None),
                "altitude": getattr(f, "altitude", None),
                "speed": getattr(f, "ground_speed", None),
                "heading": getattr(f, "heading", None),
                "aircraft_type": getattr(f, "aircraft_code", "") or "",
                "airline_icao": getattr(f, "airline_icao", "") or "",
                "is_military": is_mil,
            })
        except Exception as exc:  # noqa: BLE001 — skip a single malformed record
            log.debug("skipped malformed FR24 flight record: %s", exc)
            continue

    result = {
        "center": {"lat": float(lat), "lon": float(lon)},
        "radius_nm": int(radius_nm),
        "aircraft_count": len(aircraft),
        "military_count": military_count,
        "aircraft": aircraft,
        "queried_at": _now_iso(),
        "source": "flightradar24",
        "data_available": True,
    }
    _cache_put(key, result)
    return result


def _aircraft_error(lat: float, lon: float, radius_nm: int, msg: str) -> dict[str, Any]:
    return {
        "error": msg,
        "data_available": False,
        "center": {"lat": float(lat), "lon": float(lon)},
        "radius_nm": int(radius_nm),
        "aircraft_count": 0,
        "military_count": 0,
        "aircraft": [],
        "queried_at": _now_iso(),
        "source": "flightradar24",
    }


# ---------------------------------------------------------------------------
# 2. Satellite passes (skyfield + CelesTrak TLEs)
# ---------------------------------------------------------------------------

def _ground_track_for_pass(
    sat_name: str, rise_dt: datetime, set_dt: datetime
) -> list[dict[str, Any]]:
    """Sample the satellite's subpoint every 30s during the pass window."""
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ImportError:
        return []
    tle = _fetch_or_cache_tle(sat_name, _catnr_for(sat_name))
    if tle is None:
        return []
    ts = load.timescale()
    sat = EarthSatellite(tle[1], tle[2], sat_name, ts)
    track: list[dict[str, Any]] = []
    duration_s = max(1, int((set_dt - rise_dt).total_seconds()))
    step = max(GROUND_TRACK_SAMPLE_SECONDS, 1)
    offset = 0
    while offset <= duration_s:
        sample_dt = rise_dt + timedelta(seconds=offset)
        try:
            sub = wgs84.subpoint(sat.at(ts.from_datetime(sample_dt)))
            track.append({
                "lat": float(sub.latitude.degrees),
                "lon": float(sub.longitude.degrees),
                "time_offset_sec": offset,
            })
        except Exception as exc:  # noqa: BLE001
            log.debug("subpoint sample failed at offset %s: %s", offset, exc)
        offset += step
    return track


def _catnr_for(sat_name: str) -> int:
    for name, catnr in SENTINEL_TLES:
        if name == sat_name:
            return catnr
    return 0


def get_satellite_passes(lat: float, lon: float, hours_ahead: int = 24) -> dict[str, Any]:
    """Upcoming satellite imaging passes overhead lat/lon within the next hours_ahead.

    Computes against real Sentinel-1A/B and Sentinel-2A/B TLEs from CelesTrak.

    Args:
        lat: Observer latitude in decimal degrees.
        lon: Observer longitude in decimal degrees.
        hours_ahead: Lookahead window (default 24h).

    Returns:
        Dict with keys: next_pass (or None), passes_in_window, all_passes, queried_at.
        Each pass has satellite, rise_utc, set_utc, max_elevation_deg, duration_seconds.
        next_pass additionally carries ground_track sampled at 30s intervals.
    """
    key = ("sat_passes", *_key_latlon(lat, lon), int(hours_ahead))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        # _compute_passes already pulls Sentinel TLEs and uses a 7-day window;
        # we filter to hours_ahead below.
        all_raw = _compute_passes(float(lat), float(lon), days=max(1, (hours_ahead + 23) // 24))
    except Exception as exc:  # noqa: BLE001
        log.warning("satellite passes computation failed: %s", exc)
        result = {
            "error": f"compute failed: {exc}",
            "data_available": False,
            "next_pass": None,
            "passes_in_window": 0,
            "all_passes": [],
            "queried_at": _now_iso(),
        }
        _cache_put(key, result)
        return result

    cutoff = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
    in_window: list[dict[str, Any]] = []
    for p in all_raw:
        try:
            rise = datetime.fromisoformat(p["rise_time_utc"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if rise <= cutoff:
            in_window.append({
                "satellite": p.get("satellite_name"),
                "rise_utc": p.get("rise_time_utc"),
                "set_utc": p.get("set_time_utc"),
                "max_elevation_deg": p.get("max_elevation_deg"),
                "duration_seconds": p.get("duration_seconds"),
            })

    in_window.sort(key=lambda x: x["rise_utc"] or "")

    next_pass: dict[str, Any] | None = None
    if in_window:
        first = dict(in_window[0])  # don't mutate the all_passes copy
        try:
            rise_dt = datetime.fromisoformat(first["rise_utc"].replace("Z", "+00:00"))
            set_dt = datetime.fromisoformat(first["set_utc"].replace("Z", "+00:00"))
            first["ground_track"] = _ground_track_for_pass(first["satellite"], rise_dt, set_dt)
        except (KeyError, ValueError, AttributeError):
            first["ground_track"] = []
        next_pass = first

    result = {
        "next_pass": next_pass,
        "passes_in_window": len(in_window),
        "all_passes": in_window,
        "queried_at": _now_iso(),
        "data_available": True,
    }
    _cache_put(key, result)
    return result


# ---------------------------------------------------------------------------
# 3. Recent news (Exa.ai with date filter)
# ---------------------------------------------------------------------------

def get_recent_news(location_name: str, hours: int = 24) -> dict[str, Any]:
    """Recent news mentions of a location via Exa.ai semantic search.

    Args:
        location_name: Search anchor, e.g. "Naval Station Norfolk".
        hours: How far back to look (default 24h).

    Returns:
        Dict with keys: article_count, articles, queried_at. Each article has
        title, url, published_at, snippet. {error, data_available: False} on failure.
    """
    key = ("news", location_name.lower(), int(hours))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        result = {
            "error": "EXA_API_KEY missing in .env",
            "data_available": False,
            "article_count": 0,
            "articles": [],
            "queried_at": _now_iso(),
        }
        _cache_put(key, result)
        return result

    start_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    body = {
        "query": f"recent news {location_name}",
        "numResults": 5,
        "type": "neural",
        "useAutoprompt": True,
        "startPublishedDate": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "contents": {"text": True},
    }
    try:
        resp = requests.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        log.warning("Exa news request failed: %s", exc)
        result = {
            "error": f"network: {exc}",
            "data_available": False,
            "article_count": 0,
            "articles": [],
            "queried_at": _now_iso(),
        }
        _cache_put(key, result)
        return result
    if not resp.ok:
        body_text = (resp.text or "")[:200]
        result = {
            "error": f"HTTP {resp.status_code}: {body_text}",
            "data_available": False,
            "article_count": 0,
            "articles": [],
            "queried_at": _now_iso(),
        }
        _cache_put(key, result)
        return result
    payload = resp.json()
    articles: list[dict[str, Any]] = []
    for r in payload.get("results", []):
        text = (r.get("text") or "").strip()
        snippet = text[:300] + ("..." if len(text) > 300 else "")
        articles.append({
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "published_at": r.get("publishedDate") or r.get("published_date"),
            "snippet": snippet,
            "score": r.get("score"),
        })

    result = {
        "article_count": len(articles),
        "articles": articles,
        "queried_at": _now_iso(),
        "data_available": True,
    }
    _cache_put(key, result)
    return result


# ---------------------------------------------------------------------------
# 4. Master parallel fetch
# ---------------------------------------------------------------------------

def get_full_current_state(
    lat: float, lon: float, location_name: str
) -> dict[str, Any]:
    """Combined live-state snapshot — calls aircraft, satellite, and news in parallel.

    Args:
        lat: Center latitude.
        lon: Center longitude.
        location_name: Used for the news query and reporting.

    Returns:
        Dict with keys: center, location_name, aircraft, satellite, news,
        sources_succeeded (list of source names that returned data), queried_at.
    """
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_air = ex.submit(get_live_aircraft, lat, lon)
        f_sat = ex.submit(get_satellite_passes, lat, lon)
        f_news = ex.submit(get_recent_news, location_name)
        aircraft = f_air.result()
        satellite = f_sat.result()
        news = f_news.result()

    succeeded: list[str] = []
    if aircraft.get("data_available"):
        succeeded.append("aircraft")
    if satellite.get("data_available"):
        succeeded.append("satellite")
    if news.get("data_available"):
        succeeded.append("news")

    return {
        "center": {"lat": float(lat), "lon": float(lon)},
        "location_name": location_name,
        "aircraft": aircraft,
        "satellite": satellite,
        "news": news,
        "sources_succeeded": succeeded,
        "queried_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# CLI test mode
# ---------------------------------------------------------------------------

LOCATION_FIXTURES = {
    "fort-liberty": (35.139, -78.997, "Fort Liberty"),
    "norfolk": (36.9466, -76.3013, "Naval Station Norfolk"),
    "jblm": (47.0876, -122.5726, "Joint Base Lewis-McChord"),
    "san-diego": (32.6839, -117.1286, "Naval Base San Diego"),
    "shack15": (37.7955, -122.3937, "Shack15"),
}


def _print_summary(state: dict[str, Any]) -> None:
    print(f"\n=== {state['location_name']} "
          f"({state['center']['lat']}, {state['center']['lon']}) ===")
    print(f"  sources_succeeded: {state['sources_succeeded']}")

    air = state["aircraft"]
    print(f"\n  AIRCRAFT  ({air.get('aircraft_count', 0)} total, "
          f"{air.get('military_count', 0)} military, source={air.get('source')})")
    if air.get("error"):
        print(f"    error: {air['error']}")
    for a in (air.get("aircraft") or [])[:5]:
        mil = " [MIL]" if a["is_military"] else ""
        print(
            f"    {a['hex']:8s} {a['callsign'] or '':10s} "
            f"alt={a['altitude']!s:>6s} spd={a['speed']!s:>4s}{mil}"
        )

    sat = state["satellite"]
    print(f"\n  SATELLITE  (passes_in_window={sat.get('passes_in_window', 0)})")
    if sat.get("error"):
        print(f"    error: {sat['error']}")
    if sat.get("next_pass"):
        n = sat["next_pass"]
        track_n = len(n.get("ground_track") or [])
        print(f"    next: {n['satellite']}  rise={n['rise_utc']}  "
              f"max_elev={n['max_elevation_deg']:.1f}°  ground_track_samples={track_n}")
    for p in (sat.get("all_passes") or [])[1:4]:
        print(f"      then: {p['satellite']}  rise={p['rise_utc']}  "
              f"max_elev={p['max_elevation_deg']:.1f}°")

    news = state["news"]
    print(f"\n  NEWS  ({news.get('article_count', 0)} articles)")
    if news.get("error"):
        print(f"    error: {news['error']}")
    for a in (news.get("articles") or [])[:3]:
        print(f"    - {a['title'][:80]}")
        print(f"      {a['url']}")
        print(f"      published: {a.get('published_at')}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Realtime enrichment CLI test.")
    p.add_argument("--test", choices=sorted(LOCATION_FIXTURES.keys()),
                   help="Run live test against one of the locked locations.")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if not args.test:
        p.print_help()
        return 0

    lat, lon, name = LOCATION_FIXTURES[args.test]
    print(f"Querying live state for {name} ({lat}, {lon})…")
    state = get_full_current_state(lat, lon, name)
    _print_summary(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
