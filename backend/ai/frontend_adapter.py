"""Adapter that maps GHOSTLINE query_api responses into the MissionReport JSON
shape the teammate's deck.gl frontend expects.

The contract is fixed by his TypeScript types in
~/Desktop/bang_sec/command-deck/src/domain/types.ts:

    MissionReport {
      runId, target, generatedAt, mode, score, findings, layers, narrative,
      mitigationPriorities, aip
    }

with constrained enums:
    Severity = "critical" | "high" | "medium" | "low"
    CollectorSource = "adsb" | "exa" | "satellite" | "strava" | "palantir" | "mapbox"
    MapLayer.type = "column" | "heatmap" | "path" | "marker" | "polygon" | "footprint"
    MapLayer.tone = "green" | "amber" | "red" | "blue"
    SyncState = "not_synced" | "syncing" | "synced" | "failed"

Direct in-process query_api import (no HTTP) so we automatically get the
in-memory cache + disk cache fallback that query_api already provides.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from . import osint_sources, query_api

# Cap how many representative unit/platform/sensor markers we render. Beyond
# ~12 the deck.gl marker layer turns into visual noise; the panel UI lists
# the full chain via cascade endpoints anyway.
MAX_LINKED_MARKERS = 12

# Spread radius for the synthetic ring of linked-entity markers around the
# base center. Tight enough to obviously cluster on the base, loose enough
# that markers don't fully overlap on a typical zoom.
LINKED_RING_RADIUS_KM = 2.5

DEFAULT_RADIUS_KM = 24
DEFAULT_THEATER = "CONUS"

# Severity mapping for adversary actions, per spec.
TIMELINE_TO_SEVERITY: dict[str, str] = {
    "immediate": "critical",
    "days": "high",
    "weeks": "medium",
    "months": "low",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str | None, n: int = 300) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _ring_position(
    center_lat: float, center_lon: float, index: int, total: int, radius_km: float
) -> list[float]:
    """Even-spread point on a small ring around (center_lat, center_lon).

    Returns deck.gl-order [lon, lat]. Used for representative markers when
    the underlying entities don't carry their own coordinates."""
    angle = (2.0 * math.pi * index) / max(1, total)
    delta_lat_deg = (radius_km / 111.32) * math.cos(angle)
    cos_lat = max(0.01, math.cos(math.radians(center_lat)))
    delta_lon_deg = (radius_km / (111.32 * cos_lat)) * math.sin(angle)
    return [center_lon + delta_lon_deg, center_lat + delta_lat_deg]


def _action_severity(timeline: str | None) -> str:
    return TIMELINE_TO_SEVERITY.get((timeline or "").lower(), "medium")


