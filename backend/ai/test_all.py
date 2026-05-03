"""Smoke test for the GHOSTLINE AI layer.

Run from the repo root:
    python -m backend.ai.test_all

Sections (in order):
    1. STRAVA ANALYZER     — synthetic tile dir → density / hotspot / routes
    2. ADS-B ANALYZER      — synthetic flight log → recurring callsigns / pattern
    3. SATELLITE ANALYZER  — synthetic upcoming passes → vulnerability score
    4. PIPELINE            — end-to-end run with all synthetic inputs
    5. SCORE CALCULATOR    — original SAMPLE_ASSESSMENT shape
    6. THREAT BRIEF        — original SAMPLE_ASSESSMENT (real LLM call, judges' tone check)
    7. MITIGATION ENGINE   — original SAMPLE_ASSESSMENT
    8. PALANTIR            — write attempt (skips without creds)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from .adsb_analyzer import analyze_adsb_data
from .mitigation_engine import generate_mitigations
from .palantir_integration import write_assessment_to_palantir
from .pipeline import run_full_assessment
from .satellite_analyzer import analyze_satellite_passes
from .score_calculator import calculate_exposure_score
from .strava_analyzer import analyze_strava_tiles
from .threat_brief import generate_threat_brief


SAMPLE_ASSESSMENT = {
    "location": "Fort Liberty, NC",
    "lat": 35.139,
    "lon": -78.997,
    "strava": {
        "density_score": 78,
        "route_count": 47,
        "peak_hours": ["0600-0700", "1700-1800"],
        "hotspots": ["eastern perimeter", "main gate area"],
    },
    "adsb": {
        "military_flights_7d": 23,
        "civilian_flights_7d": 156,
        "recurring_callsigns": ["SHADOW6", "EAGLE7", "RADR12"],
        "predictability_score": 65,
        "pattern": "Tuesday-Thursday concentration, 0800-1200",
    },
    "satellite": {
        "next_pass_utc": "2026-05-03T14:30:00Z",
        "hours_from_now": 14.5,
        "satellite_name": "Sentinel-2B",
        "max_elevation": 72,
        "vulnerability_score": 85,
    },
}


HR = "=" * 70


def _section(title: str) -> None:
    print(f"\n{HR}\n  {title}\n{HR}")


def _make_synthetic_tile_dir() -> Path:
    """Build a tiny slippy-layout tile dir with most activity in the NE quadrant."""
    base = Path(tempfile.mkdtemp(prefix="ghostline_strava_"))
    z = 13
    # Three NE/SE tiles bright, one SW dark — center is at lat/lon between them.
    tiles = [
        (2298, 3239, 220),  # NE (lon east, lat north)
        (2298, 3240, 200),  # SE
        (2297, 3239, 60),   # NW dim
        (2297, 3240, 0),    # SW empty
    ]
    for x, y, brightness in tiles:
        sub = base / str(z) / str(x)
        sub.mkdir(parents=True, exist_ok=True)
        arr = np.zeros((128, 128, 3), dtype=np.uint8)
        if brightness > 0:
            arr[40:44, 10:120, :] = brightness
            arr[80:84, 30:100, :] = brightness
        Image.fromarray(arr, "RGB").save(sub / f"{y}.png")
    return base


def _make_synthetic_flights() -> list[dict]:
    """Mil-heavy fixture: SHADOW6 + EAGLE7 recurring; Tue/Thu cluster, 0800-1200."""
    now = datetime.now(timezone.utc)
    flights: list[dict] = []
    for d in range(14):  # 2 weeks, so multiple Tue/Thu dates
        day = now - timedelta(days=d)
        wd = day.weekday()
        if wd in (1, 3):
            for h in (8, 9, 10, 11):
                flights.append({
                    "hex": "AE0001",
                    "callsign": "SHADOW6",
                    "lat": 35.14,
                    "lon": -78.99,
                    "alt_baro": 5500,
                    "speed": 220,
                    "mil": True,
                    "seen_pos": day.replace(hour=h, minute=15, second=0, microsecond=0),
                })
            flights.append({
                "hex": "AE0002",
                "callsign": "EAGLE7",
                "lat": 35.14,
                "lon": -78.99,
                "alt_baro": 4200,
                "speed": 200,
                "mil": True,
                "seen_pos": day.replace(hour=10, minute=30, second=0, microsecond=0),
            })
        flights.append({
            "hex": "A12345",
            "callsign": f"DAL{200 + d}",
            "lat": 35.20,
            "lon": -79.00,
            "alt_baro": 35000,
            "speed": 480,
            "mil": False,
            "seen_pos": day.replace(hour=14, minute=0, second=0, microsecond=0),
        })
    return flights


def _make_synthetic_passes() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "satellite_name": "Sentinel-2B",
            "rise_time_utc": (now + timedelta(hours=14, minutes=30)).isoformat(),
            "set_time_utc": (now + timedelta(hours=14, minutes=38)).isoformat(),
            "max_elevation_deg": 72.0,
            "duration_seconds": 480,
        },
        {
            "satellite_name": "WorldView-3",
            "rise_time_utc": (now + timedelta(hours=20)).isoformat(),
            "set_time_utc": (now + timedelta(hours=20, minutes=6)).isoformat(),
            "max_elevation_deg": 45.0,
            "duration_seconds": 360,
        },
        {
            "satellite_name": "Landsat-9",
            "rise_time_utc": (now + timedelta(days=2, hours=4)).isoformat(),
            "set_time_utc": (now + timedelta(days=2, hours=4, minutes=8)).isoformat(),
            "max_elevation_deg": 35.0,
            "duration_seconds": 480,
        },
    ]


def main() -> int:
    tile_dir: Path | None = None
    try:
        _section("STRAVA ANALYZER — synthetic tiles")
        tile_dir = _make_synthetic_tile_dir()
        strava_result = analyze_strava_tiles(tile_dir, 35.139, -78.997)
        print(json.dumps(strava_result, indent=2))

        _section("ADS-B ANALYZER — synthetic flights")
        flights = _make_synthetic_flights()
        adsb_result = analyze_adsb_data(flights)
        print(json.dumps(adsb_result, indent=2))

        _section("SATELLITE ANALYZER — synthetic passes")
        passes = _make_synthetic_passes()
        sat_result = analyze_satellite_passes(passes)
        print(json.dumps(sat_result, indent=2))

        _section("PIPELINE — full run with synthetic inputs")
        full = run_full_assessment(
            location="Fort Liberty (synthetic)",
            lat=35.139,
            lon=-78.997,
            strava_tile_dir=str(tile_dir),
            adsb_flights=flights,
            satellite_passes=passes,
        )
        print(f"  exposure_score: {full['exposure_score']}  risk: {full['risk_level']}")
        print(f"  brief word count: {len(full['brief'].split())}")
        print(f"  mitigations: {len(full['mitigations'])}")
        print(f"  palantir_written: {full['palantir_written']}")
        print("\n  --- BRIEF ---")
        print(full["brief"])
    finally:
        if tile_dir is not None and tile_dir.exists():
            shutil.rmtree(tile_dir, ignore_errors=True)

    _section("INPUT — original SAMPLE_ASSESSMENT (Fort Liberty demo)")
    print(json.dumps(SAMPLE_ASSESSMENT, indent=2))

    _section("SCORE CALCULATOR — composite exposure")
    score = calculate_exposure_score(
        strava_score=SAMPLE_ASSESSMENT["strava"]["density_score"],
        adsb_score=SAMPLE_ASSESSMENT["adsb"]["predictability_score"],
        satellite_score=SAMPLE_ASSESSMENT["satellite"]["vulnerability_score"],
    )
    print(json.dumps(score, indent=2))

    _section("THREAT BRIEF — LLM output (this gets spoken aloud)")
    brief_result = generate_threat_brief(SAMPLE_ASSESSMENT)
    print(brief_result["brief"])
    print(
        f"\n[exposure_score={brief_result['exposure_score']}  "
        f"risk_level={brief_result['risk_level']}]"
    )
    print(f"[word_count={len(brief_result['brief'].split())}  target=150-200]")

    _section("MITIGATION ENGINE — deterministic recommendations")
    mitigations = generate_mitigations(
        score_breakdown=brief_result["score_breakdown"],
        layer_inputs={
            "strava": SAMPLE_ASSESSMENT["strava"],
            "adsb": SAMPLE_ASSESSMENT["adsb"],
            "satellite": SAMPLE_ASSESSMENT["satellite"],
        },
    )
    running = brief_result["exposure_score"]
    for m in mitigations:
        running += m["score_delta"]
        print(
            f"  [{m['priority']}] {m['action']}\n"
            f"      delta={m['score_delta']:+d}  "
            f"target={m['target_layer']}  "
            f"running_score={max(0, running)}\n"
            f"      why: {m['reasoning']}\n"
        )

    final = max(
        0, brief_result["exposure_score"] + sum(m["score_delta"] for m in mitigations)
    )
    print(
        f"  Composite trajectory: {brief_result['exposure_score']} -> {final} "
        f"(target ~19 for the demo)"
    )

    _section("PALANTIR — write attempt (skips without creds)")
    wrote = write_assessment_to_palantir({
        **brief_result,
        "location": SAMPLE_ASSESSMENT["location"],
        "lat": SAMPLE_ASSESSMENT["lat"],
        "lon": SAMPLE_ASSESSMENT["lon"],
    })
    print(f"  write_assessment_to_palantir -> {wrote}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
