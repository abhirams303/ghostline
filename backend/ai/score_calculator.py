"""Exposure score calculator. Pure, deterministic, no side effects."""

from __future__ import annotations

WEIGHT_STRAVA = 0.40
WEIGHT_ADSB = 0.30
WEIGHT_SATELLITE = 0.20
WEIGHT_BASE_MODIFIER = 0.10


def _risk_level(score: int) -> str:
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MEDIUM"
    return "HIGH"


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def calculate_exposure_score(
    strava_score: int,
    adsb_score: int,
    satellite_score: int,
    base_modifier: int = 50,
) -> dict:
    s = _clamp(int(strava_score))
    a = _clamp(int(adsb_score))
    sat = _clamp(int(satellite_score))
    base = _clamp(int(base_modifier))

    weighted = {
        "strava": round(s * WEIGHT_STRAVA, 1),
        "adsb": round(a * WEIGHT_ADSB, 1),
        "satellite": round(sat * WEIGHT_SATELLITE, 1),
        "base_modifier": round(base * WEIGHT_BASE_MODIFIER, 1),
    }

    total = sum(weighted.values())
    exposure_score = _clamp(round(total))

    return {
        "exposure_score": exposure_score,
        "risk_level": _risk_level(exposure_score),
        "breakdown": {
            "strava": {"raw": s, "weighted": weighted["strava"]},
            "adsb": {"raw": a, "weighted": weighted["adsb"]},
            "satellite": {"raw": sat, "weighted": weighted["satellite"]},
            "base_modifier": {"raw": base, "weighted": weighted["base_modifier"]},
        },
    }