def _dedupe_strings(items: list[str]) -> list[str]:
    """Case-insensitive order-preserving dedup. Drops empties."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item or not item.strip():
            continue
        key = item.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_target(slug: str, name: str, lat: float, lon: float) -> dict[str, Any]:
    return {
        "id": slug,
        "name": name,
        "lat": float(lat),
        "lon": float(lon),
        "radiusKm": DEFAULT_RADIUS_KM,
        "theater": DEFAULT_THEATER,
    }


def _build_score(assessment: dict[str, Any], cascade: dict[str, Any]) -> dict[str, int]:
    chain_depth = int(cascade.get("chain_depth") or 0)
    return {
        "aggregate": int(assessment.get("exposure_score") or 0),
        "movement": int(assessment.get("strava_score") or 0),
        # Personnel layer doesn't exist as a standalone score; we encode the
        # cascade depth here as a normalized 0-100 proxy so his UI's score
        # strip has something to render in the personnel slot. Spec: depth*4
        # capped at 100. Empty chains (Shack15, San Diego) → 0.
        "personnel": min(100, chain_depth * 4),
        "facility": int(assessment.get("satellite_score") or 0),
        "aerial": int(assessment.get("aircraft_score") or 0),
    }


def _build_findings(
    slug: str,
    cascade: dict[str, Any],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    cascade_score = int(cascade.get("cascade_score") or 0)
    cascade_lat = cascade.get("lat")
    cascade_lon = cascade.get("lon")
    foundry_url = cascade.get("foundry_url") or ""
    chain_depth = int(cascade.get("chain_depth") or 0)

    # One finding per adversary action.
    for action in actions:
        action_id = action.get("action_id") or ""
        finding: dict[str, Any] = {
            "id": action_id or f"ghostline-{slug}-action-{len(findings)}",
            "source": "palantir",
            "severity": _action_severity(action.get("timeline")),
            "title": (
                f"{action.get('action_type', 'unknown')}: "
                f"{action.get('target_entity_name') or 'unspecified target'}"
            ),
            "summary": _truncate(action.get("capability_required"), 300),
            "evidence": foundry_url or action.get("foundry_url", ""),
            "status": "new",
        }
        if cascade_lat is not None and cascade_lon is not None:
            finding["lat"] = float(cascade_lat)
            finding["lon"] = float(cascade_lon)
        findings.append(finding)

    # One cascade summary finding (only if cascade actually resolved).
    if cascade and "error" not in cascade:
        cascade_severity = "critical" if cascade_score >= 85 else "high"
        cascade_finding: dict[str, Any] = {
            "id": cascade.get("cascade_id") or f"ghostline-{slug}-cascade",
            "source": "palantir",
            "severity": cascade_severity,
            "title": f"Cascade: {chain_depth} linked entities",
            "summary": _truncate(cascade.get("intelligence_compromised"), 300),
            "evidence": foundry_url,
            "status": "new",
        }
        if cascade_lat is not None and cascade_lon is not None:
            cascade_finding["lat"] = float(cascade_lat)
            cascade_finding["lon"] = float(cascade_lon)
        findings.append(cascade_finding)

    return findings


def _build_layers(
    target_name: str,
    target_lat: float,
    target_lon: float,
    cascade: dict[str, Any],
    current_state: dict[str, Any],
) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []

    # 1. Target marker (always emitted).
    layers.append({
        "id": "ghostline-target",
        "source": "palantir",
        "label": target_name,
        "type": "marker",
        "visible": True,
        "count": 1,
        "tone": "green",
        "data": [{
            "position": [float(target_lon), float(target_lat)],
            "title": target_name,
            "detail": "OPSEC target",
            "radiusMeters": 1500,
        }],
    })

    # 2. Linked entities (units + platforms + sensors), deterministic ring.
    cascade_lat = cascade.get("lat")
    cascade_lon = cascade.get("lon")
    chain_entities: list[dict[str, str]] = []
    for u in (cascade.get("linked_units") or []):
        chain_entities.append({"kind": "unit", "id": u.get("id", ""), "name": u.get("name", "")})
    for p in (cascade.get("linked_platforms") or []):
        chain_entities.append({"kind": "platform", "id": p.get("id", ""), "name": p.get("name", "")})
    for s in (cascade.get("linked_sensors") or []):
        chain_entities.append({"kind": "sensor", "id": s.get("id", ""), "name": s.get("name", "")})

    if chain_entities and cascade_lat is not None and cascade_lon is not None:
        # Cap markers + deterministic ring so re-runs match.
        sample = chain_entities[:MAX_LINKED_MARKERS]
        markers: list[dict[str, Any]] = []
        for idx, entity in enumerate(sample):
            position = _ring_position(
                float(cascade_lat), float(cascade_lon),
                idx, len(sample), LINKED_RING_RADIUS_KM,
            )
            markers.append({
                "position": position,
                "title": entity["name"] or entity["id"],
                "detail": f"{entity['kind']}: {entity['id']}",
                "radiusMeters": 350,
                "kind": entity["kind"],
                "entityId": entity["id"],
                # Honest flag — these positions are synthesized for visual
                # display, not real coordinates of the linked entities.
                "synthetic_position": True,
            })
        layers.append({
            "id": "ghostline-linked-entities",
            "source": "palantir",
            "label": f"Linked entities ({len(chain_entities)})",
            "type": "marker",
            "visible": True,
            "count": len(chain_entities),
            "tone": "amber",
            "data": markers,
        })

    # 3. Live aircraft from realtime FR24 snapshot, only if non-empty.
    aircraft = (current_state or {}).get("aircraft") or {}
    aircraft_records = aircraft.get("aircraft") or []
    if int(aircraft.get("aircraft_count") or 0) > 0:
        aircraft_data: list[dict[str, Any]] = []
        for ac in aircraft_records:
            lon = ac.get("lon")
            lat = ac.get("lat")
            if lat is None or lon is None:
                continue
            is_mil = bool(ac.get("is_military"))
            title = ac.get("callsign") or ac.get("hex") or ac.get("registration") or "?"
            alt = ac.get("altitude")
            spd = ac.get("speed")
            heading = ac.get("heading")
            atype = ac.get("aircraft_type") or ""
            detail_parts = []
            if atype:
                detail_parts.append(atype)
            if alt is not None:
                detail_parts.append(f"alt={alt}")
            if spd is not None:
                detail_parts.append(f"spd={spd}")
            if heading is not None:
                detail_parts.append(f"hdg={heading}")
            if is_mil:
                detail_parts.append("MIL")
            aircraft_data.append({
                "position": [float(lon), float(lat)],
                "title": title,
                "detail": " / ".join(detail_parts) if detail_parts else atype,
                "radiusMeters": 600 if is_mil else 300,
                "is_military": is_mil,
                "hex": ac.get("hex"),
                "callsign": ac.get("callsign"),
                "aircraft_type": atype,
                "heading": heading,
            })
        layers.append({
            "id": "ghostline-live-aircraft",
            "source": "adsb",  # closest match in his constrained source enum
            "label": f"Live aircraft ({aircraft.get('aircraft_count')})",
            "type": "marker",
            "visible": True,
            "count": int(aircraft.get("aircraft_count") or 0),
            "tone": "red",
            "data": aircraft_data,
        })

    return layers


def _build_aip(assessment: dict[str, Any]) -> dict[str, Any]:
    """Synthetic AipSyncReceipt — the ontology was already written by the
    populator/writeback pipeline, so we report the existing assessment as
    'synced' with its Foundry URL standing in for the object_rid."""
    foundry_url = assessment.get("foundry_url") or ""
    receipt: dict[str, Any] = {
        "state": "synced",
        "objectRid": foundry_url,
        "actionName": "create-opsec-assessment",
    }
    last_synced = assessment.get("assessment_timestamp")
    if last_synced:
        receipt["lastSyncedAt"] = last_synced
    return receipt


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_mission_report(location: str) -> dict[str, Any]:
    """Build a TypeScript-MissionReport-shaped dict for `location`.

    Returns {"error": "..."} when the location can't be resolved (caller
    should map to HTTP 404). On partial Foundry failures (cascade missing,
    actions missing) the report is still produced with degraded fields —
    the assessment is the only hard prerequisite.
    """
    if not location or not location.strip():
        return {"error": "location is required"}

    full = query_api.get_full_picture(location)
    if isinstance(full, dict) and "error" in full:
        return {"error": full["error"]}

    assessment: dict[str, Any] = full.get("assessment") or {}
    cascade: dict[str, Any] = full.get("cascade") or {}
    actions: list[dict[str, Any]] = full.get("adversary_actions") or []
    current_state: dict[str, Any] = full.get("current_state") or {}

    if not assessment or "error" in assessment:
        return {"error": (assessment.get("error") if isinstance(assessment, dict) else None)
                or f"No assessment found for {location!r}"}

    canonical_name = assessment.get("location") or location.strip()
    slug = osint_sources.slugify(canonical_name)
    target_lat = float(assessment.get("lat") or 0.0)
    target_lon = float(assessment.get("lon") or 0.0)

    # Mitigation list: cascade's upstream pick first, then the alternatives
    # parsed out of the threat brief (deduped against the upstream).
    mitigations_payload = query_api.recommend_mitigations(location)
    primary = (cascade.get("recommended_mitigation") or "").strip()
    alternatives: list[str] = []
    if isinstance(mitigations_payload, dict) and "error" not in mitigations_payload:
        # primary_mitigation here usually equals cascade.recommended_mitigation;
        # the dedup pass below handles the overlap.
        if mitigations_payload.get("primary_mitigation"):
            alternatives.append(mitigations_payload["primary_mitigation"])
        alternatives.extend(mitigations_payload.get("alternative_mitigations") or [])
    mitigation_priorities = _dedupe_strings(([primary] if primary else []) + alternatives)

    # Cascade may have come back as an error dict; treat as empty for layer/finding.
    cascade_for_render = cascade if isinstance(cascade, dict) and "error" not in cascade else {}

    return {
        "runId": f"ghostline-{slug}-{int(time.time())}",
        "target": _build_target(slug, canonical_name, target_lat, target_lon),
        "generatedAt": _now_iso(),
        "mode": "live",
        "score": _build_score(assessment, cascade_for_render),
        "findings": _build_findings(slug, cascade_for_render, actions),
        "layers": _build_layers(canonical_name, target_lat, target_lon, cascade_for_render, current_state),
        "narrative": assessment.get("brief") or "",
        "mitigationPriorities": mitigation_priorities,
        "aip": _build_aip(assessment),
    }
