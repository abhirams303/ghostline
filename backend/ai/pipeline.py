"""Full assessment orchestrator.

`run_full_assessment` is the single entry point the FastAPI `/assess`
endpoint will call. It runs the three analyzers, drives the threat brief +
mitigation engine, and best-effort writes the result to Palantir Foundry.

Per-layer input has a three-tier fallback so a 90-second demo runs even
without live collectors:

    1. Caller passes real upstream data → run the analyzer on it.
    2. Caller passes None and `cached_results/<location>_<layer>.json`
       exists → use the cached analyzer output (written by
       `cache_real_data.py` once Member B has real Strava tiles cached).
    3. Otherwise → use the baked-in `_DEMO_*` fixture and log a WARNING.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adsb_analyzer import analyze_adsb_data
from .mitigation_engine import generate_mitigations
from .palantir_integration import write_assessment_to_palantir
from .satellite_analyzer import analyze_satellite_passes
from .strava_analyzer import analyze_strava_tiles
from .threat_brief import generate_threat_brief

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cached_results"


_DEMO_STRAVA = {
    "density_score": 78,
    "route_count": 47,
    "peak_hours": ["0600-0700", "1700-1800"],
    "hotspots": ["eastern perimeter"],
    "raw_metrics": {
        "tiles_analyzed": 9,
        "total_pixels": 589824,
        "active_pixels": 41440,
        "avg_brightness": 142.3,
        "density_ratio": 0.0703,
        "layout": "slippy",
    },
    "note": "demo fallback — not real data",
}

_DEMO_ADSB = {
    "military_flights_7d": 23,
    "civilian_flights_7d": 156,
    "recurring_callsigns": ["EAGLE7", "RADR12", "SHADOW6"],
    "predictability_score": 65,
    "pattern": "Tuesday-Thursday concentration, 0800-1200",
    "raw_metrics": {
        "total_observations": 179,
        "military_ratio": 0.128,
        "recurring_count": 3,
        "temporal_concentration": 0.67,
        "peak_hour_window": "0800-1200",
        "peak_days": ["Tuesday", "Thursday"],
    },
    "note": "demo fallback — not real data",
}


def _demo_satellite() -> dict:
    # Generated dynamically so hours_from_now is fresh on every demo run.
    now = datetime.now(timezone.utc)
    return {
        "next_pass_utc": (now + timedelta(hours=14, minutes=30)).isoformat(),
        "hours_from_now": 14.5,
        "satellite_name": "Sentinel-2B",
        "max_elevation": 72.0,
        "vulnerability_score": 84,
        "passes_within_24h": 1,
        "raw_metrics": {
            "base_score": 80,
            "elevation_adjustment": 4,
            "total_passes_7d": 8,
        },
        "note": "demo fallback — not real data",
    }


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _load_cached_layer(location: str, layer: str) -> dict | None:
    path = CACHE_DIR / f"{slugify(location)}_{layer}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("pipeline: could not load cached %s for %s: %s", layer, location, exc)
        return None


def run_full_assessment(
    location: str,
    lat: float,
    lon: float,
    strava_tile_dir: str | None = None,
    adsb_flights: list[dict] | None = None,
    satellite_passes: list[dict] | None = None,
    base_modifier: int = 50,
) -> dict:
    """Run analyzers → threat brief → mitigations → Palantir write."""

    if strava_tile_dir is not None:
        strava = analyze_strava_tiles(strava_tile_dir, lat, lon)
    else:
        strava = _load_cached_layer(location, "strava")
        if strava is None:
            log.warning("pipeline: using demo strava fixture for %s", location)
            strava = dict(_DEMO_STRAVA)

    if adsb_flights is not None:
        adsb = analyze_adsb_data(adsb_flights)
    else:
        adsb = _load_cached_layer(location, "adsb")
        if adsb is None:
            log.warning("pipeline: using demo adsb fixture for %s", location)
            adsb = dict(_DEMO_ADSB)

    if satellite_passes is not None:
        satellite = analyze_satellite_passes(satellite_passes)
    else:
        satellite = _load_cached_layer(location, "satellite")
        if satellite is None:
            log.warning("pipeline: using demo satellite fixture for %s", location)
            satellite = _demo_satellite()

    assessment_data = {
        "location": location,
        "lat": lat,
        "lon": lon,
        "strava": strava,
        "adsb": adsb,
        "satellite": satellite,
        "base_modifier": base_modifier,
    }

    brief_result = generate_threat_brief(assessment_data)

    mitigations = generate_mitigations(
        score_breakdown=brief_result["score_breakdown"],
        layer_inputs={
            "strava": strava,
            "adsb": adsb,
            "satellite": satellite,
        },
    )

    result = {
        "assessment_id": str(uuid.uuid4()),
        "assessment_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": location,
        "lat": lat,
        "lon": lon,
        "strava": strava,
        "adsb": adsb,
        "satellite": satellite,
        "exposure_score": brief_result["exposure_score"],
        "risk_level": brief_result["risk_level"],
        "score_breakdown": brief_result["score_breakdown"],
        "brief": brief_result["brief"],
        "mitigations": mitigations,
    }

    try:
        result["palantir_written"] = bool(write_assessment_to_palantir(result))
    except Exception as exc:  # noqa: BLE001 — pipeline must not crash on Palantir failure
        log.error("pipeline: palantir write failed: %s", exc)
        result["palantir_written"] = False

    return result
