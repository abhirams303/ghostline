"""Deterministic mitigation recommendation engine.

No LLM calls — the demo must produce identical mitigations every run so the
animated score-reduction sequence is reliable on stage.

Each mitigation models a percentage reduction on one (or more) raw layer
scores, then converts that reduction back into composite-score points using
the same weights as `score_calculator`. That keeps the math consistent: if
the user clicks every mitigation, the composite drops by exactly the sum of
the score_deltas.
"""

from __future__ import annotations

from typing import Any

from .score_calculator import (
    WEIGHT_ADSB,
    WEIGHT_BASE_MODIFIER,
    WEIGHT_SATELLITE,
    WEIGHT_STRAVA,
)


def _delta_from_layer(raw_score: int, percent_reduction: float, weight: float) -> int:
    """Convert a raw-score percent cut into a composite-score delta (negative)."""
    raw_drop = raw_score * percent_reduction
    weighted_drop = raw_drop * weight
    return -int(round(weighted_drop))


def _strava_mitigation(strava: dict, breakdown: dict) -> dict:
    raw = breakdown["strava"]["raw"]
    hotspots = strava.get("hotspots") or []
    hotspot_clause = (
        f" Priority area: {hotspots[0]}." if hotspots else ""
    )
    return {
        "id": 1,
        "action": "Enforce Strava privacy settings for all personnel."
        + hotspot_clause,
        "score_delta": _delta_from_layer(raw, 0.75, WEIGHT_STRAVA),
        "target_layer": "strava",
        "reasoning": (
            "Removes ~75% of fitness-app exposure by blocking public heatmap "
            "contribution and segment leaderboards."
        ),
        "priority": 0,  # filled in after sort
    }


def _adsb_mitigation(adsb: dict, breakdown: dict) -> dict:
    raw = breakdown["adsb"]["raw"]
    callsigns = adsb.get("recurring_callsigns") or []
    if callsigns:
        callsign_str = ", ".join(callsigns)
        action = (
            f"File FAA LADD callsign-blocking request for {callsign_str}."
        )
        reasoning = (
            f"Hides {len(callsigns)} recurring military callsign(s) from public "
            "ADS-B feeds, breaking pattern-of-life on flight ops."
        )
    else:
        action = "Coordinate FAA LADD enrollment for tail numbers servicing this installation."
        reasoning = (
            "Removes military flight patterns from public ADS-B aggregators."
        )
    return {
        "id": 2,
        "action": action,
        "score_delta": _delta_from_layer(raw, 0.70, WEIGHT_ADSB),
        "target_layer": "adsb",
        "reasoning": reasoning,
        "priority": 0,
    }


def _satellite_mitigation(satellite: dict, breakdown: dict) -> dict:
    raw = breakdown["satellite"]["raw"]
    hours = satellite.get("hours_from_now")
    sat_name = satellite.get("satellite_name", "next overhead pass")
    imminent = isinstance(hours, (int, float)) and hours < 24

    if imminent:
        action = (
            f"Reschedule outdoor staging and equipment movement outside the "
            f"{hours:.1f}-hour {sat_name} imaging window."
        )
        percent = 0.90
    else:
        action = (
            f"Stage covered hangars or camo for sensitive assets ahead of {sat_name} pass."
        )
        percent = 0.50

    return {
        "id": 3,
        "action": action,
        "score_delta": _delta_from_layer(raw, percent, WEIGHT_SATELLITE),
        "target_layer": "satellite",
        "reasoning": (
            "Denies optical collection during the predicted imaging window."
            if imminent
            else "Reduces overhead-imagery signature on routine passes."
        ),
        "priority": 0,
    }


def _general_mitigation(breakdown: dict) -> dict:
    # 10% off each public-vector layer, plus drop the base modifier in half.
    delta = (
        _delta_from_layer(breakdown["strava"]["raw"], 0.10, WEIGHT_STRAVA)
        + _delta_from_layer(breakdown["adsb"]["raw"], 0.10, WEIGHT_ADSB)
        + _delta_from_layer(breakdown["satellite"]["raw"], 0.10, WEIGHT_SATELLITE)
        + _delta_from_layer(breakdown["base_modifier"]["raw"], 0.50, WEIGHT_BASE_MODIFIER)
    )
    return {
        "id": 4,
        "action": "Issue OPSEC directive: disable geotagging on all personal devices.",
        "score_delta": delta,
        "target_layer": "general",
        "reasoning": (
            "Reduces social-media and photo location leakage across every "
            "exposure vector simultaneously."
        ),
        "priority": 0,
    }


def _pt_variation_mitigation(strava: dict, breakdown: dict) -> dict | None:
    raw = breakdown["strava"]["raw"]
    if raw < 60:
        return None
    peak = strava.get("peak_hours") or []
    peak_str = (
        f" currently clustered {', '.join(peak)}" if peak else ""
    )
    return {
        "id": 5,
        "action": (
            "Mandate weekly randomization of PT routes and start times"
            + peak_str
            + "."
        ),
        # Smaller incremental cut on top of the privacy push.
        "score_delta": _delta_from_layer(raw, 0.10, WEIGHT_STRAVA),
        "target_layer": "strava",
        "reasoning": (
            "Defeats temporal pattern-of-life inference even when fitness data leaks."
        ),
        "priority": 0,
    }


def generate_mitigations(
    score_breakdown: dict,
    layer_inputs: dict[str, Any] | None = None,
) -> list[dict]:
    """Produce 4-5 deterministic mitigations ordered by impact.

    Args:
        score_breakdown: the `breakdown` dict returned by `calculate_exposure_score`.
        layer_inputs: original per-layer input (the `strava`/`adsb`/`satellite`
            sub-dicts from the assessment payload). Used so action text can
            quote real callsigns, hotspots, and pass timing.
    """
    layer_inputs = layer_inputs or {}
    strava = layer_inputs.get("strava", {}) or {}
    adsb = layer_inputs.get("adsb", {}) or {}
    satellite = layer_inputs.get("satellite", {}) or {}

    candidates: list[dict] = [
        _strava_mitigation(strava, score_breakdown),
        _adsb_mitigation(adsb, score_breakdown),
        _satellite_mitigation(satellite, score_breakdown),
        _general_mitigation(score_breakdown),
    ]

    pt_extra = _pt_variation_mitigation(strava, score_breakdown)
    if pt_extra is not None:
        candidates.append(pt_extra)

    # Order by absolute impact (largest score reduction first).
    candidates.sort(key=lambda m: m["score_delta"])

    for idx, m in enumerate(candidates, start=1):
        m["priority"] = idx

    return candidates
