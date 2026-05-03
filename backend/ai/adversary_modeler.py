"""GHOSTLINE Adversary Modeler — turns CascadeRisks into specific AdversaryActions.

For each CascadeRisk in Foundry:
  1. Resolve the cascade's chain_entities IDs to real entity names.
  2. Ask GPT-4 to predict 1-3 specific adversary actions exploiting the cascade.
  3. Write each as an AdversaryAction object, FK-linked to the parent cascade
     via source_cascade_id.

The schema's `adversary-capability-required` field carries both the
capability description and the LLM's rationale (concatenated) — the
AdversaryAction object type doesn't have a separate `rationale` property,
so we preserve that reasoning here rather than discard it.

Idempotent on action_id = "action_{cascade_id}_{index}". Re-running the
same day skips already-written actions.

Run:
    python -m backend.ai.adversary_modeler --dry-run
    python -m backend.ai.adversary_modeler --location fort_liberty
    python -m backend.ai.adversary_modeler --verify
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .palantir_integration import ACTIONS, FoundryClient, FoundryError

load_dotenv()
log = logging.getLogger("ghostline.adversary")

LLM_MODEL = "gpt-4o"
LLM_TIMEOUT = 30.0
MAX_ACTIONS_PER_CASCADE = 3

ALLOWED_ACTION_TYPES = {
    "surveillance", "kinetic_planning", "deception", "interdiction", "disruption",
}
ALLOWED_TIMELINES = {"immediate", "days", "weeks", "months"}

# Object types whose IDs may appear in chain_entities, ordered for the entity-map
# build. Sensors and CommsAssets are empty in V1; harmless to query.
CHAIN_ENTITY_TYPES = (
    ("GhostlineGeoFeature", "featureId"),
    ("GhostlineUnit", "unitId"),
    ("GhostlinePlatform", "platformId"),
    ("GhostlineSensor", "sensorId"),
    ("GhostlineCommsAsset", "assetId"),
)


# The user's exact prompt template; .replace() substitution handles the
# literal {} in the JSON schema example.
ADVERSARY_MODELER_PROMPT = """You are modeling adversary intent given a specific OPSEC cascade compromise. Given the cascaded intelligence available, predict what a sophisticated adversary would actually DO to exploit it.

Cascade context:
- Location: {location_name} at {lat}, {lon}
- Intelligence compromised: {intelligence_compromised}
- Predicted exploitation: {adversary_action_likely}
- Linked entities at risk: {chain_entities_named}
- Composite cascade score: {cascade_score}

Generate 1-3 specific adversary actions. Each action must be:
- Specific: name a real entity (unit, platform, sensor) from the chain
- Realistic: within current adversary capabilities (no sci-fi, no nation-state-only assumptions)
- Time-bounded: realistic timeline for execution

Output strict JSON:
{
  "actions": [
    {
      "action_type": "surveillance" | "kinetic_planning" | "deception" | "interdiction" | "disruption",
      "target_entity_name": "specific entity name from the chain",
      "target_entity_id": "the entity_id if known, otherwise empty string",
      "adversary_capability_required": "what an adversary needs to execute this — be concrete",
      "timeline_estimate": "immediate" | "days" | "weeks" | "months",
      "rationale": "1-2 sentence explanation of why this exploits the cascade"
    }
  ]
}

Higher cascade scores warrant more specific, more aggressive actions. Lower scores warrant surveillance-stage actions. For Shack15 (civilian, low cascade), generate ONE action of type "surveillance" only — this is OPSEC reconnaissance against a civilian gathering, not an attack."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def action_id_for(cascade_id: str, index: int) -> str:
    return f"action_{cascade_id}_{index}"


def _cascade_risk_url(cascade_id: str) -> str:
    """Foundry REST URL for a CascadeRisk — used as source_url on AdversaryAction."""
    host = (os.getenv("FOUNDRY_HOSTNAME") or "").strip().strip("<>'\"`")
    rid = (os.getenv("FOUNDRY_ONTOLOGY_RID") or "").strip().strip("<>'\"`")
    return f"https://{host}/api/v2/ontologies/{rid}/objects/CascadeRisk/{cascade_id}"


