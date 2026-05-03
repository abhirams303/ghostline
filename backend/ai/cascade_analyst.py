"""GHOSTLINE Cascade Analyst — turns linked entities into CascadeRisk objects.

For each location with a populated GhostlineGeoFeature, traverse the ontology:

    GeoFeature
      ├── units            (reverse link "units")
      │     └── platforms  (reverse link "unit")
      │           └── sensors (reverse link "platform")  [empty in V1]
      └── commsAssets      (reverse link "commsAssets")  [empty in V1]

Pull the most recent OpsecAssessment for the same location, ask GPT-4 to
narrate how surface OPSEC exposure cascades through the linked entities to
compromise higher-order intelligence, and write one CascadeRisk per location.

Cascade score is computed deterministically in Python (LLMs are unreliable
at arithmetic):
    score = round(exposure_score * (1 + 0.08 * chain_depth)), capped at 100
    chain_depth == 0 -> no amplification (score == exposure_score)

Idempotent on cascade_id = "cascade_{slug}_{YYYY-MM-DD}".

Run:
    python -m backend.ai.cascade_analyst --dry-run
    python -m backend.ai.cascade_analyst --location fort_liberty
    python -m backend.ai.cascade_analyst --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timezone
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .palantir_integration import ACTIONS, FoundryClient, FoundryError

load_dotenv()
log = logging.getLogger("ghostline.cascade")

CASCADE_AMPLIFICATION_PER_DEPTH = 0.08
LLM_MODEL = "gpt-4o"
LLM_TIMEOUT = 30.0


def _opsec_assessment_url(assessment_id: str) -> str:
    """Construct the Foundry REST URL for an OpsecAssessment object — used as source_url
    on CascadeRisk. Reads env vars directly (defensively un-wrapped, like FoundryClient)."""
    host = (os.getenv("FOUNDRY_HOSTNAME") or "").strip().strip("<>'\"`")
    rid = (os.getenv("FOUNDRY_ONTOLOGY_RID") or "").strip().strip("<>'\"`")
    return f"https://{host}/api/v2/ontologies/{rid}/objects/OpsecAssessment/{assessment_id}"

LOCATIONS: list[dict[str, Any]] = [
    {"slug": "fort_liberty", "feature_id": "geo_fort_liberty"},
    {"slug": "naval_station_norfolk", "feature_id": "geo_naval_station_norfolk"},
    {"slug": "joint_base_lewis_mcchord", "feature_id": "geo_joint_base_lewis_mcchord"},
    {"slug": "naval_base_san_diego", "feature_id": "geo_naval_base_san_diego"},
    {"slug": "shack15", "feature_id": "geo_shack15"},
]

# The user's exact prompt, with {key} placeholders. We use simple .replace()
# substitution because the JSON-schema example below contains literal {} that
# would break str.format().
CASCADE_ANALYSIS_PROMPT = """You are a senior intelligence officer analyzing OPSEC cascade risk for a military installation. Surface-level public exposure (fitness app heatmaps, ADS-B aircraft tracking, satellite imaging windows) at a single base does not exist in isolation. It propagates through the linked operational entities — the units stationed there, the platforms they operate, the sensors those platforms carry — to compromise higher-order intelligence the adversary couldn't infer from any single source.

Inputs:
- Location: {location_name}
- Coordinates: {lat}, {lon}
- Surface OPSEC scores: Strava {strava_score}/100, Aircraft {adsb_score}/100, Satellite {satellite_score}/100
- Composite base exposure score: {exposure_score}
- Linked Units (from Palantir ontology): {units_with_names}
- Linked Platforms operated by those Units: {platforms_with_names}
- Linked Sensors carried by those Platforms: {sensors_with_names}
- Linked Comms Assets at this location: {comms_with_names}
- Chain depth: {chain_depth} (number of links from base to deepest entity)

Tasks:
1. intelligence_compromised: 150-word narrative naming the actual units and platforms from the input. Describe how surface exposure propagates through the linked entities to compromise specific operational intelligence the adversary couldn't get from any single source. Quote real entity names. Never invent units or platforms.

2. adversary_action_likely: 100-word narrative on what an adversary could DO with this cascaded intelligence. Specific exploitable actions, not generic surveillance.

3. recommended_upstream_mitigation: ONE specific imperative action that, if taken upstream in the chain, defeats the most downstream exposures simultaneously. Quote the actual platform or unit name.

4. composite_cascade_score: integer 0-100. Calculation:
   - Start with exposure_score from input
   - Multiply by (1 + 0.08 * chain_depth)
   - Cap at 100
   - If chain_depth is 0 (e.g., Shack15 with no military entities), cascade_score = exposure_score (no amplification)

