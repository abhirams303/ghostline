"""GHOSTLINE Sensor populator — extends the chain one link beyond Platform.

For every GhostlinePlatform in Foundry, fetches the relevant Wikipedia
infobox and creates GhostlineSensor objects for the radar / sonar / EW /
comms / FLIR systems mounted on it.

Naming reality: most of our platform names are hull numbers (DDG-81,
CVN-75) which don't have direct Wikipedia pages. We fall back to the
class-level article ("Arleigh Burke-class destroyer", "Nimitz-class
aircraft carrier") whose infobox carries the canonical sensor list.
Each hull gets its own GhostlineSensor instances with the class-level
names but a unique mountedOnId — that's correct schema use, not
duplication.

We deliberately filter OUT munitions (AIM-9, AGM-65, JDAM, Mk-83 bombs,
torpedoes, gun calibres) — they appear in `armament` infobox fields but
they're not sensors. GhostlineSensor is for sensing/EW/comms only.

Idempotent on sensor_id = "sens_{sensor-slug}__{platform-pk-short}".

Run:
    python -m backend.ai.sensor_populator --dry-run
    python -m backend.ai.sensor_populator
    python -m backend.ai.sensor_populator --platform DDG-81
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import osint_sources
from .palantir_integration import ACTIONS, FoundryClient, FoundryError

log = logging.getLogger("ghostline.sensors")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_ROOT = REPO_ROOT / "backend" / "ai" / "cached_osint" / "sensors"

MAX_SENSORS_PER_PLATFORM = 8  # Cap so a single noisy infobox can't flood the ontology.

# Hull-number prefixes -> class-level Wikipedia article. Used as fallback when
# the bare hull number doesn't resolve to a Wikipedia article.
PLATFORM_CLASS_FALLBACKS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^DDG-\d", re.I), "Arleigh Burke-class destroyer"),
    (re.compile(r"^CVN-\d", re.I), "Nimitz-class aircraft carrier"),
    (re.compile(r"^CG-\d", re.I), "Ticonderoga-class cruiser"),
    (re.compile(r"^SSN-\d", re.I), "Virginia-class submarine"),
    (re.compile(r"^LHA-\d", re.I), "America-class amphibious assault ship"),
    (re.compile(r"^LHD-\d", re.I), "Wasp-class amphibious assault ship"),
    (re.compile(r"^LPD-\d", re.I), "San Antonio-class amphibious transport dock"),
    (re.compile(r"^FFG-\d", re.I), "Constellation-class frigate"),
]

# Infobox field-name fragments whose values are likely to contain sensors.
SENSOR_FIELD_KEYWORDS = (
    "sensor", "ew_and_decoy", "ew", "electronic_warfare", "electronic warfare",
    "electronic_countermeasure", "electronics", "ecm", "avionics", "radar",
    "sonar", "fire_control", "fire control", "countermeasure", "weapon_system",
    "weapons_system", "weapon systems", "weapons systems",
)

# Items whose names match these patterns are sensors / EW / comms.
_SENSOR_NAME_PATTERNS: list[re.Pattern[str]] = [
    # AN/ designators — US military gold standard.
    re.compile(r"\bAN/[ASMU][PSL][PYQRSGTKN]-\d", re.I),  # AN/APG-, AN/SPY-, AN/SLQ-, etc.
    re.compile(r"\bAN/AAQ-\d", re.I),                     # FLIR / IR
    re.compile(r"\bAN/SQ[QSR]-\d", re.I),                 # naval sonar
    re.compile(r"\bAN/W[LQ][RNSC]-\d", re.I),             # ESM / ELINT
    re.compile(r"\bAN/U[YS][KCQ]-\d", re.I),              # data links / UPX/UYK
    # Generic system names.
    re.compile(r"\bradar\b", re.I),
    re.compile(r"\bsonar\b", re.I),
    re.compile(r"\bFLIR\b", re.I),
    re.compile(r"\bIRST\b", re.I),                        # Infrared Search and Track
    re.compile(r"\bECM\b", re.I),
    re.compile(r"\bELINT\b", re.I),
    re.compile(r"\bSIGINT\b", re.I),
    re.compile(r"\bjammer\b", re.I),
    re.compile(r"\bsearch radar\b", re.I),
    re.compile(r"\bfire[- ]control\b", re.I),
    re.compile(r"\btargeting pod\b", re.I),
    re.compile(r"\bdata[- ]link\b", re.I),
    re.compile(r"\bSATCOM\b", re.I),
    re.compile(r"\b[Ll]ink[ -]?(?:1[16]|22)\b"),           # Link 11/16/22
    re.compile(r"\b(Aegis|Phalanx|Sea ?Sparrow)\b", re.I), # Combat / sensor systems
    re.compile(r"\bdecoy\b", re.I),
]

# Items matching these are munitions, not sensors. Reject hard.
_WEAPON_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(AIM|AGM|MIM|RIM|UGM|RGM|SM-?|RUM|GBU|JDAM|JSOW|HARM|"
               r"AMRAAM|Sidewinder|Tomahawk|Hellfire|Mk[ .-]?\d+|"
               r"BGM|ASROC|Standard Missile)", re.I),
    re.compile(r"\b(missile|torpedo|bomb|mine|warhead|munition|"
               r"shell|round|cartridge|grenade)\b", re.I),
    re.compile(r"\b\d+\s*mm\b", re.I),                    # 25mm, 127mm gun
    re.compile(r"\b(machine ?gun|cannon|howitzer)\b", re.I),
]

# IDs / subtypes for sensor_type classification.
_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sonar|AN/SQ[QSR]-", re.I), "sonar"),
    (re.compile(r"FLIR|infrared|thermal|AN/AAQ-", re.I), "ir"),
    (re.compile(r"ECM|jammer|countermeasure|AN/[AS]LQ-", re.I), "ecm"),
    (re.compile(r"ELINT|ESM|SIGINT|AN/[ASW][LR][RNQ]-|warning receiver", re.I), "ew"),
    (re.compile(r"radar|AN/A?P[GYQ]-|AN/SPY|AN/SPS|AN/SPQ|AN/MPQ", re.I), "radar"),
    (re.compile(r"data ?link|link[ -]?(1[16]|22)|tactical link", re.I), "data_link"),
    (re.compile(r"SATCOM|satellite ?communic|comms", re.I), "communications"),
    (re.compile(r"GPS|navigation|inertial|INS\b", re.I), "navigation"),
    (re.compile(r"targeting", re.I), "targeting"),
    (re.compile(r"Aegis|combat system", re.I), "combat_system"),
    (re.compile(r"decoy", re.I), "decoy"),
]


def _looks_like_sensor(name: str) -> bool:
    n = name.strip()
    if not n or len(n) > 120:
        return False
    # Reject fragments with unbalanced parens / brackets — they're typically
    # comma-split debris from prose like "[[AN/SPY-1D|SPY-1D]] (Flight I)".
    if n.count("(") != n.count(")") or n.count("[") != n.count("]"):
        return False
    # Reject fragments that start with a non-letter / non-digit (often a stray
    # piece of punctuation left over after splitting).
    if not n[:1].isalnum():
        return False
    if any(p.search(n) for p in _WEAPON_NAME_PATTERNS):
        return False
    return any(p.search(n) for p in _SENSOR_NAME_PATTERNS)


def _infer_sensor_type(name: str) -> str:
    for pat, label in _TYPE_RULES:
        if pat.search(name):
            return label
    return "sensor"


# ---------------------------------------------------------------------------
# Wikipedia title resolution (per-platform)
# ---------------------------------------------------------------------------

def candidate_wiki_titles(platform_name: str) -> list[str]:
    """Returns the list of Wikipedia titles to try, in priority order."""
    titles: list[str] = [platform_name.replace(" ", "_")]
    for pat, class_title in PLATFORM_CLASS_FALLBACKS:
        if pat.match(platform_name):
            class_t = class_title.replace(" ", "_")
            if class_t not in titles:
                titles.append(class_t)
            break
    return titles


def fetch_platform_wikitext(platform_name: str, cache_dir: Path) -> tuple[str, str, str] | None:
    """Returns (title_used, page_url, wikitext) or None if all candidates fail.

    Skips redirect stubs (short wikitext starting with #REDIRECT)."""
    for title in candidate_wiki_titles(platform_name):
        parse = osint_sources.wikipedia_parse(title, cache_dir)
        if parse is None:
            continue
        wt = parse.get("wikitext") or ""
        if len(wt) < 1000 and re.match(r"^\s*#redirect", wt, re.IGNORECASE):
            log.info("wiki parse for %s is a redirect; trying next candidate", title)
            continue
        return title, parse.get("page_url") or "", wt
    return None


# ---------------------------------------------------------------------------
# Wikitext infobox parsing
# ---------------------------------------------------------------------------

def _extract_infoboxes(wikitext: str) -> list[str]:
    """Return the body of EVERY {{Infobox …}} template in the wikitext.

    Many Wikipedia ship/aircraft articles use nested infoboxes (e.g.
    `{{Infobox ship | section3={{Infobox ship/characteristics | sensors=… }} }}`)
    so we can't just grab the first one — the sensors live in the nested
    sub-template. Iterating all templates and aggregating fields handles
    both flat and nested layouts."""
    bodies: list[str] = []
    for m in re.finditer(r"\{\{\s*Infobox\b", wikitext, re.IGNORECASE):
        start_body = m.end()
        depth = 1
        i = start_body
        while i < len(wikitext) and depth > 0:
            if wikitext[i:i + 2] == "{{":
                depth += 1
                i += 2
            elif wikitext[i:i + 2] == "}}":
                depth -= 1
                i += 2
            else:
                i += 1
        if depth == 0:
            bodies.append(wikitext[start_body:i - 2])
    return bodies


def _split_infobox_fields(infobox_body: str) -> list[tuple[str, str]]:
    """Split into (key, value) pairs. Handles multi-line values terminated by `\\n|` at depth 0."""
    fields: list[tuple[str, str]] = []
    depth = 0
    current_start = 0
    pending_pipe_idx: int | None = None
    text = infobox_body
    i = 0
    while i < len(text):
        ch = text[i]
        if text[i:i + 2] == "{{" or text[i:i + 2] == "[[":
            depth += 1
            i += 2
            continue
        if text[i:i + 2] == "}}" or text[i:i + 2] == "]]":
            depth -= 1
            i += 2
            continue
        if ch == "|" and depth == 0:
            if pending_pipe_idx is not None:
                # Close out the previous field.
                segment = text[pending_pipe_idx + 1:i]
                kv = segment.split("=", 1)
                if len(kv) == 2:
                    fields.append((kv[0].strip().lower(), kv[1].strip()))
            pending_pipe_idx = i
        i += 1
    # Trailing field (no terminating pipe — runs to end of body).
    if pending_pipe_idx is not None:
        segment = text[pending_pipe_idx + 1:]
        kv = segment.split("=", 1)
        if len(kv) == 2:
            fields.append((kv[0].strip().lower(), kv[1].strip()))
    return fields


def _candidates_from_value(value: str) -> list[str]:
    """Extract candidate item names from an infobox field value.

    Pulls wikilink targets, then plaintext bullet items. Strips templates."""
    out: list[str] = []
    seen: set[str] = set()

    # Wikilinks: [[Target]] or [[Target|Display]] -> use Target.
    for raw in re.findall(r"\[\[([^\]\|]+)(?:\|[^\]]*)?\]\]", value):
        name = raw.strip().split("#")[0].strip()
        if name and name.lower() not in seen and not name.lower().startswith(("file:", "image:", "category:")):
            seen.add(name.lower())
            out.append(name)

    # Strip {{...}} templates and remaining wikilinks for plaintext scan.
    cleaned = re.sub(r"\{\{[^}]*\}\}", " ", value)
    cleaned = re.sub(r"\[\[[^\]]*\]\]", " ", cleaned)
    for line in cleaned.splitlines():
        item = line.strip().lstrip("*#:").strip()
        item = re.sub(r"<[^>]+>", " ", item).strip()        # drop HTML
        item = re.sub(r"<!--.*?-->", " ", item).strip()     # drop wiki comments
        if not item:
            continue
        # Items often look like "AN/SPY-1D radar". We accept the whole line if
        # it matches a sensor pattern, but trim trailing parentheticals or
        # comma-tails that turn a single sensor into a comma-soup.
        for chunk in re.split(r",| / ", item):
            chunk = chunk.strip()
            if 0 < len(chunk) <= 120 and chunk.lower() not in seen:
                seen.add(chunk.lower())
                out.append(chunk)
    return out


def _add_candidate(out: list[tuple[str, str]], seen: set[str], name: str) -> None:
    key = name.lower()
    if key in seen:
        return
    if _looks_like_sensor(name):
        seen.add(key)
        out.append((name, "high"))


# Templates we should never recurse into (formatting helpers, not sensor lists).
_TEMPLATE_BLACKLIST = (
    "convert", "plain list", "plainlist", "ubl", "unbulleted list",
    "cite ", "cn", "citation needed", "ref",
)


def _is_recursable_template(template_name: str) -> bool:
    n = template_name.strip().lower()
    if not n or len(n) < 3:
        return False
    return not any(n.startswith(b) for b in _TEMPLATE_BLACKLIST)


def extract_sensors_from_wikitext(
    wikitext: str,
    fetch_template: "callable | None" = None,
) -> list[tuple[str, str]]:
    """Returns [(name, confidence)]. Confidence is 'high' (infobox-derived).

    Walks every {{Infobox …}} template (including nested ones) and pulls
    sensor-eligible items from any field whose key matches SENSOR_FIELD_KEYWORDS.
    If `fetch_template(name) -> wikitext` is provided, also follows
    transcluded sub-templates inside sensor fields — e.g. the Arleigh
    Burke article transcludes `{{Arleigh Burke-class destroyer sensors}}`.

    Weapons / munitions / gun calibres are dropped by _looks_like_sensor."""
    bodies = _extract_infoboxes(wikitext)
    if not bodies:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for body in bodies:
        for key, value in _split_infobox_fields(body):
            if not any(kw in key for kw in SENSOR_FIELD_KEYWORDS):
                continue
            # Direct candidates from this field's value.
            for cand in _candidates_from_value(value):
                _add_candidate(out, seen, cand)
            # Follow transcluded sub-templates if a fetcher is provided.
            if fetch_template is None:
                continue
            for m in re.finditer(r"\{\{\s*([^|}\n]+?)\s*(?:\}\}|\|)", value):
                tname = m.group(1).strip()
                if not _is_recursable_template(tname):
                    continue
                template_wt = fetch_template(tname)
                if not template_wt:
                    continue
                for cand in _candidates_from_value(template_wt):
                    _add_candidate(out, seen, cand)
    return out


# ---------------------------------------------------------------------------
# IDs + write
# ---------------------------------------------------------------------------

def sensor_id_for(platform_id: str, sensor_name: str) -> str:
    sensor_slug = osint_sources.slugify(sensor_name).replace("-", "_")[:40]
    plat_short = platform_id.replace("plat_", "")[:40]
    return f"sens_{sensor_slug}__{plat_short}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_sensor(
    client: FoundryClient | None,
    params: dict[str, Any],
    *,
    dry_run: bool,
) -> str:
    sid = params["sensor-id"]
    if dry_run:
        print(f"  [DRY] GhostlineSensor[{sid}]")
        print(f"        name:         {params['name']}")
        print(f"        sensor_type:  {params['sensor-type']}")
        print(f"        mounted_on:   {params['mounted-on-id']}")
        print(f"        source_url:   {params['source-url']}")
        return "dry-run"

    assert client is not None
    try:
        existing = client.get_object("GhostlineSensor", sid)
    except FoundryError as exc:
        log.warning("idempotency check failed for %s: %s", sid, exc)
        existing = None
    if existing is not None:
        return "exists"

    try:
        client.apply_action(ACTIONS["GhostlineSensor"], params)
    except FoundryError as exc:
        log.error("create GhostlineSensor[%s] failed: %s", sid, exc)
        return "failed"

    try:
        readback = client.get_object("GhostlineSensor", sid)
    except FoundryError as exc:
        log.error("read-back GhostlineSensor[%s] failed: %s", sid, exc)
        return "failed"
    if readback is None:
        log.error("WROTE BUT VANISHED: GhostlineSensor[%s]", sid)
        return "failed"

    log.info("created GhostlineSensor[%s] (mounted on %s)", sid, params["mounted-on-id"])
    return "created"


