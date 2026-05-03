"""GHOSTLINE OpsecAssessment writeback.

Per-location pipeline:
  1. Load GhostlineGeoFeature from Foundry (lat/lon/name come from there, not hardcoded).
  2. Strava: map the cached severity finding -> density_score.
     We don't have raw heatmap PNG tiles checked in, so we can't run the
     pixel-level analyzer; the cached JSONs are at the "finding" tier already.
     For locations without a cached sample (JBLM, San Diego), density_score=0
     with a `note` field — score_calculator handles zero gracefully.
  3. ADS-B: SYNTHETIC for V1. We don't have a real historical capture yet.
     Derives plausible flight observations from the Units / Platforms already
     populated in Foundry (e.g., aviation brigades produce more military
     traffic than infantry divisions). Seeded by (slug, date) so re-runs are
     idempotent. When Member A's real ADS-B collector lands, swap
     `_synthetic_adsb` for the real fetch — the analyzer interface stays put.
  4. Satellite: REAL skyfield passes computed from CelesTrak TLEs for
     Sentinel-1A/B and Sentinel-2A/B. TLEs cached in backend/data/tle/.
  5. Combine via score_calculator + threat_brief, write through FoundryClient
     using create-opsec-assessment.

Idempotent on UUID5(slug, today's UTC date) — re-running the same day skips
already-written assessments.

Run:
    python -m backend.ai.assessment_writeback --dry-run
    python -m backend.ai.assessment_writeback --location fort_liberty
    python -m backend.ai.assessment_writeback --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import urllib.request
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .adsb_analyzer import analyze_adsb_data
from .palantir_integration import ACTIONS, FoundryClient, FoundryError
from .satellite_analyzer import analyze_satellite_passes
from .score_calculator import calculate_exposure_score
from .threat_brief import generate_threat_brief

log = logging.getLogger("ghostline.writeback")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STRAVA_CACHE_DIR = REPO_ROOT / "backend" / "data" / "cached" / "strava_samples"
TLE_CACHE_DIR = REPO_ROOT / "backend" / "data" / "tle"
SYNTH_ADSB_DIR = REPO_ROOT / "backend" / "ai" / "cached_osint"

# Stable namespace for deterministic assessment IDs.
ASSESSMENT_UUID_NS = uuid.UUID("3a47e6b1-7c5d-4f1e-8b29-1f5a4c8d9e02")

LOCATIONS: list[dict[str, Any]] = [
    {
        "slug": "fort_liberty",
        "feature_id": "geo_fort_liberty",
        "strava_cache": "fort_liberty.json",
        "civilian": False,
    },
    {
        "slug": "naval_station_norfolk",
        "feature_id": "geo_naval_station_norfolk",
        "strava_cache": "norfolk.json",
        "civilian": False,
    },
    {
        "slug": "joint_base_lewis_mcchord",
        "feature_id": "geo_joint_base_lewis_mcchord",
        "strava_cache": None,  # no cached sample on disk
        "civilian": False,
    },
    {
        "slug": "naval_base_san_diego",
        "feature_id": "geo_naval_base_san_diego",
        "strava_cache": None,
        "civilian": False,
    },
    {
        "slug": "shack15",
        "feature_id": "geo_shack15",
        "strava_cache": "san_francisco.json",
        "civilian": True,
    },
]

SENTINEL_TLES = [
    ("Sentinel-1A", 39634),
    ("Sentinel-1B", 41456),
    ("Sentinel-2A", 40697),
    ("Sentinel-2B", 42063),
]

SEVERITY_TO_DENSITY = {"high": 78, "medium": 50, "low": 25}

SYNTH_ADSB_FOOTER = (
    "\n\n[Note: ADS-B traffic is synthetic for V1 — derived from the populated "
    "Units/Platforms ontology. To be replaced by Member A's real ADS-B Exchange "
    "capture when available.]"
)


# ---------------------------------------------------------------------------
# Strava: severity -> density_score from cached finding JSON
# ---------------------------------------------------------------------------

def _load_strava_layer(loc: dict[str, Any]) -> dict[str, Any]:
    cache_name = loc.get("strava_cache")
    if not cache_name:
        return {
            "density_score": 0,
            "route_count": 0,
            "peak_hours": [],
            "hotspots": [],
            "note": "no Strava heatmap sample cached for this location",
            "data_source": "missing",
        }
    path = STRAVA_CACHE_DIR / cache_name
    if not path.exists():
        log.warning("strava cache file missing: %s", path)
        return {
            "density_score": 0, "route_count": 0, "peak_hours": [],
            "hotspots": [], "note": f"strava cache file missing: {cache_name}",
            "data_source": "missing",
        }
    payload = json.loads(path.read_text())
    severity = (payload.get("severity") or "low").lower()
    density = SEVERITY_TO_DENSITY.get(severity, 0)
    return {
        "density_score": density,
        "route_count": int(payload.get("tile_count", 0)),
        "peak_hours": ["0600-0700", "1700-1800"],  # placeholder until real time-of-day data
        "hotspots": [],  # finding-tier cache has no quadrant info
        "raw_metrics": {
            "tiles_with_activity": payload.get("tile_count"),
            "tiles_total": payload.get("tile_total"),
            "severity": severity,
            "summary": payload.get("summary"),
        },
        "evidence_urls": payload.get("evidence_urls", []),
        "data_source": "cached_finding",
    }


# ---------------------------------------------------------------------------
# ADS-B: synthetic generator anchored on the populated ontology.
# ---------------------------------------------------------------------------

# Common military aviation callsign prefixes mapped to mission profile.
_AIR_CALLSIGN_POOL = ["RAGE", "EAGLE", "REACH", "SHADOW", "RADR", "SAVAGE", "VIPER", "TALON", "STING"]
_NAVAL_CALLSIGN_POOL = ["RAYGUN", "HAMMER", "STRIKE", "VANGUARD", "TIGER", "GUNFISH", "SCREAM"]
_CIV_CALLSIGN_POOL = ["DAL", "UAL", "AAL", "SWA", "JBU", "ASA"]

_AVIATION_KEYWORDS = (
    "aviation", "wing", "squadron", "airborne", "air force", "fighter", "carrier",
    "strike", "attack", "drone", "uav", "helicopter",
)


def _is_aviation_unit(unit: dict[str, Any]) -> bool:
    name = (unit.get("name") or "").lower()
    return any(kw in name for kw in _AVIATION_KEYWORDS)


def _platform_count(platforms: list[dict[str, Any]]) -> int:
    return len([p for p in platforms if (p.get("platformType") or "").endswith(("aircraft", "helicopter", "uav"))])


def _synthetic_adsb(
    loc: dict[str, Any],
    units: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    today: date,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    """Generate plausible flight observations seeded by (slug, date)."""
    rng = random.Random(f"{loc['slug']}|{today.isoformat()}")
    aviation_units = [u for u in units if _is_aviation_unit(u)]
    air_platform_count = _platform_count(platforms)

    if loc.get("civilian"):
        n_flights, mil_ratio = rng.randint(2, 6), 0.0
    elif aviation_units or air_platform_count > 0:
        n_flights, mil_ratio = rng.randint(28, 42), 0.65
    elif units:
        # Has units but no aviation specifically — modest mil traffic.
        n_flights, mil_ratio = rng.randint(10, 18), 0.45
    else:
        # No populated units (e.g. San Diego in V1) — minimal data.
        n_flights, mil_ratio = rng.randint(4, 9), 0.25

    # Choose a small recurring-callsign pool per location for predictability signal.
    is_naval = "naval" in loc["slug"] or "norfolk" in loc["slug"]
    mil_pool = _NAVAL_CALLSIGN_POOL if is_naval else _AIR_CALLSIGN_POOL
    recurring_mil = [
        f"{rng.choice(mil_pool)}{rng.randint(1, 99):02d}"
        for _ in range(rng.randint(3, 5))
    ]
    recurring_civ = [
        f"{rng.choice(_CIV_CALLSIGN_POOL)}{rng.randint(100, 999)}"
        for _ in range(2)
    ]

    # Concentrate military traffic in two daily windows for measurable predictability.
    mil_hour_pool = [7, 8, 9, 14, 15] if not is_naval else [6, 7, 8, 13, 14]

    now = datetime.now(timezone.utc)
    flights: list[dict[str, Any]] = []
    for i in range(n_flights):
        is_mil = rng.random() < mil_ratio
        if is_mil:
            cs_pool = recurring_mil if rng.random() < 0.7 else [
                f"{rng.choice(mil_pool)}{rng.randint(1, 99):02d}"
            ]
            hour = rng.choice(mil_hour_pool)
            alt = rng.choice([5000, 8000, 12000, 18000, 25000])
            speed = rng.randint(180, 420)
        else:
            cs_pool = recurring_civ + [f"{rng.choice(_CIV_CALLSIGN_POOL)}{rng.randint(100, 999)}"]
            hour = rng.randint(6, 22)
            alt = rng.choice([20000, 28000, 35000, 38000])
            speed = rng.randint(380, 520)

        days_ago = rng.randint(0, 6)
        seen_at = (
            datetime.combine(today - timedelta(days=days_ago), time(hour=hour, minute=rng.randint(0, 59)))
            .replace(tzinfo=timezone.utc)
        )
        # Drop observations strictly in the future (rare, but possible if today's hour < seen_hour).
        if seen_at > now:
            seen_at = now - timedelta(minutes=rng.randint(5, 90))

        flights.append({
            "hex": f"AE{rng.randint(0x1000, 0xFFFF):04X}",
            "callsign": rng.choice(cs_pool),
            "lat": None,  # not used by analyzer's predictability path
            "lon": None,
            "alt_baro": alt,
            "speed": speed,
            "mil": is_mil,
            "seen_pos": seen_at,
        })

    # Cache the synthetic batch for audit replay. The "_synthetic_v1" key
    # makes it impossible to confuse with a real capture later.
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"synth_adsb_{today.isoformat()}.json"
    out.write_text(json.dumps({
        "_synthetic_v1": True,
        "_seed": f"{loc['slug']}|{today.isoformat()}",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "n_flights": n_flights,
        "mil_ratio_target": mil_ratio,
        "flights": [
            {**f, "seen_pos": f["seen_pos"].isoformat()} for f in flights
        ],
    }, indent=2))
    return flights


# ---------------------------------------------------------------------------
# Satellite: real skyfield passes from CelesTrak TLEs.
# ---------------------------------------------------------------------------

def _fetch_or_cache_tle(name: str, catnr: int) -> tuple[str, str, str] | None:
    """Return (name_line, l1, l2). Cache to TLE_CACHE_DIR for 24h."""
    TLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = TLE_CACHE_DIR / f"{name.replace(' ', '_')}.tle"
    fresh_for = timedelta(hours=24)
    if cache_file.exists():
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(
            cache_file.stat().st_mtime, tz=timezone.utc
        )
        if age < fresh_for:
            lines = cache_file.read_text().strip().splitlines()
            if len(lines) >= 3:
                return lines[0].strip(), lines[1].strip(), lines[2].strip()

    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=tle"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        log.warning("TLE fetch %s failed: %s", name, exc)
        return None
    lines = text.strip().splitlines()
    if len(lines) < 3:
        log.warning("TLE response for %s did not contain 3 lines: %r", name, text[:200])
        return None
    cache_file.write_text("\n".join(lines[:3]) + "\n")
    return lines[0].strip(), lines[1].strip(), lines[2].strip()


def _compute_passes(lat: float, lon: float, days: int = 7) -> list[dict[str, Any]]:
    try:
        from skyfield.api import EarthSatellite, load, wgs84
    except ImportError:
        log.warning("skyfield not installed; satellite layer will be empty")
        return []

    ts = load.timescale()
    t0 = ts.now()
    end_dt = datetime.now(timezone.utc) + timedelta(days=days)
    t1 = ts.from_datetime(end_dt)
    observer = wgs84.latlon(lat, lon)

    passes: list[dict[str, Any]] = []
    for name, catnr in SENTINEL_TLES:
        tle = _fetch_or_cache_tle(name, catnr)
        if tle is None:
            continue
        try:
            sat = EarthSatellite(tle[1], tle[2], name, ts)
            t_events, events = sat.find_events(observer, t0, t1, altitude_degrees=10.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("skyfield failed for %s: %s", name, exc)
            continue
        # Group events into rise/culminate/set triples.
        i = 0
        while i + 2 < len(events):
            if events[i] == 0 and events[i + 1] == 1 and events[i + 2] == 2:
                rise = t_events[i].utc_datetime()
                culm = t_events[i + 1]
                sett = t_events[i + 2].utc_datetime()
                try:
                    alt, _, _ = (sat - observer).at(culm).altaz()
                    elev = float(alt.degrees)
                except Exception as exc:  # noqa: BLE001
                    log.warning("alt computation failed for %s: %s", name, exc)
                    elev = 0.0
                passes.append({
                    "satellite_name": name,
                    "rise_time_utc": rise.astimezone(timezone.utc).isoformat(),
                    "set_time_utc": sett.astimezone(timezone.utc).isoformat(),
                    "max_elevation_deg": elev,
                    "duration_seconds": (sett - rise).total_seconds(),
                })
                i += 3
            else:
                i += 1
    return passes


# ---------------------------------------------------------------------------
# Per-location assessment
# ---------------------------------------------------------------------------

def _fetch_geo(client: FoundryClient, feature_id: str) -> dict[str, Any] | None:
    try:
        return client.get_object("GhostlineGeoFeature", feature_id)
    except FoundryError as exc:
        log.error("get_object %s failed: %s", feature_id, exc)
        return None


def _fetch_units_for(client: FoundryClient, feature_id: str) -> list[dict[str, Any]]:
    try:
        return client.get_linked_objects("GhostlineGeoFeature", feature_id, "units", page_size=50)
    except FoundryError as exc:
        log.warning("get_linked_objects units for %s failed: %s", feature_id, exc)
        return []


def _fetch_platforms_for(client: FoundryClient, units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Walk each unit's `unit` reverse-link for its platforms."""
    out: list[dict[str, Any]] = []
    for u in units:
        pk = u.get("unitId")
        if not pk:
            continue
        try:
            out.extend(client.get_linked_objects("GhostlineUnit", pk, "unit", page_size=20))
        except FoundryError as exc:
            log.debug("get_linked_objects unit-platforms for %s: %s", pk, exc)
    return out