Output strict JSON only:
{
  "intelligence_compromised": "...",
  "adversary_action_likely": "...",
  "recommended_upstream_mitigation": "...",
  "composite_cascade_score": int
}"""


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def cascade_id_for(slug: str, today: date, version: int = 1) -> str:
    """Daily cascade primary key. version > 1 produces a `_v{N}` suffix so a
    --regenerate run doesn't clobber the existing day's cascade — the old
    cascade remains in the audit trail and `_latest_cascade_for` (which
    sorts by createdTimestamp) automatically prefers the newer version."""
    base = f"cascade_{slug}_{today.isoformat()}"
    if version <= 1:
        return base
    return f"{base}_v{version}"


def _next_cascade_version(client: FoundryClient, slug: str, today: date) -> int:
    """Find the highest existing version for today's cascade and return next."""
    base = f"cascade_{slug}_{today.isoformat()}"
    pattern = re.compile(rf"^{re.escape(base)}(?:_v(\d+))?$")
    try:
        existing = client.list_objects("CascadeRisk", page_size=200)
    except FoundryError:
        return 2  # if we can't tell, assume v2 is safe
    versions: set[int] = set()
    for c in existing:
        cid = c.get("cascadeId") or ""
        m = pattern.match(cid)
        if m:
            versions.add(int(m.group(1) or "1"))
    return (max(versions) + 1) if versions else 1


def amplified_cascade_score(exposure_score: int, chain_depth: int) -> int:
    """Apply the cascade amplification formula. Pure, deterministic."""
    if chain_depth <= 0:
        return max(0, min(100, int(exposure_score)))
    raw = exposure_score * (1.0 + CASCADE_AMPLIFICATION_PER_DEPTH * chain_depth)
    return max(0, min(100, round(raw)))


def risk_level(score: int) -> str:
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MEDIUM"
    return "HIGH"


def determine_chain_confidence(units: list[dict], platforms: list[dict]) -> str:
    """If every chain entity has confidence='high', cascade is 'high'; otherwise 'medium'."""
    confidences = [
        (e.get("confidence") or "").lower()
        for e in (units + platforms)
        if e.get("confidence")
    ]
    if not confidences:
        return "medium"
    if all(c == "high" for c in confidences):
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Foundry traversal
# ---------------------------------------------------------------------------

def fetch_chain(client: FoundryClient, feature_id: str) -> dict[str, list[dict]]:
    """Pull the full GeoFeature → Units → Platforms → Sensors plus CommsAssets chain."""
    units: list[dict] = []
    platforms: list[dict] = []
    sensors: list[dict] = []
    comms: list[dict] = []

    try:
        units = client.get_linked_objects("GhostlineGeoFeature", feature_id, "units", page_size=50)
    except FoundryError as exc:
        log.warning("units traversal failed for %s: %s", feature_id, exc)

    for u in units:
        pk = u.get("unitId")
        if not pk:
            continue
        try:
            platforms.extend(
                client.get_linked_objects("GhostlineUnit", pk, "unit", page_size=20)
            )
        except FoundryError as exc:
            log.debug("unit-platforms traversal for %s: %s", pk, exc)

    for p in platforms:
        pk = p.get("platformId")
        if not pk:
            continue
        try:
            sensors.extend(
                client.get_linked_objects("GhostlinePlatform", pk, "platform", page_size=20)
            )
        except FoundryError as exc:
            log.debug("platform-sensors traversal for %s: %s", pk, exc)

    try:
        comms = client.get_linked_objects(
            "GhostlineGeoFeature", feature_id, "commsAssets", page_size=20
        )
    except FoundryError as exc:
        log.debug("commsAssets traversal for %s: %s", feature_id, exc)

    return {"units": units, "platforms": platforms, "sensors": sensors, "comms": comms}


def find_latest_assessment(client: FoundryClient, location_name: str) -> dict | None:
    """Return the highest-timestamp OpsecAssessment matching the location name."""
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


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def _format_entity_list(entities: list[dict], name_key: str, id_key: str) -> str:
    if not entities:
        return "(none)"
    lines = []
    for e in entities:
        name = e.get(name_key) or "?"
        eid = e.get(id_key) or "?"
        lines.append(f"  - {name} ({eid})")
    return "\n" + "\n".join(lines)


