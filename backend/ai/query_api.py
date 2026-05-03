"""GHOSTLINE consumer-facing query API — the surface the voice agent calls.

Seven read-only functions that wrap the populated Foundry ontology plus the
realtime enrichment layer into a clean Python interface. Designed so the
voice agent's LLM can use the docstrings directly as tool descriptions.

Every function:
  - Caches results in-memory for 60s (FOUNDRY_TTL_SECONDS).
  - Resolves location names fuzzily — "Norfolk" finds "Naval Station Norfolk".
  - Returns plain dicts ready for JSON serialization or voice narration.
  - On failure, returns {"error": str} rather than raising.

Run:
    python -m backend.ai.query_api --test
"""

from __future__ import annotations

import argparse
import json
import logging
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import osint_sources
from .palantir_integration import FoundryClient, FoundryError
from .realtime_enrichment import get_full_current_state

log = logging.getLogger("ghostline.query")

CACHE_TTL_SECONDS = 60.0
PROVENANCE_FIELDS = ("sourceUrl", "retrievedAt", "sourceType", "confidence")

# Persistent disk cache. Every successful Foundry query writes its result
# here; on Foundry-unreachable paths we fall back to the disk copy. After
# one successful smoke test the demo can run offline indefinitely.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DISK_CACHE_DIR = REPO_ROOT / "backend" / "ai" / "demo_cache"

# Map ID prefix -> object_type. Lets get_provenance look up by raw entity_id.
ID_PREFIX_TO_TYPE: list[tuple[str, str]] = [
    ("geo_", "GhostlineGeoFeature"),
    ("unit_", "GhostlineUnit"),
    ("plat_", "GhostlinePlatform"),
    ("sens_", "GhostlineSensor"),
    ("comms_", "GhostlineCommsAsset"),
    ("cascade_", "CascadeRisk"),
    ("action_", "AdversaryAction"),
]

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# Spoken-name aliases the substring matcher would otherwise miss. Lowercased keys.
LOCATION_ALIASES: dict[str, str] = {
    "jblm": "Joint Base Lewis-McChord",
    "lewis mcchord": "Joint Base Lewis-McChord",
    "lewis-mcchord": "Joint Base Lewis-McChord",
    "fort bragg": "Fort Liberty",
    "bragg": "Fort Liberty",
    "liberty": "Fort Liberty",
    "norfolk": "Naval Station Norfolk",
    "san diego": "Naval Base San Diego",
}

