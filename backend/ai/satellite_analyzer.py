"""Vulnerability scoring from upcoming satellite passes.

Consumes pass predictions in the shape produced by skyfield-style propagators
(rise/set times in UTC, peak elevation, duration). Returns a 0-100 score that
captures how soon the next imaging window opens and how favorable its
geometry is.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _parse_rise_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        log.warning("could not parse rise_time_utc: %r", value)
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _base_score_from_hours(hours: float) -> int:
    if hours < 6:
        return 100
    if hours < 12:
        return 90
    if hours < 24:
        return 80
    if hours < 48:
        return 60
    if hours < 72:
        return 40
    if hours < 168:
        return 20
    return 5


def _elevation_adjustment(elev: float) -> int:
    elev = max(0.0, min(90.0, elev))
    if elev > 60:
        return round(min(10.0, (elev - 60.0) / 3.0))
    if elev < 30:
        return -round(min(10.0, (30.0 - elev) / 3.0))
    return 0


def _zero_satellite_result(note: str) -> dict:
    return {
        "next_pass_utc": None,
        "hours_from_now": None,
        "satellite_name": None,
        "max_elevation": None,
        "vulnerability_score": 5,
        "passes_within_24h": 0,
        "raw_metrics": {
            "base_score": 5,
            "elevation_adjustment": 0,
            "total_passes_7d": 0,
        },
        "note": note,
    }


def analyze_satellite_passes(passes: list[dict]) -> dict:
    """Score the next overhead-imaging opportunity.

    Args:
        passes: list of dicts with `satellite_name`, `rise_time_utc`,
            `set_time_utc`, `max_elevation_deg`, `duration_seconds`.
            Times can be ISO 8601 strings or aware datetimes.
    """
    now = datetime.now(timezone.utc)
    parsed: list[tuple[datetime, dict]] = []
    for p in passes or []:
        rt = _parse_rise_time(p.get("rise_time_utc"))
        if rt is None:
            continue
        parsed.append((rt, p))

    if not parsed:
        return _zero_satellite_result("no upcoming passes within prediction window")

    parsed.sort(key=lambda x: x[0])
    upcoming = [(t, p) for (t, p) in parsed if t > now]
    if not upcoming:
        return _zero_satellite_result("no upcoming passes within prediction window")

    next_rise, next_p = upcoming[0]
    hours = (next_rise - now).total_seconds() / 3600.0

    base = _base_score_from_hours(hours)
    elev_raw = float(next_p.get("max_elevation_deg", 0.0))
    adjustment = _elevation_adjustment(elev_raw)
    score = max(0, min(100, round(base + adjustment)))

    passes_24h = sum(
        1 for (t, _) in upcoming if (t - now).total_seconds() <= 86400
    )
    total_7d = sum(
        1 for (t, _) in upcoming if (t - now).total_seconds() <= 7 * 86400
    )

    note = (
        "multiple imaging opportunities within 24 hours" if passes_24h > 1 else None
    )

    return {
        "next_pass_utc": next_rise.astimezone(timezone.utc).isoformat(),
        "hours_from_now": round(hours, 1),
        "satellite_name": next_p.get("satellite_name"),
        "max_elevation": max(0.0, min(90.0, elev_raw)),
        "vulnerability_score": score,
        "passes_within_24h": passes_24h,
        "raw_metrics": {
            "base_score": base,
            "elevation_adjustment": adjustment,
            "total_passes_7d": total_7d,
        },
        "note": note,
    }