def _render_prompt(
    *,
    location_name: str,
    lat: float,
    lon: float,
    strava_score: int,
    adsb_score: int,
    satellite_score: int,
    exposure_score: int,
    chain_depth: int,
    units: list[dict],
    platforms: list[dict],
    sensors: list[dict],
    comms: list[dict],
) -> str:
    placeholders = {
        "location_name": location_name,
        "lat": f"{lat:.4f}",
        "lon": f"{lon:.4f}",
        "strava_score": str(strava_score),
        "adsb_score": str(adsb_score),
        "satellite_score": str(satellite_score),
        "exposure_score": str(exposure_score),
        "chain_depth": str(chain_depth),
        "units_with_names": _format_entity_list(units, "name", "unitId"),
        "platforms_with_names": _format_entity_list(platforms, "name", "platformId"),
        "sensors_with_names": _format_entity_list(sensors, "name", "sensorId"),
        "comms_with_names": _format_entity_list(comms, "name", "assetId"),
    }
    rendered = CASCADE_ANALYSIS_PROMPT
    for key, value in placeholders.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _fallback_narrative(
    *, location_name: str, exposure_score: int, chain_depth: int,
    units: list[dict], platforms: list[dict],
) -> dict[str, Any]:
    if chain_depth == 0:
        compromise = (
            f"No linked Units or Platforms populated for {location_name}; cascade "
            f"analysis is bounded by the surface exposure score ({exposure_score}/100). "
            "No amplification through downstream operational entities is possible at this depth."
        )
        action = (
            "Adversary intelligence is limited to the surface OPSEC layer. "
            "No deeper inference is enabled by the current ontology state."
        )
        mitigation = (
            "Populate GhostlineUnit and GhostlinePlatform objects for this location "
            "before running the cascade analyst again."
        )
    else:
        unit_names = ", ".join((u.get("name") or "?") for u in units[:5])
        platform_names = ", ".join((p.get("name") or "?") for p in platforms[:3])
        compromise = (
            f"{location_name} hosts {len(units)} populated Units (e.g., {unit_names}) "
            f"with {len(platforms)} linked Platforms ({platform_names or 'none on file'}). "
            f"Surface exposure (composite {exposure_score}/100) cascades through these "
            "links to expose unit-level operational rhythms and platform availability."
        )
        action = (
            "Adversary can correlate surface signatures with the linked unit chain to "
            "predict deployment readiness and platform staging windows. "
            "[Manual review recommended — automated narrative unavailable.]"
        )
        focus_unit = units[0].get("name") if units else "the senior tenant unit"
        mitigation = (
            f"Direct {focus_unit} to enforce OPSEC discipline across the linked "
            "Platforms before any amplification cascades downstream."
        )
    return {
        "intelligence_compromised": compromise,
        "adversary_action_likely": action,
        "recommended_upstream_mitigation": mitigation,
        "composite_cascade_score": amplified_cascade_score(exposure_score, chain_depth),
        "_fallback": True,
    }


