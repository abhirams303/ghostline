"""GHOSTLINE OSINT populator — writes the Foundry ontology from public sources.

Per-location flow (CLAUDE.md §Architecture):
  1. Nominatim geocode                   -> GhostlineGeoFeature (lat/lon)
  2. Wikipedia REST summary              -> augment GeoFeature description
  3. Overpass perimeter (best-effort)    -> augment GeoFeature
  4. Wikidata SPARQL stationed-units     -> GhostlineUnit (high confidence)
  5. Wikipedia Tenant-units section      -> GhostlineUnit (high confidence)
  6. Exa.ai gap-fill                     -> GhostlineUnit (medium confidence)
  7. Per-unit Wikipedia summary          -> GhostlinePlatform (best-effort)
  8. (Sensors / extra comms — V2)

Every entity carries source_url / retrieved_at / source_type / confidence.
Entity primary keys are deterministic slugs so re-runs are idempotent: if an
object already exists, we skip creation but still try to fill in any later-tier
links that depend on it.

Run:
    python -m backend.ai.osint_populator --dry-run --location shack15
    python -m backend.ai.osint_populator --dry-run                # all 5
    python -m backend.ai.osint_populator --location shack15        # live
    python -m backend.ai.osint_populator --verify                  # read-back counts
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.ai import osint_sources
from backend.ai.palantir_integration import (
    ACTIONS,
    LINKS_REVERSE,
    FoundryClient,
    FoundryError,
)

log = logging.getLogger("ghostline.populator")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_ROOT = REPO_ROOT / "backend" / "ai" / "cached_osint"

# ---------------------------------------------------------------------------
# Locked target locations (CLAUDE.md §"Target Locations").
# ---------------------------------------------------------------------------
LOCATIONS: list[dict[str, Any]] = [
    {
        "slug": "fort_liberty",
        "name": "Fort Liberty",
        "nominatim_query": "Fort Liberty, NC",
        "wikipedia_titles": ["Fort_Liberty", "Fort_Bragg"],
        "lat": 35.139, "lon": -78.997,
        "country": "USA",
        "feature_type": "military_base",
        "civilian": False,
    },
    {
        "slug": "naval_station_norfolk",
        "name": "Naval Station Norfolk",
        "nominatim_query": "Naval Station Norfolk, VA",
        "wikipedia_titles": ["Naval_Station_Norfolk"],
        "lat": 36.9466, "lon": -76.3013,
        "country": "USA",
        "feature_type": "naval_base",
        "civilian": False,
    },
    {
        "slug": "joint_base_lewis_mcchord",
        "name": "Joint Base Lewis-McChord",
        "nominatim_query": "Joint Base Lewis-McChord, WA",
        "wikipedia_titles": ["Joint_Base_Lewis–McChord", "Joint_Base_Lewis-McChord"],
        "lat": 47.0876, "lon": -122.5726,
        "country": "USA",
        "feature_type": "joint_base",
        "civilian": False,
    },
    {
        "slug": "naval_base_san_diego",
        "name": "Naval Base San Diego",
        "nominatim_query": "Naval Base San Diego, CA",
        "wikipedia_titles": ["Naval_Base_San_Diego"],
        "lat": 32.6839, "lon": -117.1286,
        "country": "USA",
        "feature_type": "naval_base",
        "civilian": False,
    },
    {
        "slug": "shack15",
        "name": "Shack15",
        "nominatim_query": "Shack15, San Francisco, CA",
        "wikipedia_titles": [],
        "lat": 37.7955, "lon": -122.3937,
        "country": "USA",
        "feature_type": "civilian_venue",
        "civilian": True,
    },
]

# ---------------------------------------------------------------------------
# Wikitext extraction helpers
# ---------------------------------------------------------------------------

# Wikipedia section headers that typically list stationed/tenant military units.
UNIT_SECTION_KEYWORDS = (
    "tenant units", "major units", "current units", "units assigned",
    "units stationed", "garrison units", "based units", "resident units",
    "tenant commands", "major tenants",
    # Naval bases use different conventions:
    "operational units", "carrier strike groups", "destroyer squadrons",
    "tenant/shore", "shore commands", "air squadrons",
    # Air bases:
    "based aircraft", "host wing", "tenant wings",
)

# Wikilinks we should never treat as units.
NON_UNIT_LINK_PREFIXES = ("file:", "image:", "category:", "wikipedia:", "help:", "portal:")

# Generic concepts that show up as wikilinks in unit sections but are not units.
NON_UNIT_NAMES = {
    "shoulder_sleeve_insignia", "shoulder sleeve insignia",
    "airborne forces", "special operations", "military intelligence",
    "psychological operations", "civil affairs",
    "us army", "u.s. army", "united states army", "united states navy",
    "united states marine corps", "united states air force",
    "joint base", "military base",
}

# Heuristic: a real unit name usually contains one of these words.
UNIT_KEYWORDS = (
    "division", "brigade", "regiment", "battalion", "squadron",
    "wing", "group", "command", "corps", "fleet", "force",
    "company", "marine", "navy", "army", "airfield",
    "special forces", "psychological", "civil affairs",
    "signal", "engineer", "infantry", "artillery", "cavalry", "aviation",
    "task force", "expeditionary", "amphibious",
)

# Common military platform designators we can spot in Wikipedia text.
# Conservative: only match well-known prefixed designators.
PLATFORM_DESIGNATOR_RE = re.compile(
    r"\b(?:F-?\d{2,3}[A-Z]?|F/A-?\d{2,3}[A-Z]?|"
    r"C-?\d{1,3}[A-Z]?|"
    r"AH-?\d{1,3}[A-Z]?|UH-?\d{1,3}[A-Z]?|MH-?\d{1,3}[A-Z]?|CH-?\d{1,3}[A-Z]?|HH-?\d{1,3}[A-Z]?|"
    r"E-?\d{1,3}[A-Z]?|P-?\d{1,3}[A-Z]?|"
    r"MQ-?\d{1,2}[A-Z]?|RQ-?\d{1,2}[A-Z]?|"
    r"M1A?\d?|M2A?\d?\s*Bradley|Stryker|HMMWV|JLTV|MRAP|"
    r"DDG-?\d{2,3}|CVN-?\d{2,3}|SSN-?\d{2,3}|LHA-?\d{1,2}|LHD-?\d{1,2}|LPD-?\d{1,2})\b"
)


def _section_text(wikitext: str, header_keyword: str) -> str | None:
    """Return the text of the first section whose header matches keyword (case-insensitive)."""
    pattern = re.compile(
        r"^=+\s*([^=\n]+?)\s*=+\s*$(.+?)(?=^=+\s*[^=\n]+\s*=+\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(wikitext):
        title = m.group(1).strip().lower()
        if header_keyword in title:
            return m.group(2)
    return None


def extract_units_from_wikitext(wikitext: str) -> list[str]:
    """Return a deduped list of plausible unit names found in tenant-units sections.

    Walks every matching section (not just the first) — naval base articles often
    spread units across multiple section headers (Operational units, Tenant/Shore
    Commands, Air Squadrons, etc.).
    """
    candidates: list[str] = []
    seen: set[str] = set()
    for keyword in UNIT_SECTION_KEYWORDS:
        for section in _all_section_texts(wikitext, keyword):
            for raw in re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]*)?\]\]", section):
                name = raw.strip().split("#")[0].strip()
                if not name:
                    continue
                lower = name.lower()
                if any(lower.startswith(p) for p in NON_UNIT_LINK_PREFIXES):
                    continue
                if lower in NON_UNIT_NAMES:
                    continue
                if not any(kw in lower for kw in UNIT_KEYWORDS):
                    continue
                key = lower.replace("_", " ")
                if key in seen:
                    continue
                seen.add(key)
                display = name.replace("_", " ").strip()
                candidates.append(display)
    return candidates


def _all_section_texts(wikitext: str, header_keyword: str) -> list[str]:
    pattern = re.compile(
        r"^=+\s*([^=\n]+?)\s*=+\s*$(.+?)(?=^=+\s*[^=\n]+\s*=+\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    out = []
    for m in pattern.finditer(wikitext):
        if header_keyword in m.group(1).strip().lower():
            out.append(m.group(2))
    return out


def extract_platforms_from_text(text: str) -> list[str]:
    """Return distinct platform designators mentioned in a chunk of text."""
    found: list[str] = []
    seen: set[str] = set()
    for m in PLATFORM_DESIGNATOR_RE.finditer(text):
        token = m.group(0)
        # Normalise: drop any embedded whitespace, strip surrounding punctuation
        norm = re.sub(r"\s+", " ", token).strip()
        key = norm.upper()
        if key in seen:
            continue
        seen.add(key)
        found.append(norm)
    return found


# ---------------------------------------------------------------------------
# ID generation (deterministic so re-runs are idempotent)
# ---------------------------------------------------------------------------

def _id_safe(s: str) -> str:
    """Slug suitable for embedding in a primary key."""
    return osint_sources.slugify(s).replace("-", "_")


def feature_id(loc_slug: str) -> str:
    return f"geo_{loc_slug}"


def unit_id(unit_name: str) -> str:
    return f"unit_{_id_safe(unit_name)}"


def platform_id(platform_name: str, unit_name: str) -> str:
    return f"plat_{_id_safe(platform_name)}__{_id_safe(unit_name)[:32]}"


# ---------------------------------------------------------------------------
# Provenance + action parameter helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def provenance(source_url: str, source_type: str, confidence: str) -> dict[str, str]:
    """The four non-negotiable provenance fields as kebab-case action parameters."""
    return {
        "source-url": source_url,
        "retrieved-at": _now_iso(),
        "source-type": source_type,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Data classes for in-memory drafts (before write or print)
# ---------------------------------------------------------------------------

@dataclass
class EntityDraft:
    object_type: str          # e.g., "GhostlineUnit"
    primary_key: str          # the action's primary-key value
    params: dict[str, Any]    # the FULL kebab-case action.parameters dict (incl. provenance)
    parent_pk: str | None = None  # for logging / cascade
    summary: str = ""         # one-line summary for dry-run output


# ---------------------------------------------------------------------------
# Per-location pipeline
# ---------------------------------------------------------------------------

def _pick_wikipedia_title(location: dict[str, Any], cache_dir: Path) -> tuple[str | None, dict | None]:
    """Try each candidate Wikipedia title; return (title, summary_dict) for the first hit."""
    for title in location.get("wikipedia_titles", []):
        summary = osint_sources.wikipedia_summary(title, cache_dir)
        if summary:
            return title, summary
    return None, None


def _pick_wikipedia_parse(
    location: dict[str, Any], cache_dir: Path
) -> tuple[str | None, dict | None]:
    """Try each candidate title for full wikitext, skipping redirect stubs."""
    for title in location.get("wikipedia_titles", []):
        parse = osint_sources.wikipedia_parse(title, cache_dir)
        if not parse:
            continue
        wt = parse["wikitext"] or ""
        # Detect redirect: short wikitext starting with #REDIRECT (case-insensitive).
        if len(wt) < 1000 and re.match(r"^\s*#redirect", wt, re.IGNORECASE):
            log.info("wikipedia parse for %s is a redirect; trying next candidate", title)
            continue
        return title, parse
    return None, None


def _build_geo_feature(
    location: dict[str, Any],
    nominatim: dict | None,
    wiki_summary: dict | None,
) -> EntityDraft:
    """Build the GhostlineGeoFeature draft using the strongest available source."""
    fid = feature_id(location["slug"])

    # Source priority: Wikipedia (richest) > Nominatim > hard-coded fallback.
    if wiki_summary:
        source_url = wiki_summary["content_url"]
        source_type = "wikipedia"
        confidence = "high"
        description = wiki_summary["extract"]
    elif nominatim:
        source_url = nominatim["source_url"]
        source_type = "nominatim"
        confidence = "high"
        description = nominatim["display_name"]
    else:
        source_url = f"https://www.openstreetmap.org/?mlat={location['lat']}&mlon={location['lon']}"
        source_type = "osm"
        confidence = "low"
        description = location["name"]

    lat = nominatim["lat"] if nominatim else location["lat"]
    lon = nominatim["lon"] if nominatim else location["lon"]

    params: dict[str, Any] = {
        "feature-id": fid,
        "name": location["name"],
        "feature-type": location["feature_type"],
        "country": location["country"],
        "latitude": float(lat),
        "longitude": float(lon),
        "description": description[:1000] if description else location["name"],
        **provenance(source_url, source_type, confidence),
    }
    return EntityDraft(
        object_type="GhostlineGeoFeature",
        primary_key=fid,
        params=params,
        summary=f"GhostlineGeoFeature[{fid}] {location['name']} ({lat:.4f},{lon:.4f}) src={source_type}",
    )


def _build_unit(
    name: str,
    feature_pk: str,
    source_url: str,
    source_type: str,
    confidence: str,
    parent_command: str | None = None,
    unit_type: str | None = None,
) -> EntityDraft:
    uid = unit_id(name)
    params: dict[str, Any] = {
        "unit-id": uid,
        "name": name,
        "unit-type": unit_type or _guess_unit_type(name),
        "home-location-id": feature_pk,
        **provenance(source_url, source_type, confidence),
    }
    if parent_command:
        params["parent-command"] = parent_command
    return EntityDraft(
        object_type="GhostlineUnit",
        primary_key=uid,
        params=params,
        parent_pk=feature_pk,
        summary=f"GhostlineUnit[{uid}] {name} -> {feature_pk} src={source_type}/{confidence}",
    )


def _guess_unit_type(name: str) -> str:
    lower = name.lower()
    for keyword in (
        "division", "brigade", "regiment", "battalion", "squadron", "wing",
        "group", "command", "corps", "fleet", "company", "task force",
    ):
        if keyword in lower:
            return keyword
    return "unit"


def _build_platform(
    name: str,
    unit_pk: str,
    source_url: str,
    source_type: str,
    confidence: str,
    feature_pk: str | None = None,
    platform_type: str | None = None,
) -> EntityDraft:
    pid = platform_id(name, unit_pk)
    params: dict[str, Any] = {
        "platform-id": pid,
        "name": name,
        "platform-type": platform_type or _guess_platform_type(name),
        "operating-unit-id": unit_pk,
        **provenance(source_url, source_type, confidence),
    }
    if feature_pk:
        params["base-location-id"] = feature_pk
    return EntityDraft(
        object_type="GhostlinePlatform",
        primary_key=pid,
        params=params,
        parent_pk=unit_pk,
        summary=f"GhostlinePlatform[{pid}] {name} -> {unit_pk} src={source_type}",
    )


def _guess_platform_type(name: str) -> str:
    n = name.upper()
    if n.startswith(("F-", "F/A-")):
        return "fighter_aircraft"
    if n.startswith(("C-", "MC-")):
        return "transport_aircraft"
    if n.startswith(("AH-", "UH-", "MH-", "CH-", "HH-")):
        return "helicopter"
    if n.startswith(("MQ-", "RQ-")):
        return "uav"
    if n.startswith(("E-",)):
        return "command_aircraft"
    if n.startswith(("P-",)):
        return "patrol_aircraft"
    if n.startswith(("DDG-",)):
        return "destroyer"
    if n.startswith(("CVN-",)):
        return "aircraft_carrier"
    if n.startswith(("SSN-",)):
        return "submarine"
    if n.startswith(("LHA-", "LHD-", "LPD-")):
        return "amphibious_ship"
    if "BRADLEY" in n:
        return "infantry_fighting_vehicle"
    if n in {"STRYKER", "HMMWV", "JLTV", "MRAP"} or n.startswith(("M1", "M2")):
        return "ground_vehicle"
    return "platform"


# ---------------------------------------------------------------------------
# Foundry write helpers
# ---------------------------------------------------------------------------

class WriteResult:
    """Outcome of attempting to create one entity."""
    CREATED = "created"
    SKIPPED_EXISTS = "exists"
    FAILED = "failed"
    DRY_RUN = "dry-run"


def _exists(client: FoundryClient, draft: EntityDraft) -> bool:
    try:
        obj = client.get_object(draft.object_type, draft.primary_key)
        return obj is not None
    except FoundryError as exc:
        log.warning("get_object %s/%s failed: %s", draft.object_type, draft.primary_key, exc)
        return False


def write_draft(
    client: FoundryClient | None,
    draft: EntityDraft,
    *,
    dry_run: bool,
) -> str:
    """Write one draft. Returns a WriteResult string. In dry-run, just prints."""
    if dry_run:
        print(f"  [DRY] {draft.summary}")
        for k, v in sorted(draft.params.items()):
            shown = v if len(str(v)) <= 100 else str(v)[:97] + "..."
            print(f"        {k}: {shown}")
        return WriteResult.DRY_RUN

    assert client is not None
    if _exists(client, draft):
        log.info("skip %s[%s] — already in Foundry", draft.object_type, draft.primary_key)
        return WriteResult.SKIPPED_EXISTS

    action = ACTIONS[draft.object_type]
    try:
        client.apply_action(action, draft.params)
    except FoundryError as exc:
        log.error("create %s[%s] failed: %s", draft.object_type, draft.primary_key, exc)
        return WriteResult.FAILED

    # Read-back verify (loud failure if action returned 2xx but object missing)
    fetched = None
    try:
        fetched = client.get_object(draft.object_type, draft.primary_key)
    except FoundryError as exc:
        log.error("read-back %s[%s] failed: %s", draft.object_type, draft.primary_key, exc)
    if fetched is None:
        log.error(
            "WROTE BUT VANISHED: %s[%s] action returned 2xx but read-back is None",
            draft.object_type, draft.primary_key,
        )
        return WriteResult.FAILED

    log.info("created %s[%s]", draft.object_type, draft.primary_key)
    return WriteResult.CREATED


# ---------------------------------------------------------------------------
# Per-location populate
# ---------------------------------------------------------------------------

def populate_location(
    location: dict[str, Any],
    client: FoundryClient | None,
    *,
    dry_run: bool,
    cache_root: Path = CACHE_ROOT,
) -> dict[str, int]:
    cache_dir = cache_root / location["slug"]
    cache_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {
        "GhostlineGeoFeature": 0,
        "GhostlineUnit": 0,
        "GhostlinePlatform": 0,
        "skipped": 0,
        "failed": 0,
    }

    print(f"\n=== {location['name']} ({location['slug']}) ===")

    # 1. Geocode
    nominatim = osint_sources.geocode_nominatim(location["nominatim_query"], cache_dir)
    if nominatim:
        print(f"  nominatim: lat={nominatim['lat']:.4f} lon={nominatim['lon']:.4f}")
    else:
        print("  nominatim: NO RESULT (falling back to hard-coded coords)")

    # 2. Wikipedia summary (skipped for civilian sites with no wikipedia_titles)
    wiki_title, wiki_summary = _pick_wikipedia_title(location, cache_dir)
    if wiki_summary:
        print(f"  wikipedia: {wiki_title} ({len(wiki_summary['extract'])} chars)")
    elif location.get("wikipedia_titles"):
        print(f"  wikipedia: NO MATCH for {location['wikipedia_titles']}")

    # 3. Build & write GhostlineGeoFeature
    geo_draft = _build_geo_feature(location, nominatim, wiki_summary)
    feature_pk = geo_draft.primary_key
    result = write_draft(client, geo_draft, dry_run=dry_run)
    _bump(counts, geo_draft.object_type, result)

    # Civilian site: stop after the GeoFeature.
    if location.get("civilian"):
        print(f"  (civilian venue — skipping unit/platform population)")
        return counts

    # 4 + 5. Wikipedia "Tenant units" parsing for units. Wikidata is best-effort.
    unit_drafts: list[EntityDraft] = []

    wiki_parse_title, wiki_parse = _pick_wikipedia_parse(location, cache_dir)
    if wiki_parse and wiki_parse_title != wiki_title:
        print(f"  wikipedia (parse): using {wiki_parse_title} (summary used {wiki_title})")
    if wiki_parse:
        names = extract_units_from_wikitext(wiki_parse["wikitext"])
        if names:
            print(f"  wiki tenant units: {len(names)} candidates")
        for name in names:
            unit_drafts.append(_build_unit(
                name=name,
                feature_pk=feature_pk,
                source_url=wiki_parse["page_url"],
                source_type="wikipedia",
                confidence="high",
            ))

    # 6. Exa gap-fill if we found very few units. Be conservative: only accept
    # results whose text mentions THIS base by name (avoids picking up units
    # from neighbouring bases that happen to be in adjacent search results).
    if len(unit_drafts) < 3:
        print(f"  exa gap-fill: only {len(unit_drafts)} units so far, querying Exa")
        exa_results = osint_sources.exa_search(
            f"What military units are stationed at {location['name']}?",
            cache_dir,
            num_results=5,
        )
        location_tokens = _location_match_tokens(location)
        for r in exa_results:
            text_blob = (r.get("title") or "") + " " + (r.get("text") or "")
            text_lower = text_blob.lower()
            if not any(tok in text_lower for tok in location_tokens):
                log.info("exa: dropping result %s — no location-name match", r.get("url"))
                continue
            for name in _exa_candidate_unit_names(text_blob):
                if any(d.params["name"].lower() == name.lower() for d in unit_drafts):
                    continue
                unit_drafts.append(_build_unit(
                    name=name,
                    feature_pk=feature_pk,
                    source_url=r["url"],
                    source_type="exa_search",
                    confidence="medium",
                ))

    # Cap unit creation at 12 per location to keep the demo focused.
    if len(unit_drafts) > 12:
        log.info("trimming unit count from %d to 12 for %s", len(unit_drafts), location["slug"])
        unit_drafts = unit_drafts[:12]

    # Write units
    for ud in unit_drafts:
        result = write_draft(client, ud, dry_run=dry_run)
        _bump(counts, ud.object_type, result)

    # 7. Per-unit Wikipedia summary -> platform extraction (best-effort)
    for ud in unit_drafts:
        unit_name = ud.params["name"]
        unit_title = unit_name.replace(" ", "_")
        unit_summary = osint_sources.wikipedia_summary(unit_title, cache_dir)
        if not unit_summary:
            continue
        text = unit_summary["extract"] or ""
        platforms = extract_platforms_from_text(text)
        if not platforms:
            continue
        # cap per-unit platforms
        for plat_name in platforms[:3]:
            pdraft = _build_platform(
                name=plat_name,
                unit_pk=ud.primary_key,
                source_url=unit_summary["content_url"],
                source_type="wikipedia",
                confidence="medium",
                feature_pk=feature_pk,
            )
            result = write_draft(client, pdraft, dry_run=dry_run)
            _bump(counts, pdraft.object_type, result)

    return counts


def _bump(counts: dict[str, int], object_type: str, result: str) -> None:
    if result == WriteResult.CREATED or result == WriteResult.DRY_RUN:
        counts[object_type] = counts.get(object_type, 0) + 1
    elif result == WriteResult.SKIPPED_EXISTS:
        counts["skipped"] = counts.get("skipped", 0) + 1
    elif result == WriteResult.FAILED:
        counts["failed"] = counts.get("failed", 0) + 1


def _location_match_tokens(location: dict[str, Any]) -> list[str]:
    """Lowercased tokens that, if any appear in Exa result text, mean this base."""
    name = location["name"].lower()
    toks = [name]
    # Also accept the historical name where applicable.
    if location["slug"] == "fort_liberty":
        toks.append("fort bragg")
    return toks


def _exa_candidate_unit_names(text: str) -> list[str]:
    """Pull plausible unit names from free-form Exa text. Conservative regex."""
    pattern = re.compile(
        r"\b("
        r"(?:\d+(?:st|nd|rd|th))\s+"
        r"(?:[A-Z][A-Za-z]+\s+){0,3}"
        r"(?:Division|Brigade|Regiment|Battalion|Squadron|Wing|Group|Command|Corps)"
        r")\b"
    )
    seen = set()
    out = []
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


# ---------------------------------------------------------------------------
# Verify mode
# ---------------------------------------------------------------------------

def verify_counts(client: FoundryClient) -> None:
    print("\n=== Verify: object counts in Foundry ===")
    for object_type in (
        "GhostlineGeoFeature",
        "GhostlineUnit",
        "GhostlinePlatform",
        "GhostlineSensor",
        "GhostlineCommsAsset",
        "CascadeRisk",
        "AdversaryAction",
        "OpsecAssessment",
    ):
        try:
            objs = client.list_objects(object_type, page_size=200)
        except FoundryError as exc:
            print(f"  {object_type:24s} ERROR {exc}")
            continue
        prov_count = 0
        for o in objs:
            if all(o.get(k) for k in ("sourceUrl", "retrievedAt", "sourceType", "confidence")):
                prov_count += 1
        suffix = "" if object_type == "OpsecAssessment" else f"  (full provenance: {prov_count}/{len(objs)})"
        print(f"  {object_type:24s} count={len(objs)}{suffix}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Populate the GHOSTLINE Foundry ontology from public OSINT.")
    p.add_argument("--dry-run", action="store_true", help="Print would-be writes; do not call Foundry.")
    p.add_argument("--verify", action="store_true", help="After population (or alone), query Foundry and print counts.")
    p.add_argument("--location", action="append", default=[],
                   help="Limit population to this slug (may be repeated). Default: all 5.")
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    selected_slugs = set(args.location)
    locations = [L for L in LOCATIONS if not selected_slugs or L["slug"] in selected_slugs]
    if selected_slugs and not locations:
        print(f"No locations match {sorted(selected_slugs)}. Available: {[L['slug'] for L in LOCATIONS]}")
        return 2

    client: FoundryClient | None = None
    if not args.dry_run or args.verify:
        try:
            client = FoundryClient()
        except FoundryError as exc:
            print(f"Foundry config error: {exc}")
            return 2

    summary: dict[str, dict[str, int]] = {}
    if not args.verify or selected_slugs or not args.dry_run:
        # If --verify is the only flag (no other selection), skip population.
        do_populate = not (args.verify and not selected_slugs and not args.dry_run)
    else:
        do_populate = False
    do_populate = not (args.verify and not args.location and not args.dry_run and len(sys.argv) <= 2)
    # Simpler rule: populate unless the user *only* asked for --verify.
    only_verify = args.verify and not args.dry_run and not args.location
    do_populate = not only_verify

    if do_populate:
        for loc in locations:
            counts = populate_location(loc, client, dry_run=args.dry_run)
            summary[loc["slug"]] = counts

        print("\n=== Population summary ===")
        total = {"GhostlineGeoFeature": 0, "GhostlineUnit": 0, "GhostlinePlatform": 0, "skipped": 0, "failed": 0}
        for slug, counts in summary.items():
            print(f"  {slug:28s} {counts}")
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
        print(f"  {'TOTAL':28s} {total}")

    if args.verify:
        if client is None:
            try:
                client = FoundryClient()
            except FoundryError as exc:
                print(f"Foundry config error: {exc}")
                return 2
        verify_counts(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