def assessment_id_for(slug: str, when: date) -> str:
    return str(uuid.uuid5(ASSESSMENT_UUID_NS, f"{slug}|{when.isoformat()}"))


def build_assessment_for_location(
    client: FoundryClient,
    loc: dict[str, Any],
    today: date,
) -> dict[str, Any] | None:
    """Run all three analyzers + score + threat brief. Returns an assessment payload or None."""
    geo = _fetch_geo(client, loc["feature_id"])
    if geo is None:
        log.error("no GhostlineGeoFeature for %s — run osint_populator first", loc["slug"])
        return None

    location_name = geo.get("name") or loc["slug"]
    lat = float(geo["latitude"])
    lon = float(geo["longitude"])

    units = _fetch_units_for(client, loc["feature_id"])
    platforms = _fetch_platforms_for(client, units)
    log.info(
        "%s: %d units, %d platforms in ontology",
        loc["slug"], len(units), len(platforms),
    )

    strava_layer = _load_strava_layer(loc)

    cache_dir = SYNTH_ADSB_DIR / loc["slug"]
    flights = _synthetic_adsb(loc, units, platforms, today, cache_dir)
    adsb_layer = analyze_adsb_data(flights, days=7)
    adsb_layer["data_source"] = "synthetic_v1_pending_real_capture"

    passes = _compute_passes(lat, lon, days=7)
    sat_layer = analyze_satellite_passes(passes)

    score = calculate_exposure_score(
        strava_score=int(strava_layer.get("density_score", 0)),
        adsb_score=int(adsb_layer.get("predictability_score", 0)),
        satellite_score=int(sat_layer.get("vulnerability_score", 0)),
        base_modifier=50,
    )

    brief_input = {
        "location": location_name,
        "lat": lat,
        "lon": lon,
        "strava": strava_layer,
        "adsb": adsb_layer,
        "satellite": sat_layer,
        "base_modifier": 50,
    }
    brief_result = generate_threat_brief(brief_input)
    brief_text = brief_result["brief"] + SYNTH_ADSB_FOOTER

    aid = assessment_id_for(loc["slug"], today)
    timestamp = datetime.now(timezone.utc).isoformat()

    params = {
        "assessment-id": aid,
        "location-name": location_name,
        "assessment-timestamp": timestamp,
        "exposure-score": int(score["exposure_score"]),
        "aircraft-predictability-score": int(adsb_layer.get("predictability_score", 0)),
        "satellite-vulnerability-score": int(sat_layer.get("vulnerability_score", 0)),
        "strava-density-score": int(strava_layer.get("density_score", 0)),
        "latitude": lat,
        "longitude": lon,
        "threat-brief": brief_text,
    }

    return {
        "params": params,
        "exposure_score": score["exposure_score"],
        "risk_level": score["risk_level"],
        "score_breakdown": score["breakdown"],
        "layers": {
            "strava": strava_layer,
            "adsb": adsb_layer,
            "satellite": sat_layer,
        },
        "brief": brief_text,
    }