def build_entity_name_map(client: FoundryClient) -> dict[str, dict[str, str]]:
    """One-time pull of every chain-eligible entity's name. Three list_objects
    calls (GeoFeature, Unit, Platform) replace ~100 per-id GETs.

    Returns: dict[entity_id] -> {"name": str, "object_type": str}
    """
    out: dict[str, dict[str, str]] = {}
    for object_type, pk_field in CHAIN_ENTITY_TYPES:
        try:
            objs = client.list_objects(object_type, page_size=200)
        except FoundryError as exc:
            log.warning("list %s failed: %s", object_type, exc)
            continue
        for o in objs:
            pk = o.get(pk_field)
            if not pk:
                continue
            out[pk] = {
                "name": o.get("name") or pk,
                "object_type": object_type,
            }
    log.info("entity name map: %d total objects across %d types", len(out), len(CHAIN_ENTITY_TYPES))
    return out


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _format_chain_entities(chain_entities: list[str], entity_map: dict[str, dict]) -> str:
    if not chain_entities:
        return "(no entities in chain)"
    lines = []
    for eid in chain_entities:
        meta = entity_map.get(eid)
        if meta:
            lines.append(f"  - {meta['object_type']}: {meta['name']} ({eid})")
        else:
            lines.append(f"  - (unknown type): {eid}")
    return "\n" + "\n".join(lines)


def _render_prompt(cascade: dict[str, Any], entity_map: dict[str, dict]) -> str:
    chain_entities = cascade.get("chainEntities") or []
    placeholders = {
        "location_name": cascade.get("locationName") or "?",
        "lat": f"{float(cascade.get('centerLat') or 0):.4f}",
        "lon": f"{float(cascade.get('centerLon') or 0):.4f}",
        "intelligence_compromised": cascade.get("intelligenceCompromised") or "(none)",
        "adversary_action_likely": cascade.get("adversaryActionLikely") or "(none)",
        "chain_entities_named": _format_chain_entities(chain_entities, entity_map),
        "cascade_score": str(cascade.get("compositeCascadeScore") or 0),
    }
    rendered = ADVERSARY_MODELER_PROMPT
    for k, v in placeholders.items():
        rendered = rendered.replace("{" + k + "}", v)
    return rendered


# ---------------------------------------------------------------------------
# LLM call + fallback + validation
# ---------------------------------------------------------------------------

def _validate_action(raw: dict[str, Any], cascade_id: str) -> dict[str, Any] | None:
    """Pass-through with warning logs on off-spec values. None on irrecoverable."""
    if not isinstance(raw, dict):
        log.warning("[%s] action is not a dict: %r", cascade_id, raw)
        return None
    action_type = (raw.get("action_type") or "").strip().lower()
    timeline = (raw.get("timeline_estimate") or "").strip().lower()
    if action_type not in ALLOWED_ACTION_TYPES:
        log.warning("[%s] off-spec action_type=%r", cascade_id, action_type)
    if timeline not in ALLOWED_TIMELINES:
        log.warning("[%s] off-spec timeline_estimate=%r", cascade_id, timeline)
    target_name = (raw.get("target_entity_name") or "").strip()
    if not target_name:
        log.warning("[%s] action missing target_entity_name; skipping", cascade_id)
        return None
    return {
        "action_type": action_type or "surveillance",
        "target_entity_name": target_name,
        "target_entity_id": (raw.get("target_entity_id") or "").strip(),
        "adversary_capability_required": (raw.get("adversary_capability_required") or "").strip(),
        "timeline_estimate": timeline or "weeks",
        "rationale": (raw.get("rationale") or "").strip(),
    }


