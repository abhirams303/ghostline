"""Verify the Foundry Bearer token, discover the ontology RID, and list object types.

Read-only. Safe to run. Reads FOUNDRY_TOKEN and FOUNDRY_HOSTNAME from the
project-root .env. Run with:

    python scripts/test_foundry.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    sys.stderr.write("Missing dependency: pip install requests\n")
    sys.exit(2)

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EXPECTED_OBJECT_TYPES = [
    "GhostlineGeoFeature",
    "GhostlineUnit",
    "GhostlinePlatform",
    "GhostlineSensor",
    "GhostlineCommsAsset",
    "CascadeRisk",
    "AdversaryAction",
    "OpsecAssessment",
]

EXPECTED_RIDS = {
    "GhostlineGeoFeature": "ri.ontology.main.object-type.f502f6e7-9188-4382-a1d2-d1f8347e9888",
    "GhostlineUnit":       "ri.ontology.main.object-type.1840f19e-3617-480f-9ac6-abbf8e46d7c1",
    "GhostlinePlatform":   "ri.ontology.main.object-type.b2ca81c6-1920-414e-876b-c0d75beb7e25",
    "GhostlineSensor":     "ri.ontology.main.object-type.3b0b2a70-951b-4ba4-bc25-430619a34023",
    "GhostlineCommsAsset": "ri.ontology.main.object-type.988dfc5c-6f76-45fd-a8a8-9daa87dbf737",
    "CascadeRisk":         "ri.ontology.main.object-type.37960cfc-5161-407a-a37f-3f796d85a4f2",
    "AdversaryAction":     "ri.ontology.main.object-type.1d027012-9068-4930-93bb-98b00a1abe1b",
}

PROVENANCE_PROPS = ("source_url", "retrieved_at", "source_type", "confidence")

EXPECTED_LINKS: dict[str, list[tuple[str, str]]] = {
    "GhostlineGeoFeature": [("hosts_unit", "GhostlineUnit"), ("has_comms", "GhostlineCommsAsset")],
    "GhostlineUnit":       [("operates", "GhostlinePlatform")],
    "GhostlinePlatform":   [("carries", "GhostlineSensor")],
    "GhostlineSensor":     [],
    "GhostlineCommsAsset": [],
    "CascadeRisk":         [("analyzed_from", "OpsecAssessment"), ("located_at", "GhostlineGeoFeature")],
    "AdversaryAction":     [("responds_to", "CascadeRisk")],
    "OpsecAssessment":     [],
}

ONTOLOGY_NAME_HINTS = ("natsec", "hackathon", "opsec", "ghostline")
TIMEOUT = 10


def die(msg: str, code: int = 1) -> None:
    sys.stderr.write(f"\n[FATAL] {msg}\n")
    sys.exit(code)


def unwrap(value: str) -> str:
    """Strip whitespace and a single pair of wrapping <>, "" or '' if present.

    Catches the common pasting mistake where a placeholder like <your-token> was
    replaced inline but the angle brackets were left in.
    """
    v = value.strip()
    pairs = (("<", ">"), ('"', '"'), ("'", "'"), ("`", "`"))
    for left, right in pairs:
        if len(v) >= 2 and v.startswith(left) and v.endswith(right):
            v = v[1:-1].strip()
            break
    return v


def normalize_hostname(raw: str) -> str:
    h = unwrap(raw)
    for prefix in ("https://", "http://"):
        if h.startswith(prefix):
            h = h[len(prefix):]
    return h.rstrip("/")


def fmt_response(resp: requests.Response) -> str:
    body = resp.text or "<empty>"
    if len(body) > 4000:
        body = body[:4000] + f"\n... [truncated {len(resp.text) - 4000} chars]"
    return (
        f"  HTTP {resp.status_code} {resp.reason}\n"
        f"  url:  {resp.url}\n"
        f"  body: {body}"
    )


def get_json(session: requests.Session, base: str, path: str, **params: Any) -> dict:
    url = f"{base}{path}"
    try:
        resp = session.get(url, params=params or None, timeout=TIMEOUT)
    except requests.RequestException as exc:
        die(f"GET {url} raised {type(exc).__name__}: {exc}")
    if not resp.ok:
        sys.stderr.write(f"\n[ERROR] GET {path} failed:\n{fmt_response(resp)}\n")
        die(f"Aborting — GET {path} returned {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        die(f"GET {path} returned non-JSON:\n{fmt_response(resp)}")
    return {}  # unreachable


def list_ontologies(session: requests.Session, base: str) -> list[dict]:
    print("\n=== Step 1: list ontologies ===")
    payload = get_json(session, base, "/api/v2/ontologies")
    ontologies = payload.get("data", [])
    if not ontologies:
        die("Token authenticated but tenant returned zero ontologies.")
    for ont in ontologies:
        print(f"  - apiName:     {ont.get('apiName', '?')}")
        print(f"    displayName: {ont.get('displayName', '?')}")
        print(f"    rid:         {ont.get('rid', '?')}")
        if ont.get("description"):
            print(f"    description: {ont['description']}")
        print()
    return ontologies


def pick_ontology(ontologies: list[dict]) -> dict:
    if len(ontologies) == 1:
        chosen = ontologies[0]
        print(f"=> Only one ontology — using {chosen.get('displayName')!r} ({chosen.get('rid')})")
        return chosen
    matches: list[dict] = []
    for ont in ontologies:
        haystack = " ".join(
            str(ont.get(k, "")).lower() for k in ("apiName", "displayName", "description")
        )
        if any(hint in haystack for hint in ONTOLOGY_NAME_HINTS):
            matches.append(ont)
    if len(matches) == 1:
        chosen = matches[0]
        print(f"=> Hint match — using {chosen.get('displayName')!r} ({chosen.get('rid')})")
        return chosen
    if len(matches) > 1:
        die(
            f"Multiple ontologies matched name hints ({[m.get('displayName') for m in matches]}). "
            "Set FOUNDRY_ONTOLOGY_RID in .env to disambiguate."
        )
    die(
        "Multiple ontologies but none matched NatSec/Hackathon/OPSEC/Ghostline hints. "
        "Pick one above and set FOUNDRY_ONTOLOGY_RID in .env."
    )
    return {}  # unreachable


def list_object_types(session: requests.Session, base: str, ont_id: str) -> list[dict]:
    print(f"\n=== Step 2: list object types for ontology '{ont_id}' ===")
    types: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token
        payload = get_json(
            session, base, f"/api/v2/ontologies/{ont_id}/objectTypes", **params
        )
        types.extend(payload.get("data", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    if not types:
        print("  (no object types returned)")
        return types
    for ot in types:
        api_name = ot.get("apiName", "?")
        display = ot.get("displayName", "?")
        pk = ot.get("primaryKey", "?")
        props = ot.get("properties", {})
        print(f"  - {api_name:24s}  display={display!r:40s}  pk={pk}  props={len(props)}")
    return types


def check_expected(types: list[dict]) -> None:
    print("\n=== Step 3: expected vs found ===")
    found = {t.get("apiName") for t in types if t.get("apiName")}
    expected = set(EXPECTED_OBJECT_TYPES)
    missing = sorted(expected - found)
    extra_ghostline = sorted(n for n in (found - expected) if "ghostline" in (n or "").lower())
    if not missing:
        print(f"  OK: all {len(expected)} expected object types present.")
    else:
        print(f"  MISSING (expected but not found): {missing}")
        print("  -> If apiNames differ from our guess, update CLAUDE.md and the populator.")
    if extra_ghostline:
        print(f"  Extra Ghostline-prefixed types not in expected list: {extra_ghostline}")


def try_get_json(
    session: requests.Session, base: str, path: str, **params: Any
) -> tuple[dict | None, str | None]:
    """Non-fatal GET. Returns (json, None) on success, (None, error_message) on failure."""
    url = f"{base}{path}"
    try:
        resp = session.get(url, params=params or None, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not resp.ok:
        body = (resp.text or "")[:300]
        return None, f"HTTP {resp.status_code} {resp.reason} — {body}"
    try:
        return resp.json(), None
    except ValueError:
        return None, f"non-JSON body: {(resp.text or '')[:300]}"


def _norm_name(name: str) -> str:
    """Normalize an apiName for comparison across snake_case / kebab-case / camelCase."""
    return name.lower().replace("_", "").replace("-", "")


def find_property(properties: dict, target: str) -> str | None:
    """Match property apiName ignoring case and word separators.

    source_url == sourceUrl == source-url all collapse to 'sourceurl'.
    """
    target_norm = _norm_name(target)
    for name in properties:
        if _norm_name(name) == target_norm:
            return name
    return None


def fmt_dtype(dt: Any) -> str:
    if isinstance(dt, dict):
        kind = dt.get("type", "?")
        sub = dt.get("subType") or dt.get("itemType")
        if isinstance(sub, dict):
            return f"{kind}<{sub.get('type', '?')}>"
        return str(kind)
    return str(dt)


def step4_read_each(
    session: requests.Session, base: str, ont_id: str
) -> dict[str, bool]:
    print("\n=== Step 4: read each expected object type ===")
    results: dict[str, bool] = {}
    for type_name in EXPECTED_OBJECT_TYPES:
        body, err = try_get_json(
            session, base, f"/api/v2/ontologies/{ont_id}/objects/{type_name}", pageSize=1
        )
        if err is not None:
            print(f"  X  {type_name:24s}  {err}")
            results[type_name] = False
            continue
        n = len(body.get("data", []) if body else [])
        print(f"  OK {type_name:24s}  HTTP 200, {n} object(s) returned")
        results[type_name] = True
    return results


def step5_full_schema(
    session: requests.Session, base: str, ont_id: str
) -> dict[str, dict]:
    print("\n=== Step 5: full property schema + provenance check per type ===")
    schemas: dict[str, dict] = {}
    for type_name in EXPECTED_OBJECT_TYPES:
        print(f"\n  -- {type_name} --")
        data, err = try_get_json(
            session, base, f"/api/v2/ontologies/{ont_id}/objectTypes/{type_name}"
        )
        if err is not None or data is None:
            print(f"    [error] {err}")
            continue
        schemas[type_name] = data
        rid = data.get("rid", "?")
        pk = data.get("primaryKey", "?")
        props = data.get("properties", {}) or {}
        print(f"    rid:        {rid}")
        print(f"    primaryKey: {pk}")
        print(f"    propCount:  {len(props)}")
        expected_rid = EXPECTED_RIDS.get(type_name)
        if expected_rid and rid != expected_rid:
            print(f"    [WARN] RID mismatch — expected {expected_rid}")
        print(f"    properties:")
        for pname in sorted(props.keys()):
            kind = fmt_dtype(props[pname].get("dataType"))
            print(f"      - {pname:32s}  ({kind})")
        print(f"    provenance:")
        all_present = True
        for prop in PROVENANCE_PROPS:
            actual = find_property(props, prop)
            if actual:
                kind = fmt_dtype(props[actual].get("dataType"))
                print(f"      OK  {prop:14s}  -> {actual}  ({kind})")
            else:
                all_present = False
                print(f"      MISSING  {prop}")
        if all_present:
            print(f"    -> all 4 provenance properties present")
        else:
            print(f"    -> [WARN] not all provenance properties present")
    return schemas


def _fetch_links_for_type(
    session: requests.Session, base: str, ont_id: str, type_name: str
) -> tuple[list[dict] | None, str]:
    """Probe several known link-listing endpoint variants. Return (links, used_path)."""
    candidate_paths = [
        f"/api/v2/ontologies/{ont_id}/objectTypes/{type_name}/outgoingLinkTypes",
        f"/api/v2/ontologies/{ont_id}/objectTypes/{type_name}/linkTypes",
        f"/api/v1/ontologies/{ont_id}/objectTypes/{type_name}/outgoingLinkTypes",
        f"/api/v1/ontologies/{ont_id}/objectTypes/{type_name}/linkTypes",
    ]
    last_err = ""
    for path in candidate_paths:
        data, err = try_get_json(session, base, path)
        if err is None and data is not None:
            return data.get("data", []) or [], path
        last_err = err or "unknown error"
    return None, last_err


def step6_link_types(
    session: requests.Session, base: str, ont_id: str
) -> dict[str, list[dict]]:
    print("\n=== Step 6: link types per object type ===")
    found: dict[str, list[dict]] = {}
    used_endpoint: str | None = None
    for type_name in EXPECTED_OBJECT_TYPES:
        links, info = _fetch_links_for_type(session, base, ont_id, type_name)
        print(f"\n  -- {type_name} --")
        if links is None:
            print(f"    [error — all endpoint variants failed; last: {info}]")
            continue
        if used_endpoint is None:
            used_endpoint = info
            print(f"    (using endpoint {info})")
        found[type_name] = links
        if not links:
            print(f"    (no links defined on this object type)")
            continue
        for link in links:
            api = link.get("apiName", "?")
            target = (
                link.get("objectTypeApiName")
                or link.get("targetType")
                or link.get("linkedObjectTypeApiName")
                or link.get("targetObjectTypeApiName")
                or "?"
            )
            cardinality = link.get("cardinality") or link.get("cardinalityHint") or "?"
            print(f"    {api:24s} -> {target:24s} cardinality={cardinality}")

    # Foundry auto-generates link apiNames from the target type, not from our intended
    # name (`hosts_unit` etc. are gone). Match by (source, target) and surface the actual
    # apiName the populator/query API must call.
    print("\n  Expected (source -> target) vs found (using Foundry-generated apiNames):")
    for src, expected in EXPECTED_LINKS.items():
        if not expected:
            continue
        links_for_src = found.get(src, [])
        for intended_name, exp_target in expected:
            matches = []
            for link in links_for_src:
                actual_target = (
                    link.get("objectTypeApiName")
                    or link.get("targetType")
                    or link.get("linkedObjectTypeApiName")
                    or link.get("targetObjectTypeApiName")
                )
                if actual_target == exp_target:
                    matches.append(link)
            if not matches:
                print(f"    MISSING  {src} ->...-> {exp_target} (intended: {intended_name})")
                continue
            for m in matches:
                api = m.get("apiName")
                card = m.get("cardinality") or "?"
                print(
                    f"    OK       {src} -{api}-> {exp_target}  ({card})  "
                    f"[intended: {intended_name}]"
                )
    return found


def fetch_action_types(
    session: requests.Session, base: str, ont_id: str
) -> list[dict]:
    actions: list[dict] = []
    page_token: str | None = None
    while True:
        params: dict[str, Any] = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token
        data, err = try_get_json(
            session, base, f"/api/v2/ontologies/{ont_id}/actionTypes", **params
        )
        if err is not None or data is None:
            print(f"  [error fetching actionTypes] {err}")
            return actions
        actions.extend(data.get("data", []) or [])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return actions


def _camel_to_kebab(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def _action_creates(action: dict, object_type: str) -> tuple[bool, str]:
    """Return (matches, reason) — does this action create the given object type?"""
    ops = action.get("operations") or []
    if isinstance(ops, list):
        for op in ops:
            if not isinstance(op, dict):
                continue
            op_kind = (op.get("type") or op.get("operationType") or "").lower()
            obj = (
                op.get("objectType")
                or op.get("objectTypeApiName")
                or op.get("targetObjectType")
                or ""
            )
            if "create" in op_kind and obj == object_type:
                return True, f"operations[{op_kind}]"
    api = (action.get("apiName") or "").lower()
    display = (action.get("displayName") or "").lower()
    kebab = _camel_to_kebab(object_type)
    type_lower = object_type.lower()
    if api.startswith("create") and (kebab in api or type_lower in api.replace("-", "")):
        return True, "apiName-pattern"
    if display.startswith("create ") and type_lower in display.replace(" ", "").replace("-", ""):
        return True, "displayName-pattern"
    return False, ""


def step7_create_actions(
    session: requests.Session, base: str, ont_id: str
) -> dict[str, list[dict]]:
    print("\n=== Step 7: action types — discover create actions ===")
    actions = fetch_action_types(session, base, ont_id)
    print(f"  Total action types in ontology: {len(actions)}")

    create_map: dict[str, list[dict]] = {}
    for type_name in EXPECTED_OBJECT_TYPES:
        matches: list[tuple[dict, str]] = []
        for action in actions:
            ok, reason = _action_creates(action, type_name)
            if ok:
                matches.append((action, reason))
        create_map[type_name] = [m[0] for m in matches]
        print(f"\n  -- {type_name} --")
        if not matches:
            print(f"    [no create action found]")
            continue
        for action, reason in matches:
            api = action.get("apiName", "?")
            display = action.get("displayName", "?")
            params = action.get("parameters", {}) or {}
            print(f"    apiName:    {api}    (matched via {reason})")
            print(f"    display:    {display}")
            if action.get("description"):
                print(f"    desc:       {action['description']}")
            print(f"    parameters ({len(params)}):")
            param_names = set()
            for pname in sorted(params.keys()):
                meta = params[pname] or {}
                kind = fmt_dtype(meta.get("dataType"))
                req = meta.get("required", False)
                req_mark = "*" if req else " "
                print(f"      {req_mark} {pname:32s}  ({kind})")
                param_names.add(pname)
            # Provenance check on action params
            missing_prov = [
                p for p in PROVENANCE_PROPS if find_property(params, p) is None
            ]
            if missing_prov:
                print(f"    [WARN] action params missing provenance: {missing_prov}")
            else:
                print(f"    -> action params include all 4 provenance fields")
    return create_map


def populator_summary(
    create_map: dict[str, list[dict]],
    read_results: dict[str, bool],
) -> None:
    print("\n=== Populator-ready map ===")
    print("  ObjectType -> create-action apiName (the populator must call this)")
    for type_name in EXPECTED_OBJECT_TYPES:
        readable = read_results.get(type_name, False)
        matches = create_map.get(type_name, [])
        read_mark = "read=OK " if readable else "read=FAIL"
        if not matches:
            print(f"    [{read_mark}] {type_name:24s}  -> NO CREATE ACTION")
        elif len(matches) == 1:
            print(f"    [{read_mark}] {type_name:24s}  -> {matches[0].get('apiName')}")
        else:
            apis = [m.get("apiName") for m in matches]
            print(f"    [{read_mark}] {type_name:24s}  -> AMBIGUOUS: {apis}")


def main() -> int:
    token_raw = os.getenv("FOUNDRY_TOKEN") or ""
    hostname_raw = os.getenv("FOUNDRY_HOSTNAME") or ""
    if not token_raw.strip():
        die(f"FOUNDRY_TOKEN missing from .env (project-root .env at {ROOT / '.env'})")
    if not hostname_raw.strip():
        die("FOUNDRY_HOSTNAME missing from .env")
    token = unwrap(token_raw)
    if token != token_raw.strip():
        print("[note] FOUNDRY_TOKEN had wrapping characters (<>, quotes) — stripped. "
              "Clean them up in .env so other code doesn't trip on this.")
    hostname = normalize_hostname(hostname_raw)
    base = f"https://{hostname}"
    print(f"Host:         {base}")
    print(f"Token prefix: {token[:6]}...  (length {len(token)})")

    existing_rid = (os.getenv("FOUNDRY_ONTOLOGY_RID") or "").strip()
    if existing_rid:
        print(f"FOUNDRY_ONTOLOGY_RID already in .env: {existing_rid}")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })

    ontologies = list_ontologies(session, base)
    chosen = pick_ontology(ontologies)
    rid = chosen.get("rid") or ""
    api_name = chosen.get("apiName") or ""
    ont_id = api_name or rid
    if not ont_id:
        die("Selected ontology has neither apiName nor rid.")

    if existing_rid and existing_rid != rid:
        print(
            f"\n[WARN] FOUNDRY_ONTOLOGY_RID in .env ({existing_rid}) does not match "
            f"discovered RID ({rid}). Update .env."
        )

    types = list_object_types(session, base, ont_id)
    check_expected(types)
    read_results = step4_read_each(session, base, ont_id)
    step5_full_schema(session, base, ont_id)
    step6_link_types(session, base, ont_id)
    create_map = step7_create_actions(session, base, ont_id)
    populator_summary(create_map, read_results)

    print("\n=== Done ===")
    print(f"  Ontology apiName: {api_name}")
    print(f"  Ontology RID:     {rid}")
    print(f"  Object type count: {len(types)}")
    print()
    print("  Add to .env if not already present:")
    print(f"    FOUNDRY_ONTOLOGY_RID={rid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