# ---------------------------------------------------------------------------
# Per-platform pipeline
# ---------------------------------------------------------------------------

def populate_platform(
    client: FoundryClient | None,
    platform: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, int]:
    counts = {"created": 0, "exists": 0, "failed": 0, "dry-run": 0}
    plat_id = platform.get("platformId")
    plat_name = platform.get("name") or ""
    if not plat_id or not plat_name:
        return counts

    cache_dir = CACHE_ROOT / plat_id
    fetched = fetch_platform_wikitext(plat_name, cache_dir)
    if fetched is None:
        log.info("no Wikipedia article found for platform %s (%s)", plat_name, plat_id)
        return counts
    title_used, page_url, wikitext = fetched

    def _fetch_template(tname: str) -> str | None:
        title = "Template:" + tname.replace(" ", "_")
        parse = osint_sources.wikipedia_parse(title, cache_dir)
        if parse is None:
            return None
        return parse.get("wikitext")

    sensors = extract_sensors_from_wikitext(wikitext, fetch_template=_fetch_template)
    if not sensors:
        log.info("no sensors extracted for %s (via %s)", plat_name, title_used)
        return counts

    print(f"  {plat_name} ({plat_id})  via Wikipedia '{title_used}'  -> {len(sensors)} sensor candidate(s)")
    for sensor_name, confidence in sensors[:MAX_SENSORS_PER_PLATFORM]:
        params = {
            "sensor-id": sensor_id_for(plat_id, sensor_name),
            "name": sensor_name[:200],
            "sensor-type": _infer_sensor_type(sensor_name),
            "mounted-on-id": plat_id,
            "source-url": page_url or f"https://en.wikipedia.org/wiki/{title_used}",
            "retrieved-at": _now_iso(),
            "source-type": "wikipedia",
            "confidence": confidence,
        }
        result = write_sensor(client, params, dry_run=dry_run)
        counts[result] = counts.get(result, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Populate GhostlineSensor objects from Wikipedia.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--platform", action="append", default=[],
                   help="Limit to this platform name or ID (repeatable). Default: all.")
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    try:
        client = FoundryClient() if not args.dry_run else None
        if client is None:
            # Even in dry-run we need to read platforms.
            client = FoundryClient()
    except FoundryError as exc:
        print(f"Foundry config error: {exc}")
        return 2

    try:
        platforms = client.list_objects("GhostlinePlatform", page_size=200)
    except FoundryError as exc:
        print(f"list GhostlinePlatform failed: {exc}")
        return 2

    if args.platform:
        wanted = {p.lower() for p in args.platform}
        platforms = [
            p for p in platforms
            if (p.get("name") or "").lower() in wanted or (p.get("platformId") or "").lower() in wanted
        ]
        if not platforms:
            print(f"No platforms matched {sorted(wanted)}")
            return 0

    foundry_client_for_writes = None if args.dry_run else client
    totals = {"created": 0, "exists": 0, "failed": 0, "dry-run": 0}
    platforms_with_sensors = 0
    print(f"\n=== Populating sensors for {len(platforms)} platform(s) ===")
    for plat in platforms:
        counts = populate_platform(foundry_client_for_writes, plat, dry_run=args.dry_run)
        wrote = counts["created"] + counts["dry-run"]
        if wrote > 0:
            platforms_with_sensors += 1
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v

    print("\n=== Sensor population summary ===")
    print(f"  {totals}")
    added = totals["created"] + totals["dry-run"]
    print(f"  Added {added} sensors across {platforms_with_sensors} platforms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