def _run_llm(prompt: str) -> list[dict[str, Any]] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY missing — using deterministic fallback action")
        return None
    try:
        client = OpenAI(api_key=api_key, timeout=LLM_TIMEOUT)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            response_format={"type": "json_object"},
            temperature=0.4,
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
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("LLM returned non-JSON: %s", exc)
        return None
    actions = parsed.get("actions")
    if not isinstance(actions, list):
        log.warning("LLM JSON missing 'actions' list; got: %r", parsed)
        return None
    return actions


def _fallback_actions(cascade: dict[str, Any], entity_map: dict[str, dict]) -> list[dict[str, Any]]:
    """Deterministic single surveillance action when the LLM is unavailable."""
    location_name = cascade.get("locationName") or "?"
    chain_entities = cascade.get("chainEntities") or []
    target_id = ""
    target_name = location_name
    # Prefer a Unit, then GeoFeature, as the surveillance target.
    for eid in chain_entities:
        meta = entity_map.get(eid)
        if meta and meta["object_type"] == "GhostlineUnit":
            target_id = eid
            target_name = meta["name"]
            break
    else:
        if chain_entities:
            target_id = chain_entities[0]
            meta = entity_map.get(target_id)
            target_name = meta["name"] if meta else location_name
    return [{
        "action_type": "surveillance",
        "target_entity_name": target_name,
        "target_entity_id": target_id,
        "adversary_capability_required": (
            "Open-source intelligence collection and pattern-of-life monitoring. "
            "[Note: LLM unavailable — deterministic fallback action; manual review recommended.]"
        ),
        "timeline_estimate": "weeks",
        "rationale": (
            "With richer LLM analysis unavailable, the conservative adversary baseline "
            "is sustained OSINT collection against the most senior entity in the chain."
        ),
        "_fallback": True,
    }]


# ---------------------------------------------------------------------------
# Per-cascade build
# ---------------------------------------------------------------------------

def build_actions_for_cascade(
    client: FoundryClient,
    cascade: dict[str, Any],
    entity_map: dict[str, dict],
) -> list[dict[str, Any]]:
    cascade_id = cascade.get("cascadeId") or ""
    if not cascade_id:
        return []
    prompt = _render_prompt(cascade, entity_map)
    raw_actions = _run_llm(prompt)
    is_fallback = False
    if raw_actions is None:
        validated = _fallback_actions(cascade, entity_map)
        is_fallback = True
    else:
        validated = []
        for raw in raw_actions:
            v = _validate_action(raw, cascade_id)
            if v is not None:
                validated.append(v)

    # Cap at MAX_ACTIONS_PER_CASCADE — first-N preserves LLM ordering (most aggressive first).
    if len(validated) > MAX_ACTIONS_PER_CASCADE:
        log.info("[%s] LLM returned %d actions; capping to %d", cascade_id, len(validated), MAX_ACTIONS_PER_CASCADE)
        validated = validated[:MAX_ACTIONS_PER_CASCADE]

    parent_confidence = (cascade.get("confidence") or "medium").lower()
    confidence = "low" if is_fallback else parent_confidence
    now_iso = datetime.now(timezone.utc).isoformat()
    source_url = _cascade_risk_url(cascade_id)

    drafts: list[dict[str, Any]] = []
    for idx, action in enumerate(validated):
        # Resolve target_entity_id: trust the LLM if it returned one, else look
        # up by name from the entity_map.
        target_id = action.get("target_entity_id") or ""
        if not target_id:
            target_lower = action["target_entity_name"].lower()
            for eid, meta in entity_map.items():
                if meta["name"].lower() == target_lower:
                    target_id = eid
                    break

        capability = action.get("adversary_capability_required") or ""
        rationale = action.get("rationale") or ""
        # Concatenate rationale into the capability field — the schema has no
        # separate rationale property, and the reasoning is operationally useful
        # to downstream consumers.
        if rationale:
            capability_full = f"{capability}\n\nRationale: {rationale}"
        else:
            capability_full = capability

        params: dict[str, Any] = {
            "action-id": action_id_for(cascade_id, idx),
            "action-type": action["action_type"],
            "target-entity-name": action["target_entity_name"][:300],
            "target-entity-id": target_id,
            "adversary-capability-required": capability_full[:6000],
            "timeline-estimate": action["timeline_estimate"],
            "source-cascade-id": cascade_id,
            "center-lat": float(cascade.get("centerLat") or 0),
            "center-lon": float(cascade.get("centerLon") or 0),
            "created-timestamp": now_iso,
            "source-url": source_url,
            "retrieved-at": now_iso,
            "source-type": "agent_inferred",
            "confidence": confidence,
        }
        drafts.append({
            "params": params,
            "rationale": rationale,
            "is_fallback": is_fallback,
        })
    return drafts


