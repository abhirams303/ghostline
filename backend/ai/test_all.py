"""Smoke test for the GHOSTLINE AI layer.

Run from the repo root:
    python -m backend.ai.test_all

Prints:
    - Threat brief (the spoken text — judge this for tone)
    - Composite exposure score and per-layer breakdown
    - Mitigation list with score deltas and post-mitigation projection
    - Palantir write attempt (will skip without creds — that's expected)
"""

from __future__ import annotations

import json
import sys

from .mitigation_engine import generate_mitigations
from .palantir_integration import write_assessment_to_palantir
from .score_calculator import calculate_exposure_score
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


def main() -> int:
    _section("INPUT — assessment payload")
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
    word_count = len(brief_result["brief"].split())
    print(f"[word_count={word_count}  target=150-200]")

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

    final = max(0, brief_result["exposure_score"] + sum(m["score_delta"] for m in mitigations))
    print(
        f"  Composite trajectory: {brief_result['exposure_score']} -> {final} "
        f"(target ~19 for the demo)"
    )

    _section("PALANTIR — write attempt (skips without creds)")
    payload_for_foundry = {
        **brief_result,
        "location": SAMPLE_ASSESSMENT["location"],
        "lat": SAMPLE_ASSESSMENT["lat"],
        "lon": SAMPLE_ASSESSMENT["lon"],
    }
    wrote = write_assessment_to_palantir(payload_for_foundry)
    print(f"  write_assessment_to_palantir -> {wrote}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
