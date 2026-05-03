"""Pattern-of-life analysis on historical ADS-B observations.

Consumes a list of one-observation-per-record dicts (extended-normalized
shape — see module-level type hints). Produces a 0-100 predictability
score plus the recurring callsigns and time-of-day / day-of-week patterns
that an adversary would exploit.

`normalize_adsbx_record` adapts a raw ADS-B Exchange API record (with
relative `seen` offset) into the extended shape so a future historical
collector can feed this analyzer directly.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_RECURRING_THRESHOLD = 3
_PEAK_WINDOW_HOURS = 4
_DAY_SIGNIFICANCE_RATIO = 0.20
_MIN_MIL_FOR_DAY_PATTERN = 6
_MIN_DISTINCT_DATES_FOR_DAY_PATTERN = 3


def _zero_adsb_result(note: str) -> dict:
    return {
        "military_flights_7d": 0,
        "civilian_flights_7d": 0,
        "recurring_callsigns": [],
        "predictability_score": 0,
        "pattern": "No consistent military pattern",
        "raw_metrics": {
            "total_observations": 0,
            "military_ratio": 0.0,
            "recurring_count": 0,
            "temporal_concentration": 0.0,
            "peak_hour_window": None,
            "peak_days": [],
        },
        "note": note,
    }


def _parse_seen_pos(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _consecutive_weekdays(day_indices: list[int]) -> bool:
    if len(day_indices) < 2:
        return False
    s = sorted(day_indices)
    return all(s[i] + 1 == s[i + 1] for i in range(len(s) - 1))


def normalize_adsbx_record(raw: dict, snapshot_time: datetime) -> dict | None:
    """Adapt a raw ADS-B Exchange record to the extended-normalized shape.

    Returns None if the record lacks usable lat/lon.
    """
    lat = raw.get("lat")
    lon = raw.get("lon")
    if lat is None or lon is None:
        return None

    callsign = (raw.get("flight") or "").strip() or None

    alt_raw = raw.get("alt_baro")
    if isinstance(alt_raw, str) and alt_raw.lower() == "ground":
        alt_baro: float | None = 0.0
    elif alt_raw is None:
        alt_baro = None
    else:
        try:
            alt_baro = float(alt_raw)
        except (TypeError, ValueError):
            alt_baro = None

    speed_raw = raw.get("gs")
    try:
        speed: float | None = float(speed_raw) if speed_raw is not None else None
    except (TypeError, ValueError):
        speed = None

    if snapshot_time.tzinfo is None:
        snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)
    seen_seconds = float(raw.get("seen") or 0.0)
    seen_pos = snapshot_time - timedelta(seconds=seen_seconds)

    return {
        "hex": str(raw.get("hex", "")),
        "callsign": callsign,
        "lat": float(lat),
        "lon": float(lon),
        "alt_baro": alt_baro,
        "speed": speed,
        "mil": bool(raw.get("mil") or False),
        "seen_pos": seen_pos,
    }


def analyze_adsb_data(flights: list[dict], days: int = 7) -> dict:
    """Score predictability of military air activity from historical observations.

    Args:
        flights: list of observations in the extended-normalized shape:
            {hex, callsign, lat, lon, alt_baro, speed, mil, seen_pos}.
        days: lookback window. Observations older than now-days are dropped.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    filtered: list[dict] = []
    for f in flights or []:
        seen = _parse_seen_pos(f.get("seen_pos"))
        if seen is None or seen < cutoff:
            continue
        item = dict(f)
        item["seen_pos"] = seen
        filtered.append(item)

    if not filtered:
        return _zero_adsb_result("no observations in lookback window")

    mil_obs = [f for f in filtered if f.get("mil") is True]
    civilian_obs = [f for f in filtered if f.get("mil") is not True]
    mil_count = len(mil_obs)
    civilian_count = len(civilian_obs)
    total = len(filtered)

    callsign_counter: Counter[str] = Counter()
    for f in mil_obs:
        cs = (f.get("callsign") or "").strip().upper()
        if cs:
            callsign_counter[cs] += 1
    recurring = sorted(
        cs for cs, n in callsign_counter.items() if n >= _RECURRING_THRESHOLD
    )
    recurring_count = len(recurring)

    if mil_count == 0:
        peak_hour_window: str | None = None
        temporal_concentration = 0.0
        best_start = 0
    else:
        hour_counts = [0] * 24
        for f in mil_obs:
            hour_counts[f["seen_pos"].hour] += 1
        best_start = 0
        best_sum = -1
        for start in range(24):
            window_sum = sum(
                hour_counts[(start + i) % 24] for i in range(_PEAK_WINDOW_HOURS)
            )
            if window_sum > best_sum:
                best_sum = window_sum
                best_start = start
        end_hour = (best_start + _PEAK_WINDOW_HOURS) % 24
        peak_hour_window = f"{best_start:02d}00-{end_hour:02d}00"
        temporal_concentration = best_sum / mil_count if mil_count else 0.0

    peak_days: list[str] = []
    consecutive_days = False
    if mil_count >= _MIN_MIL_FOR_DAY_PATTERN:
        distinct_dates = {f["seen_pos"].date() for f in mil_obs}
        if len(distinct_dates) >= _MIN_DISTINCT_DATES_FOR_DAY_PATTERN:
            day_counter: Counter[int] = Counter(f["seen_pos"].weekday() for f in mil_obs)
            threshold = _DAY_SIGNIFICANCE_RATIO * mil_count
            significant = [
                (idx, n)
                for idx, n in day_counter.items()
                if n >= threshold
            ]
            significant.sort(key=lambda x: -x[1])
            top = significant[:3]
            top_indices = sorted(idx for idx, _ in top)
            peak_days = [_DAY_NAMES[i] for i in top_indices]
            consecutive_days = _consecutive_weekdays(top_indices)

    if mil_count < 3:
        pattern = "No consistent military pattern"
    elif not peak_days:
        pattern = f"{peak_hour_window} concentration"
    elif len(peak_days) >= 2 and consecutive_days:
        pattern = f"{peak_days[0]}-{peak_days[-1]} concentration, {peak_hour_window}"
    elif len(peak_days) >= 2:
        pattern = f"{'/'.join(peak_days)} concentration, {peak_hour_window}"
    else:
        pattern = f"{peak_days[0]} concentration, {peak_hour_window}"

    mil_ratio = min(1.0, mil_count / max(1, total))
    score = round(
        mil_ratio * 30
        + min(recurring_count * 10, 30)
        + temporal_concentration * 40
    )
    score = max(0, min(100, score))

    return {
        "military_flights_7d": mil_count,
        "civilian_flights_7d": civilian_count,
        "recurring_callsigns": recurring,
        "predictability_score": score,
        "pattern": pattern,
        "raw_metrics": {
            "total_observations": total,
            "military_ratio": round(mil_ratio, 3),
            "recurring_count": recurring_count,
            "temporal_concentration": round(temporal_concentration, 3),
            "peak_hour_window": peak_hour_window,
            "peak_days": peak_days,
        },
        "note": None,
    }