def write_assessment(
    client: FoundryClient,
    assessment: dict[str, Any],
    *,
    dry_run: bool,
) -> str:
    params = assessment["params"]
    aid = params["assessment-id"]
    if dry_run:
        print(f"  [DRY] OpsecAssessment[{aid}]")
        print(f"        location: {params['location-name']}  ({params['latitude']:.4f}, {params['longitude']:.4f})")
        print(f"        scores: exposure={params['exposure-score']}  strava={params['strava-density-score']}  "
              f"adsb={params['aircraft-predictability-score']}  sat={params['satellite-vulnerability-score']}")
        print(f"        risk: {assessment['risk_level']}")
        print(f"        brief preview ({len(assessment['brief'])} chars):")
        for line in assessment["brief"].splitlines()[:6]:
            print(f"          {line[:120]}")
        return "dry-run"

    try:
        existing = client.get_object("OpsecAssessment", aid)
    except FoundryError as exc:
        log.warning("idempotency check failed for %s: %s", aid, exc)
        existing = None
    if existing is not None:
        log.info("OpsecAssessment[%s] already exists — skipping", aid)
        return "exists"

    try:
        client.apply_action(ACTIONS["OpsecAssessment"], params)
    except FoundryError as exc:
        log.error("create OpsecAssessment[%s] failed: %s", aid, exc)
        return "failed"

    try:
        readback = client.get_object("OpsecAssessment", aid)
    except FoundryError as exc:
        log.error("read-back OpsecAssessment[%s] failed: %s", aid, exc)
        return "failed"
    if readback is None:
        log.error("WROTE BUT VANISHED: OpsecAssessment[%s]", aid)
        return "failed"

    log.info("created OpsecAssessment[%s]", aid)
    return "created"