def run_cascade_llm(prompt: str) -> dict[str, Any] | None:
    """Call OpenAI; return parsed JSON or None on any failure."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY missing — using deterministic fallback narrative")
        return None
    try:
        client = OpenAI(api_key=api_key, timeout=LLM_TIMEOUT)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            response_format={"type": "json_object"},
            temperature=0.3,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Output the strict JSON object now."},
            ],
        )
    except Exception as exc:  # noqa: BLE001 — demo path must not crash
        log.warning("OpenAI call failed: %s", exc)
        return None
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("LLM returned non-JSON: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Per-location cascade build
# ---------------------------------------------------------------------------

def build_cascade_for_location(
    client: FoundryClient,
    loc: dict[str, Any],
    today: date,
    *,
    regenerate: bool = False,
) -> dict[str, Any] | None:
    feature_id = loc["feature_id"]
    geo = client.get_object("GhostlineGeoFeature", feature_id)
    if geo is None:
        log.error("no GhostlineGeoFeature[%s] — run osint_populator first", feature_id)
        return None

    location_name = geo.get("name") or loc["slug"]
    lat = float(geo["latitude"])
    lon = float(geo["longitude"])

    chain = fetch_chain(client, feature_id)
    units, platforms = chain["units"], chain["platforms"]
    sensors, comms = chain["sensors"], chain["comms"]

    chain_entities: list[str] = [feature_id]
    chain_entities.extend(u["unitId"] for u in units if u.get("unitId"))
    chain_entities.extend(p["platformId"] for p in platforms if p.get("platformId"))
    chain_entities.extend(s["sensorId"] for s in sensors if s.get("sensorId"))
    chain_entities.extend(c["assetId"] for c in comms if c.get("assetId"))
    chain_depth = len(chain_entities) - 1

    assessment = find_latest_assessment(client, location_name)
    if assessment is None:
        log.error(
            "no OpsecAssessment for %s — run assessment_writeback before cascade_analyst",
            location_name,
        )
        return None

    exposure_score = int(assessment.get("exposureScore") or 0)
    strava_score = int(assessment.get("stravaDensityScore") or 0)
    adsb_score = int(assessment.get("aircraftPredictabilityScore") or 0)
    satellite_score = int(assessment.get("satelliteVulnerabilityScore") or 0)
    assessment_id = assessment.get("assessmentId") or ""

    log.info(
        "%s: chain_depth=%d (units=%d platforms=%d sensors=%d comms=%d), exposure=%d",
        loc["slug"], chain_depth, len(units), len(platforms), len(sensors), len(comms),
        exposure_score,
    )

    prompt = _render_prompt(
        location_name=location_name, lat=lat, lon=lon,
        strava_score=strava_score, adsb_score=adsb_score, satellite_score=satellite_score,
        exposure_score=exposure_score, chain_depth=chain_depth,
        units=units, platforms=platforms, sensors=sensors, comms=comms,
    )

    llm_out = run_cascade_llm(prompt)
    if llm_out is None:
        narrative = _fallback_narrative(
            location_name=location_name, exposure_score=exposure_score,
            chain_depth=chain_depth, units=units, platforms=platforms,
        )
    else:
        narrative = llm_out
        narrative.setdefault("_fallback", False)

    # Always overwrite the cascade score with the deterministic Python value —
    # LLMs are unreliable at the arithmetic and we need the demo numbers stable.
    deterministic_score = amplified_cascade_score(exposure_score, chain_depth)
    llm_score = narrative.get("composite_cascade_score")
    if isinstance(llm_score, (int, float)) and abs(int(llm_score) - deterministic_score) > 5:
        log.info(
            "LLM cascade score %s differs from deterministic %s for %s — using deterministic",
            llm_score, deterministic_score, loc["slug"],
        )
    narrative["composite_cascade_score"] = deterministic_score

    confidence = determine_chain_confidence(units, platforms)
    if narrative.get("_fallback"):
        confidence = "low"

    version = _next_cascade_version(client, loc["slug"], today) if regenerate else 1
    cid = cascade_id_for(loc["slug"], today, version=version)
    now_iso = datetime.now(timezone.utc).isoformat()
    source_url = _opsec_assessment_url(assessment_id)

    params: dict[str, Any] = {
        "cascade-id": cid,
        "location-name": location_name,
        "center-lat": lat,
        "center-lon": lon,
        "chain-depth": chain_depth,
        "chain-entities": chain_entities,
        "composite-cascade-score": deterministic_score,
        "intelligence-compromised": narrative.get("intelligence_compromised", "")[:6000],
        "adversary-action-likely": narrative.get("adversary_action_likely", "")[:4000],
        "recommended-upstream-mitigation": narrative.get("recommended_upstream_mitigation", "")[:2000],
        "created-timestamp": now_iso,
        "source-assessment-id": assessment_id,
        "location-feature-id": feature_id,
        "source-url": source_url,
        "retrieved-at": now_iso,
        "source-type": "agent_inferred",
        "confidence": confidence,
    }

    return {
        "params": params,
        "narrative": narrative,
        "chain_depth": chain_depth,
        "exposure_score": exposure_score,
        "deterministic_score": deterministic_score,
        "risk": risk_level(deterministic_score),
        "assessment_id": assessment_id,
    }


# ---------------------------------------------------------------------------
# Write + verify
# ---------------------------------------------------------------------------

def write_cascade(
    client: FoundryClient, cascade: dict[str, Any], *, dry_run: bool
) -> str:
    params = cascade["params"]
    cid = params["cascade-id"]
    if dry_run:
        narrative = cascade["narrative"]
        print(f"  [DRY] CascadeRisk[{cid}]")
        print(f"        location:        {params['location-name']} ({params['center-lat']:.4f}, {params['center-lon']:.4f})")
        print(f"        chain_depth:     {params['chain-depth']}")
        print(f"        chain_entities:  {len(params['chain-entities'])} ids "
              f"(first 3: {params['chain-entities'][:3]})")
        print(f"        exposure:        {cascade['exposure_score']}")
        print(f"        cascade_score:   {params['composite-cascade-score']}  (risk: {cascade['risk']})")
        print(f"        confidence:      {params['confidence']}")
        print(f"        source_assess:   {params['source-assessment-id']}")
        print(f"        intelligence_compromised:")
        for line in narrative.get("intelligence_compromised", "").splitlines():
            print(f"          {line}")
        print(f"        adversary_action_likely:")
        for line in narrative.get("adversary_action_likely", "").splitlines():
            print(f"          {line}")
        print(f"        recommended_upstream_mitigation:")
        for line in narrative.get("recommended_upstream_mitigation", "").splitlines():
            print(f"          {line}")
        return "dry-run"

    try:
        existing = client.get_object("CascadeRisk", cid)
    except FoundryError as exc:
        log.warning("idempotency check failed for %s: %s", cid, exc)
        existing = None
    if existing is not None:
        log.info("CascadeRisk[%s] already exists — skipping", cid)
        return "exists"

    try:
        client.apply_action(ACTIONS["CascadeRisk"], params)
    except FoundryError as exc:
        log.error("create CascadeRisk[%s] failed: %s", cid, exc)
        return "failed"

    try:
        readback = client.get_object("CascadeRisk", cid)
    except FoundryError as exc:
        log.error("read-back CascadeRisk[%s] failed: %s", cid, exc)
        return "failed"
    if readback is None:
        log.error("WROTE BUT VANISHED: CascadeRisk[%s]", cid)
        return "failed"

    # Verify the FK-on-create resolved the link to OpsecAssessment.
    try:
        linked = client.get_linked_objects(
            "CascadeRisk", cid, "analyzedCascadeRisks", page_size=5
        )
        if not linked:
            log.warning(
                "CascadeRisk[%s] wrote OK but analyzedCascadeRisks link is empty "
                "(source-assessment-id may not have resolved)", cid,
            )
        else:
            log.info(
                "CascadeRisk[%s] linked to OpsecAssessment[%s]",
                cid, linked[0].get("assessmentId"),
            )
    except FoundryError as exc:
        log.warning("link verification failed for CascadeRisk[%s]: %s", cid, exc)

    log.info("created CascadeRisk[%s]", cid)
    return "created"


def verify_cascade_risks(client: FoundryClient) -> None:
    print("\n=== Verify: CascadeRisk objects in Foundry ===")
    try:
        objs = client.list_objects("CascadeRisk", page_size=200)
    except FoundryError as exc:
        print(f"  ERROR listing: {exc}")
        return
    print(f"  total: {len(objs)}")
    for o in sorted(objs, key=lambda x: -(x.get("compositeCascadeScore") or 0)):
        cid = o.get("cascadeId")
        loc = o.get("locationName")
        score = o.get("compositeCascadeScore")
        depth = o.get("chainDepth")
        conf = o.get("confidence")
        ic_len = len(o.get("intelligenceCompromised") or "")
        print(f"  - {cid}")
        print(f"      location={loc}  cascade={score}  chain_depth={depth}  conf={conf}")
        print(f"      intelligence_compromised: {ic_len} chars")


def print_summary_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    print("\n=== Cascade summary ===")
    print(f"  {'Location':28s} | {'Base Exposure':>13s} | {'Chain Depth':>11s} | "
          f"{'Cascade Score':>13s} | Risk")
    print(f"  {'-'*28} | {'-'*13} | {'-'*11} | {'-'*13} | {'-'*6}")
    for r in sorted(rows, key=lambda x: -x["deterministic_score"]):
        print(
            f"  {r['location_name']:28s} | "
            f"{r['exposure_score']:>13d} | "
            f"{r['chain_depth']:>11d} | "
            f"{r['deterministic_score']:>13d} | "
            f"{r['risk']}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Write CascadeRisk objects from the populated ontology.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--regenerate", action="store_true",
                   help="Force a new cascade version (cascade_..._v2, _v3, ...) "
                        "instead of skipping when today's cascade already exists. "
                        "Old versions remain as audit trail; query_api picks the latest "
                        "by createdTimestamp.")
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
    logging.getLogger("httpx").setLevel(logging.WARNING)

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

    summary_rows: list[dict[str, Any]] = []
    counts = {"created": 0, "exists": 0, "failed": 0, "dry-run": 0, "no-data": 0}
    if not only_verify:
        for loc in locations:
            print(f"\n=== {loc['slug']} ===")
            cascade = build_cascade_for_location(client, loc, today, regenerate=args.regenerate)
            if cascade is None:
                counts["no-data"] += 1
                continue
            result = write_cascade(client, cascade, dry_run=args.dry_run)
            counts[result] = counts.get(result, 0) + 1
            summary_rows.append({
                "location_name": cascade["params"]["location-name"],
                "exposure_score": cascade["exposure_score"],
                "chain_depth": cascade["chain_depth"],
                "deterministic_score": cascade["deterministic_score"],
                "risk": cascade["risk"],
            })

        print_summary_table(summary_rows)
        print(f"\n  Writeback counts: {counts}")

    if args.verify:
        verify_cascade_risks(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