# ---------------------------------------------------------------------------
# Write + verify
# ---------------------------------------------------------------------------

def write_action(
    client: FoundryClient, draft: dict[str, Any], *, dry_run: bool
) -> str:
    params = draft["params"]
    aid = params["action-id"]
    if dry_run:
        print(f"  [DRY] AdversaryAction[{aid}]")
        print(f"        action_type:       {params['action-type']}")
        print(f"        target:            {params['target-entity-name']} (id: {params['target-entity-id']!r})")
        print(f"        timeline:          {params['timeline-estimate']}")
        print(f"        confidence:        {params['confidence']}")
        print(f"        source_cascade:    {params['source-cascade-id']}")
        capability = params["adversary-capability-required"]
        print(f"        capability_required:")
        for line in capability.splitlines():
            print(f"          {line[:200]}")
        return "dry-run"

    try:
        existing = client.get_object("AdversaryAction", aid)
    except FoundryError as exc:
        log.warning("idempotency check failed for %s: %s", aid, exc)
        existing = None
    if existing is not None:
        log.info("AdversaryAction[%s] already exists — skipping", aid)
        return "exists"

    try:
        client.apply_action(ACTIONS["AdversaryAction"], params)
    except FoundryError as exc:
        log.error("create AdversaryAction[%s] failed: %s", aid, exc)
        return "failed"

    try:
        readback = client.get_object("AdversaryAction", aid)
    except FoundryError as exc:
        log.error("read-back AdversaryAction[%s] failed: %s", aid, exc)
        return "failed"
    if readback is None:
        log.error("WROTE BUT VANISHED: AdversaryAction[%s]", aid)
        return "failed"

    log.info("created AdversaryAction[%s]", aid)
    return "created"


def verify_actions(client: FoundryClient) -> None:
    print("\n=== Verify: AdversaryAction objects in Foundry ===")
    try:
        objs = client.list_objects("AdversaryAction", page_size=200)
    except FoundryError as exc:
        print(f"  ERROR listing: {exc}")
        return
    print(f"  total: {len(objs)}")

    # Group by parent cascade for readable output.
    by_cascade: dict[str, list[dict]] = {}
    for o in objs:
        by_cascade.setdefault(o.get("sourceCascadeId") or "?", []).append(o)
    for cid, actions in by_cascade.items():
        print(f"\n  CascadeRisk[{cid}]: {len(actions)} action(s)")
        for a in actions:
            print(
                f"    - {a.get('actionId')}  "
                f"type={a.get('actionType')}  "
                f"target={a.get('targetEntityName')}  "
                f"timeline={a.get('timelineEstimate')}  "
                f"conf={a.get('confidence')}"
            )

    # Verify reverse traversal CascadeRisk -> cascadeRisk -> AdversaryAction.
    print("\n=== Reverse link: CascadeRisk.cascadeRisk -> AdversaryActions ===")
    cascades = client.list_objects("CascadeRisk", page_size=50)
    for c in cascades:
        cid = c.get("cascadeId")
        try:
            linked = client.get_linked_objects("CascadeRisk", cid, "cascadeRisk", page_size=10)
        except FoundryError as exc:
            print(f"  {cid}: link error: {exc}")
            continue
        print(f"  {cid}: {len(linked)} linked AdversaryAction(s)")