# Regex to lift "Recommended actions. One: ... Two: ..." style numbered actions
# out of a threat brief paragraph.
_NUMBERED_ACTION_RE = re.compile(
    r"\b(?:One|Two|Three|Four|Five|1|2|3|4|5)[\.:]\s+([^\n]+?)(?=\s+(?:One|Two|Three|Four|Five|1|2|3|4|5)[\.:]|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Cache + Foundry client (thread-safe module-level)
# ---------------------------------------------------------------------------

_cache: dict[tuple, tuple[Any, float]] = {}
_cache_lock = threading.Lock()
_client_lock = threading.Lock()
_client_instance: FoundryClient | None = None


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


def _get_client() -> FoundryClient | None:
    """Lazy-initialize and reuse a FoundryClient. Returns None if config is missing."""
    global _client_instance
    with _client_lock:
        if _client_instance is None:
            try:
                _client_instance = FoundryClient()
            except FoundryError as exc:
                log.error("FoundryClient init failed: %s", exc)
                return None
    return _client_instance


# ---------------------------------------------------------------------------
# Persistent disk cache (write-on-success, read-on-foundry-unreachable)
# ---------------------------------------------------------------------------

def _disk_cache_path(function_name: str, key_args: tuple) -> Path:
    """Stable filename derived from function name + slugified args."""
    if not key_args:
        return DISK_CACHE_DIR / f"{function_name}.json"
    parts = [osint_sources.slugify(str(a)) for a in key_args]
    slug = "_".join(p for p in parts if p) or "_"
    return DISK_CACHE_DIR / f"{function_name}_{slug}.json"


def _disk_write(function_name: str, key_args: tuple, value: Any) -> None:
    """Persist a successful query result to disk. Atomic via .tmp + os.replace."""
    try:
        DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _disk_cache_path(function_name, key_args)
        wrapper = {
            "_cached_at": datetime.now(timezone.utc).isoformat(),
            "_function": function_name,
            "_args": list(key_args),
            "value": value,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(wrapper, indent=2, default=str))
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001 — disk-cache write must never crash the demo
        log.warning("disk cache write failed for %s: %s", function_name, exc)


def _disk_read_dict(function_name: str, key_args: tuple) -> dict | None:
    """Return a disk-cached dict (with disk-source markers) or None if missing/corrupted."""
    try:
        path = _disk_cache_path(function_name, key_args)
        if not path.exists():
            return None
        wrapper = json.loads(path.read_text())
        value = wrapper.get("value")
        if not isinstance(value, dict):
            return None
        return {
            **value,
            "_source": "disk_cache",
            "_cached_at": wrapper.get("_cached_at"),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("disk cache read failed for %s: %s", function_name, exc)
        return None


def _disk_read_list(function_name: str, key_args: tuple) -> list | None:
    """Return a disk-cached list or None. Lists aren't tagged with _source."""
    try:
        path = _disk_cache_path(function_name, key_args)
        if not path.exists():
            return None
        wrapper = json.loads(path.read_text())
        value = wrapper.get("value")
        if not isinstance(value, list):
            return None
        return value
    except Exception as exc:  # noqa: BLE001
        log.warning("disk cache read failed for %s: %s", function_name, exc)
        return None


def _disk_or_error(function_name: str, key_args: tuple, error_dict: dict) -> dict:
    """Disk-fallback shim for dict-returning functions on error paths."""
    disk = _disk_read_dict(function_name, key_args)
    return disk if disk is not None else error_dict


def _disk_or_empty_list(function_name: str, key_args: tuple) -> list:
    """Disk-fallback shim for list-returning functions on error paths."""
    return _disk_read_list(function_name, key_args) or []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _foundry_url(object_type: str, primary_key: str) -> str:
    """Stable REST URL for any Foundry object — useful as a click-through audit link."""
    host = (os.getenv("FOUNDRY_HOSTNAME") or "").strip().strip("<>'\"`")
    rid = (os.getenv("FOUNDRY_ONTOLOGY_RID") or "").strip().strip("<>'\"`")
    return f"https://{host}/api/v2/ontologies/{rid}/objects/{object_type}/{primary_key}"


def _detect_object_type(entity_id: str) -> str | None:
    """Best-guess object_type from an entity_id. Returns None if unmatched."""
    if not entity_id:
        return None
    for prefix, obj_type in ID_PREFIX_TO_TYPE:
        if entity_id.startswith(prefix):
            return obj_type
    if UUID_RE.match(entity_id):
        return "OpsecAssessment"
    return None


def _entity_name_map(client: FoundryClient) -> dict[str, dict[str, str]]:
    """One-shot pull of every chain-eligible entity's name. Cached for 60s."""
    key = ("entity_name_map",)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    out: dict[str, dict[str, str]] = {}
    spec = (
        ("GhostlineGeoFeature", "featureId"),
        ("GhostlineUnit", "unitId"),
        ("GhostlinePlatform", "platformId"),
        ("GhostlineSensor", "sensorId"),
        ("GhostlineCommsAsset", "assetId"),
    )
    for object_type, pk_field in spec:
        try:
            objs = client.list_objects(object_type, page_size=200)
        except FoundryError as exc:
            log.warning("list %s failed: %s", object_type, exc)
            continue
        for o in objs:
            pk = o.get(pk_field)
            if not pk:
                continue
            out[pk] = {"name": o.get("name") or pk, "object_type": object_type}
    _cache_put(key, out)
    return out


def _resolve_location_name(client: FoundryClient, query: str) -> str | None:
    """Map a fuzzy input ('Norfolk') to the canonical locationName ('Naval Station Norfolk').

    Uses every distinct locationName found on OpsecAssessment objects as the
    candidate set — those are the sites we've actually populated.
    """
    if not query:
        return None
    key = ("locations_canonical",)
    canonical = _cache_get(key)
    if canonical is None:
        try:
            assessments = client.list_objects("OpsecAssessment", page_size=200)
        except FoundryError as exc:
            log.error("list OpsecAssessment failed: %s", exc)
            return None
        canonical = sorted({a.get("locationName") for a in assessments if a.get("locationName")})
        _cache_put(key, canonical)
    q = query.lower().strip()
    # 1) Spoken aliases ("JBLM", "Fort Bragg" -> "Fort Liberty") — voice-friendly.
    aliased = LOCATION_ALIASES.get(q)
    if aliased and aliased in canonical:
        return aliased
    # 2) Exact (case-insensitive) wins.
    for name in canonical:
        if name.lower() == q:
            return name
    # 3) Substring — prefer matches that start with the query (more specific).
    starts = [n for n in canonical if n.lower().startswith(q)]
    if starts:
        return min(starts, key=len)
    contains = [n for n in canonical if q in n.lower()]
    if contains:
        return min(contains, key=len)
    return None


def _latest_assessment_for(client: FoundryClient, location_name: str) -> dict | None:
    try:
        objs = client.list_objects("OpsecAssessment", page_size=200)
    except FoundryError as exc:
        log.error("list OpsecAssessment failed: %s", exc)
        return None
    matching = [o for o in objs if o.get("locationName") == location_name]
    if not matching:
        return None
    matching.sort(key=lambda o: o.get("assessmentTimestamp") or "", reverse=True)
    return matching[0]


def _latest_cascade_for(client: FoundryClient, location_name: str) -> dict | None:
    try:
        objs = client.list_objects("CascadeRisk", page_size=200)
    except FoundryError as exc:
        log.error("list CascadeRisk failed: %s", exc)
        return None
    matching = [o for o in objs if o.get("locationName") == location_name]
    if not matching:
        return None
    matching.sort(key=lambda o: o.get("createdTimestamp") or "", reverse=True)
    return matching[0]


def _risk_level(score: int) -> str:
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MEDIUM"
    return "HIGH"


def _extract_alternative_mitigations(threat_brief: str) -> list[str]:
    """Parse the 'Recommended actions. One: ... Two: ...' block out of a brief."""
    if not threat_brief:
        return []
    # Find the recommended-actions block; everything after it.
    m = re.search(r"recommended actions[.: ]+(.+?)(?:\[Note:|\Z)", threat_brief, re.I | re.S)
    body = m.group(1) if m else threat_brief
    actions: list[str] = []
    for am in _NUMBERED_ACTION_RE.finditer(body):
        text = am.group(1).strip().rstrip(".") + "."
        if text and text not in actions:
            actions.append(text)
    return actions[:5]


# ---------------------------------------------------------------------------
# 1. get_assessment
# ---------------------------------------------------------------------------

def get_assessment(location: str) -> dict[str, Any]:
    """Get the OPSEC assessment for a location.

    Returns the most recent OpsecAssessment with composite exposure score,
    the three sub-scores, and the spoken-style threat brief. Use this when
    the commander asks "what's the OPSEC picture at <base>?"

    Args:
        location: Location name. Fuzzy — "Norfolk" matches "Naval Station Norfolk".

    Returns:
        Dict with: location, exposure_score (0-100), risk_level (LOW/MEDIUM/HIGH),
        strava_score, aircraft_score, satellite_score, brief, lat, lon,
        assessment_id, foundry_url. {"error": "..."} if not found.
    """
    key_args = (location.lower(),)
    key = ("get_assessment", *key_args)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return _disk_or_error("get_assessment", key_args, {"error": "Foundry not configured"})
    canonical = _resolve_location_name(client, location)
    if canonical is None:
        return _disk_or_error("get_assessment", key_args, {"error": f"No assessment found for {location!r}"})
    assessment = _latest_assessment_for(client, canonical)
    if assessment is None:
        return _disk_or_error("get_assessment", key_args, {"error": f"No assessment found for {canonical!r}"})

    score = int(assessment.get("exposureScore") or 0)
    aid = assessment.get("assessmentId") or ""
    result = {
        "location": canonical,
        "exposure_score": score,
        "risk_level": _risk_level(score),
        "strava_score": int(assessment.get("stravaDensityScore") or 0),
        "aircraft_score": int(assessment.get("aircraftPredictabilityScore") or 0),
        "satellite_score": int(assessment.get("satelliteVulnerabilityScore") or 0),
        "brief": assessment.get("threatBrief") or "",
        "lat": float(assessment.get("latitude") or 0.0),
        "lon": float(assessment.get("longitude") or 0.0),
        "assessment_id": aid,
        "assessment_timestamp": assessment.get("assessmentTimestamp"),
        "foundry_url": _foundry_url("OpsecAssessment", aid),
    }
    _cache_put(key, result)
    _disk_write("get_assessment", key_args, result)
    return result


# ---------------------------------------------------------------------------
# 2. get_cascade
# ---------------------------------------------------------------------------

def get_cascade(location: str) -> dict[str, Any]:
    """Get the cascade-risk analysis for a location.

    Returns the most recent CascadeRisk with chain entities resolved to
    real names (units, platforms, sensors). Use this when the commander
    asks "what could an adversary infer beyond surface OPSEC at <base>?"

    Args:
        location: Location name. Fuzzy — "JBLM" matches "Joint Base Lewis-McChord".

    Returns:
        Dict with: location, lat, lon, chain_depth, linked_units (list of
        {id, name}), linked_platforms (list of {id, name}), linked_sensors
        (list of {id, name}), intelligence_compromised, adversary_action_likely,
        recommended_mitigation, cascade_score, risk_level, foundry_url.
        {"error": "..."} if not found.
    """
    key_args = (location.lower(),)
    key = ("get_cascade", *key_args)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return _disk_or_error("get_cascade", key_args, {"error": "Foundry not configured"})
    canonical = _resolve_location_name(client, location)
    if canonical is None:
        return _disk_or_error("get_cascade", key_args, {"error": f"No cascade found for {location!r}"})
    cascade = _latest_cascade_for(client, canonical)
    if cascade is None:
        return _disk_or_error("get_cascade", key_args, {"error": f"No cascade found for {canonical!r}"})

    name_map = _entity_name_map(client)
    chain = cascade.get("chainEntities") or []
    linked_units: list[dict[str, str]] = []
    linked_platforms: list[dict[str, str]] = []
    linked_sensors: list[dict[str, str]] = []
    for eid in chain:
        meta = name_map.get(eid)
        if not meta:
            continue
        bucket = {
            "GhostlineUnit": linked_units,
            "GhostlinePlatform": linked_platforms,
            "GhostlineSensor": linked_sensors,
        }.get(meta["object_type"])
        if bucket is not None:
            bucket.append({"id": eid, "name": meta["name"]})

    score = int(cascade.get("compositeCascadeScore") or 0)
    cid = cascade.get("cascadeId") or ""
    result = {
        "location": canonical,
        "lat": float(cascade.get("centerLat") or 0.0),
        "lon": float(cascade.get("centerLon") or 0.0),
        "chain_depth": int(cascade.get("chainDepth") or 0),
        "linked_units": linked_units,
        "linked_platforms": linked_platforms,
        "linked_sensors": linked_sensors,
        "intelligence_compromised": cascade.get("intelligenceCompromised") or "",
        "adversary_action_likely": cascade.get("adversaryActionLikely") or "",
        "recommended_mitigation": cascade.get("recommendedUpstreamMitigation") or "",
        "cascade_score": score,
        "risk_level": _risk_level(score),
        "confidence": cascade.get("confidence") or "",
        "cascade_id": cid,
        "source_assessment_id": cascade.get("sourceAssessmentId") or "",
        "foundry_url": _foundry_url("CascadeRisk", cid),
    }
    _cache_put(key, result)
    _disk_write("get_cascade", key_args, result)
    return result


# ---------------------------------------------------------------------------
# 3. get_adversary_actions
# ---------------------------------------------------------------------------

def get_adversary_actions(location: str) -> list[dict[str, Any]]:
    """Get all predicted adversary actions exploiting a location's cascade.

    Returns 1-3 specific adversary actions with their target entity, action
    type, capability required, timeline, and rationale. Use when the
    commander asks "what would an adversary actually DO?"

    Args:
        location: Location name. Fuzzy match.

    Returns:
        List of dicts, each with: action_id, action_type, target_entity_name,
        target_entity_id, capability_required, timeline, rationale,
        confidence, foundry_url. Empty list if no cascade or no actions.
    """
    key_args = (location.lower(),)
    key = ("get_adversary_actions", *key_args)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return _disk_or_empty_list("get_adversary_actions", key_args)
    canonical = _resolve_location_name(client, location)
    if canonical is None:
        return _disk_or_empty_list("get_adversary_actions", key_args)
    cascade = _latest_cascade_for(client, canonical)
    if cascade is None:
        return _disk_or_empty_list("get_adversary_actions", key_args)
    cid = cascade.get("cascadeId") or ""
    try:
        linked = client.get_linked_objects(
            "CascadeRisk", cid, "cascadeRisk", page_size=20
        )
    except FoundryError as exc:
        log.error("get_linked_objects cascadeRisk for %s: %s", cid, exc)
        return _disk_or_empty_list("get_adversary_actions", key_args)

    out: list[dict[str, Any]] = []
    for a in linked:
        capability_full = a.get("adversaryCapabilityRequired") or ""
        # Split capability + rationale (concatenated by adversary_modeler).
        if "\n\nRationale:" in capability_full:
            capability, rationale = capability_full.split("\n\nRationale:", 1)
            rationale = rationale.strip()
        else:
            capability, rationale = capability_full, ""
        aid = a.get("actionId") or ""
        out.append({
            "action_id": aid,
            "action_type": a.get("actionType") or "",
            "target_entity_name": a.get("targetEntityName") or "",
            "target_entity_id": a.get("targetEntityId") or "",
            "capability_required": capability.strip(),
            "timeline": a.get("timelineEstimate") or "",
            "rationale": rationale,
            "confidence": a.get("confidence") or "",
            "foundry_url": _foundry_url("AdversaryAction", aid),
        })
    # Stable order: action_id ascending (preserves the LLM's original priority).
    out.sort(key=lambda x: x["action_id"])
    _cache_put(key, out)
    _disk_write("get_adversary_actions", key_args, out)
    return out


# ---------------------------------------------------------------------------
# 4. compare_locations
# ---------------------------------------------------------------------------

def compare_locations() -> list[dict[str, Any]]:
    """Rank every location by cascade score, highest risk first.

    Use when the commander asks "which base is most exposed?" or wants a
    leaderboard view across the populated tenant.

    Returns:
        List of dicts, each with: location, lat, lon, cascade_score,
        risk_level, chain_depth, primary_concern (truncated 80 chars),
        cascade_id, foundry_url. Sorted high-to-low cascade_score.
        Deduped to the latest cascade per location (handles --regenerate
        producing v1+v2 in the same tenant).
    """
    key = ("compare_locations",)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return _disk_read_list("compare_locations", ()) or []
    try:
        cascades = client.list_objects("CascadeRisk", page_size=200)
    except FoundryError as exc:
        log.error("list CascadeRisk failed: %s", exc)
        return _disk_read_list("compare_locations", ()) or []

    # Dedupe to latest cascade per location (createdTimestamp wins) so
    # cascade_analyst --regenerate doesn't produce a doubled leaderboard.
    by_loc: dict[str, dict] = {}
    for c in cascades:
        loc = c.get("locationName") or ""
        existing = by_loc.get(loc)
        if existing is None or (c.get("createdTimestamp") or "") > (existing.get("createdTimestamp") or ""):
            by_loc[loc] = c
    cascades = list(by_loc.values())

    out: list[dict[str, Any]] = []
    for c in cascades:
        score = int(c.get("compositeCascadeScore") or 0)
        concern = (c.get("intelligenceCompromised") or "").strip()
        primary = concern[:80] + ("…" if len(concern) > 80 else "")
        cid = c.get("cascadeId") or ""
        out.append({
            "location": c.get("locationName") or "",
            "lat": float(c.get("centerLat") or 0.0),
            "lon": float(c.get("centerLon") or 0.0),
            "cascade_score": score,
            "risk_level": _risk_level(score),
            "chain_depth": int(c.get("chainDepth") or 0),
            "primary_concern": primary,
            "cascade_id": cid,
            "foundry_url": _foundry_url("CascadeRisk", cid),
        })
    out.sort(key=lambda r: -r["cascade_score"])
    _cache_put(key, out)
    _disk_write("compare_locations", (), out)
    return out


# ---------------------------------------------------------------------------
# 5. recommend_mitigations
# ---------------------------------------------------------------------------

def recommend_mitigations(location: str) -> dict[str, Any]:
    """Get the upstream mitigation plus alternative recommended actions.

    `primary_mitigation` is the single best upstream action from the
    CascadeRisk (defeats multiple downstream exposures at once).
    `alternative_mitigations` are parsed out of the OpsecAssessment's
    threat brief — the surface-layer recommendations.

    Args:
        location: Location name. Fuzzy match.

    Returns:
        Dict with: location, primary_mitigation, alternative_mitigations
        (list[str]), foundry_urls (cascade + assessment for click-through).
        {"error": "..."} if no data.
    """
    key_args = (location.lower(),)
    key = ("recommend_mitigations", *key_args)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return _disk_or_error("recommend_mitigations", key_args, {"error": "Foundry not configured"})
    canonical = _resolve_location_name(client, location)
    if canonical is None:
        return _disk_or_error("recommend_mitigations", key_args, {"error": f"No data for {location!r}"})

    cascade = _latest_cascade_for(client, canonical)
    assessment = _latest_assessment_for(client, canonical)
    if cascade is None and assessment is None:
        return _disk_or_error("recommend_mitigations", key_args, {"error": f"No mitigations available for {canonical!r}"})

    primary = cascade.get("recommendedUpstreamMitigation") if cascade else ""
    alternatives = _extract_alternative_mitigations(
        (assessment or {}).get("threatBrief") or ""
    )
    cid = (cascade or {}).get("cascadeId") or ""
    aid = (assessment or {}).get("assessmentId") or ""
    result = {
        "location": canonical,
        "primary_mitigation": primary or "",
        "alternative_mitigations": alternatives,
        "foundry_urls": {
            "cascade": _foundry_url("CascadeRisk", cid) if cid else None,
            "assessment": _foundry_url("OpsecAssessment", aid) if aid else None,
        },
    }
    _cache_put(key, result)
    _disk_write("recommend_mitigations", key_args, result)
    return result


# ---------------------------------------------------------------------------
# 6. get_provenance
# ---------------------------------------------------------------------------

def get_provenance(entity_id: str) -> dict[str, Any]:
    """Show who-said-what for any ontology entity.

    Returns the four provenance fields (source_url, retrieved_at,
    source_type, confidence) for the given object. Use when the commander
    asks "where did that come from?" — every fact in the ontology is
    auditable back to a real public source.

    Args:
        entity_id: Any primary key — geo_*, unit_*, plat_*, sens_*,
            comms_*, cascade_*, action_*, or a UUID (OpsecAssessment).

    Returns:
        Dict with: entity_id, object_type, name, source_url, retrieved_at,
        source_type, confidence, foundry_url. {"error": "..."} if the
        entity isn't found, or a note if the type doesn't carry provenance
        (OpsecAssessment is the documented exception).
    """
    key_args = (entity_id,)
    key = ("get_provenance", *key_args)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        return _disk_or_error("get_provenance", key_args, {"error": "Foundry not configured"})

    object_type = _detect_object_type(entity_id)
    if object_type is None:
        # Hard input-shape error — don't mask with disk cache; the caller
        # passed an unrecognizable ID and needs to see that.
        return {"error": f"Could not infer object type from {entity_id!r}"}

    try:
        obj = client.get_object(object_type, entity_id)
    except FoundryError as exc:
        return _disk_or_error("get_provenance", key_args, {"error": f"lookup failed: {exc}"})
    if obj is None:
        return _disk_or_error("get_provenance", key_args, {"error": f"No {object_type} with id {entity_id!r}"})

    if object_type == "OpsecAssessment":
        # Documented exception per CLAUDE.md — no provenance properties.
        result = {
            "entity_id": entity_id,
            "object_type": object_type,
            "name": obj.get("locationName") or "",
            "note": (
                "OpsecAssessment is a synthesized summary; provenance lives on "
                "the upstream Ghostline* entities and CascadeRisk objects."
            ),
            "foundry_url": _foundry_url(object_type, entity_id),
        }
    else:
        result = {
            "entity_id": entity_id,
            "object_type": object_type,
            "name": obj.get("name") or obj.get("locationName") or "",
            "source_url": obj.get("sourceUrl") or "",
            "retrieved_at": obj.get("retrievedAt") or "",
            "source_type": obj.get("sourceType") or "",
            "confidence": obj.get("confidence") or "",
            "foundry_url": _foundry_url(object_type, entity_id),
        }
    _cache_put(key, result)
    _disk_write("get_provenance", key_args, result)
    return result


# ---------------------------------------------------------------------------
# 7. get_full_picture
# ---------------------------------------------------------------------------

def get_full_picture(location: str) -> dict[str, Any]:
    """Master query — returns assessment + cascade + adversary actions + live state.

    The single call that demonstrates the full GHOSTLINE pipeline: pre-
    computed ontology + realtime enrichment, all anchored to one location.
    Use this for the highest-level voice-agent answers.

    Args:
        location: Location name. Fuzzy match.

    Returns:
        Dict with: assessment, cascade, adversary_actions, current_state
        (live aircraft + satellite passes + news), provenance_summary
        (total_entities, high_confidence_count, sources). {"error": "..."}
        if location resolution fails.
    """
    key_args = (location.lower(),)
    key = ("get_full_picture", *key_args)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    assessment = get_assessment(location)
    # If even the assessment lookup fell back to disk, surface that data instead
    # of erroring — but if there's a real error and no disk fallback, error out.
    if "error" in assessment:
        return _disk_or_error("get_full_picture", key_args, {"error": assessment["error"]})

    cascade = get_cascade(location)
    actions = get_adversary_actions(location)

    lat = cascade.get("lat") if isinstance(cascade, dict) and "error" not in cascade else assessment["lat"]
    lon = cascade.get("lon") if isinstance(cascade, dict) and "error" not in cascade else assessment["lon"]
    location_name = assessment["location"]
    current = get_full_current_state(lat, lon, location_name)

    # Provenance summary across all chain entities + the cascade itself.
    client = _get_client()
    summary = {"total_entities": 0, "high_confidence_count": 0, "sources": []}
    if client is not None and isinstance(cascade, dict) and "error" not in cascade:
        sources: set[str] = set()
        total = 0
        high = 0
        name_map = _entity_name_map(client)
        all_ids: list[str] = []
        all_ids.extend(u["id"] for u in cascade.get("linked_units", []))
        all_ids.extend(p["id"] for p in cascade.get("linked_platforms", []))
        all_ids.extend(s["id"] for s in cascade.get("linked_sensors", []))
        for eid in all_ids:
            meta = name_map.get(eid)
            if not meta:
                continue
            obj_type = meta["object_type"]
            try:
                obj = client.get_object(obj_type, eid)
            except FoundryError:
                continue
            if obj is None:
                continue
            total += 1
            conf = (obj.get("confidence") or "").lower()
            if conf == "high":
                high += 1
            src = obj.get("sourceType")
            if src:
                sources.add(src)
        summary = {
            "total_entities": total,
            "high_confidence_count": high,
            "sources": sorted(sources),
        }

    result = {
        "assessment": assessment,
        "cascade": cascade,
        "adversary_actions": actions,
        "current_state": current,
        "provenance_summary": summary,
    }
    _cache_put(key, result)
    _disk_write("get_full_picture", key_args, result)
    return result


# ---------------------------------------------------------------------------
# CLI test mode
# ---------------------------------------------------------------------------

def _print_short(label: str, obj: Any) -> None:
    print(f"\n--- {label} ---")
    if isinstance(obj, list):
        if not obj:
            print("  (empty list)")
        for i, item in enumerate(obj):
            print(f"  [{i}] {json.dumps(_truncate(item), indent=2)[:1000]}")
    elif isinstance(obj, dict):
        print(json.dumps(_truncate(obj), indent=2)[:2000])
    else:
        print(repr(obj)[:500])


def _truncate(obj: Any) -> Any:
    """Recursively truncate long strings for readable test output."""
    if isinstance(obj, str):
        return obj if len(obj) <= 240 else obj[:237] + "…"
    if isinstance(obj, list):
        return [_truncate(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _truncate(v) for k, v in obj.items()}
    return obj


def _run_test(location: str) -> int:
    print(f"=== query_api smoke test against {location!r} ===")
    _print_short("get_assessment", get_assessment(location))
    _print_short("get_cascade", get_cascade(location))
    _print_short("get_adversary_actions", get_adversary_actions(location))
    _print_short("compare_locations", compare_locations())
    _print_short("recommend_mitigations", recommend_mitigations(location))

    cascade = get_cascade(location)
    sample_id = (cascade.get("linked_units") or [{}])[0].get("id") if isinstance(cascade, dict) else None
    if sample_id:
        _print_short(f"get_provenance({sample_id})", get_provenance(sample_id))
    else:
        # Fall back to any GeoFeature on the cascade.
        gf_id = None
        if isinstance(cascade, dict):
            # chain_entities was resolved by _entity_name_map; we can still derive geo id.
            client = _get_client()
            if client is not None:
                canonical = _resolve_location_name(client, location)
                if canonical is not None:
                    cas = _latest_cascade_for(client, canonical)
                    if cas:
                        chain = cas.get("chainEntities") or []
                        gf_id = next((e for e in chain if e.startswith("geo_")), None)
        if gf_id:
            _print_short(f"get_provenance({gf_id})", get_provenance(gf_id))

    _print_short("get_full_picture (top-level keys + provenance summary)", {
        k: v for k, v in get_full_picture(location).items()
        if k in ("provenance_summary",)
    })

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Voice-agent-facing query API for the GHOSTLINE Foundry ontology."
    )
    p.add_argument("--test", nargs="?", const="Fort Liberty",
                   help="Run smoke test for the given location (default: Fort Liberty).")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.test is None:
        p.print_help()
        return 0

    return _run_test(args.test)


if __name__ == "__main__":
    sys.exit(main())