# ---------------------------------------------------------------------------
# Verify mode
# ---------------------------------------------------------------------------

def verify_assessments(client: FoundryClient) -> None:
    print("\n=== Verify: OpsecAssessment objects in Foundry ===")
    try:
        objs = client.list_objects("OpsecAssessment", page_size=200)
    except FoundryError as exc:
        print(f"  ERROR listing: {exc}")
        return
    print(f"  total: {len(objs)}")
    for o in sorted(objs, key=lambda x: x.get("locationName") or ""):
        aid = o.get("assessmentId")
        loc = o.get("locationName")
        score = o.get("exposureScore")
        ts = o.get("assessmentTimestamp")
        brief_len = len(o.get("threatBrief") or "")
        print(f"  - {aid}")
        print(f"      location: {loc}   exposure: {score}   ts: {ts}")
        print(f"      strava={o.get('stravaDensityScore')} adsb={o.get('aircraftPredictabilityScore')} "
              f"sat={o.get('satelliteVulnerabilityScore')}   brief: {brief_len} chars")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Write OpsecAssessment objects per location.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--location", action="append", default=[])
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    selected = set(args.location)
    locations = [L for L in LOCATIONS if not selected or L["slug"] in selected]
    if selected and not locations:
        print(f"No locations match {sorted(selected)}. Available: {[L['slug'] for L in LOCATIONS]}")
        return 2

    try:
        client = FoundryClient()
    except FoundryError as exc:
        print(f"Foundry config error: {exc}")
        return 2

    only_verify = args.verify and not args.dry_run and not args.location
    today = datetime.now(timezone.utc).date()

    summary = {"created": 0, "exists": 0, "failed": 0, "dry-run": 0, "no-data": 0}
    if not only_verify:
        for loc in locations:
            print(f"\n=== {loc['slug']} ===")
            assessment = build_assessment_for_location(client, loc, today)
            if assessment is None:
                summary["no-data"] += 1
                continue
            result = write_assessment(client, assessment, dry_run=args.dry_run)
            summary[result] = summary.get(result, 0) + 1

        print("\n=== Writeback summary ===")
        print(f"  {summary}")

    if args.verify:
        verify_assessments(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