def print_summary_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    print("\n=== Adversary action summary ===")
    print(f"  {'Location':28s} | {'Cascade':>7s} | {'#Actions':>8s} | "
          f"{'Top Action Type':18s} | Top Target")
    print(f"  {'-'*28} | {'-'*7} | {'-'*8} | {'-'*18} | {'-'*40}")
    for r in sorted(rows, key=lambda x: -x["cascade_score"]):
        top_type = r["top_action_type"] or "—"
        top_target = (r["top_target"] or "—")[:40]
        print(
            f"  {r['location_name']:28s} | "
            f"{r['cascade_score']:>7d} | "
            f"{r['n_actions']:>8d} | "
            f"{top_type:18s} | "
            f"{top_target}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Write AdversaryAction objects from CascadeRisks in the populated ontology."
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--location", action="append", default=[],
                   help="Filter by location name substring (case-insensitive). Repeatable.")
    p.add_argument("--log-level", default="INFO")
    return p


def _select_cascades(cascades: list[dict], filters: list[str]) -> list[dict]:
    if not filters:
        return cascades
    needles = [f.lower() for f in filters]
    out = []
    for c in cascades:
        loc = (c.get("locationName") or "").lower()
        cid = (c.get("cascadeId") or "").lower()
        if any(n in loc or n in cid for n in needles):
            out.append(c)
    return out


def _dedupe_to_latest_per_location(cascades: list[dict]) -> list[dict]:
    """When multiple cascades exist per location (after cascade_analyst --regenerate),
    keep only the highest-createdTimestamp one per locationName. Otherwise we'd
    redundantly generate adversary actions against superseded analyses."""
    by_loc: dict[str, dict] = {}
    for c in cascades:
        loc = c.get("locationName") or ""
        existing = by_loc.get(loc)
        if existing is None or (c.get("createdTimestamp") or "") > (existing.get("createdTimestamp") or ""):
            by_loc[loc] = c
    return list(by_loc.values())


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        client = FoundryClient()
    except FoundryError as exc:
        print(f"Foundry config error: {exc}")
        return 2

    only_verify = args.verify and not args.dry_run and not args.location
    summary_rows: list[dict[str, Any]] = []
    counts = {"created": 0, "exists": 0, "failed": 0, "dry-run": 0, "no-data": 0}

    if not only_verify:
        try:
            cascades = client.list_objects("CascadeRisk", page_size=200)
        except FoundryError as exc:
            print(f"list CascadeRisk failed: {exc}")
            return 2

        cascades = _dedupe_to_latest_per_location(cascades)
        cascades = _select_cascades(cascades, args.location)
        if not cascades:
            print("No CascadeRisk objects matched. "
                  "Run cascade_analyst first if the ontology is empty.")
            return 0

        entity_map = build_entity_name_map(client)

        for cascade in sorted(
            cascades, key=lambda c: -(c.get("compositeCascadeScore") or 0)
        ):
            location_name = cascade.get("locationName") or "?"
            print(f"\n=== {location_name} (cascade={cascade.get('cascadeId')}) ===")
            drafts = build_actions_for_cascade(client, cascade, entity_map)
            if not drafts:
                counts["no-data"] += 1
                continue
            for draft in drafts:
                result = write_action(client, draft, dry_run=args.dry_run)
                counts[result] = counts.get(result, 0) + 1

            top = drafts[0]["params"]
            summary_rows.append({
                "location_name": location_name,
                "cascade_score": int(cascade.get("compositeCascadeScore") or 0),
                "n_actions": len(drafts),
                "top_action_type": top["action-type"],
                "top_target": top["target-entity-name"],
            })

        print_summary_table(summary_rows)
        print(f"\n  Writeback counts: {counts}")

    if args.verify:
        verify_actions(client)

    return 0


if __name__ == "__main__":
    sys.exit(main())
