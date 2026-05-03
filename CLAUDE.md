# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: GHOSTLINE

OPSEC self-assessment tool for the National Security Hackathon. The goal is a Palantir Foundry-native intelligence backbone — not a UI, not a chatbot. A teammate is building a Pipecat voice agent in parallel that will eventually call our query API; our job is the data backbone, not the voice agent.

The legacy `OPSEC Mirror` FastAPI scaffold (`backend/app/`, `frontend/`) predates this direction. Treat it as reference material — reuse what is useful, but new work happens in `backend/ai/` and `scripts/`. We are on the `voice-agent` branch; do not push broken code to `main`.

## Architecture (three layers)

1. **Populated ontology** — `GhostlineGeoFeature`, `GhostlineUnit`, `GhostlinePlatform`, `GhostlineSensor`, `GhostlineCommsAsset` written into Foundry from real OSINT, with provenance metadata on every object.
2. **Pre-computed cascade analyses** — AI agents (Cascade Analyst, Adversary Modeler) read the populated ontology and write `CascadeRisk` and `AdversaryAction` objects back into it.
3. **Realtime enrichment** — lat/lon-keyed live data layer (ADS-B, Shodan, satellite passes, news) queried at request time, not pre-stored.

Build order, current focus:

1. `scripts/test_foundry.py` — verify Bearer token, discover ontology RID
2. `backend/ai/osint_populator.py` — populate `GhostlineGeoFeature`, `GhostlineUnit`, `GhostlinePlatform`, `GhostlineSensor`, `GhostlineCommsAsset` from real OSINT
3. `backend/ai/realtime_enrichment.py` — lat/lon-keyed live queries
4. `backend/ai/cascade_analyst.py` — read populated ontology, write `CascadeRisk` objects (use `chain_entities` array for compromised unit IDs, **not** a link to Unit)
5. `backend/ai/adversary_modeler.py` — read `CascadeRisk` objects, write `AdversaryAction` objects
6. `backend/ai/query_api.py` — clean Python query functions for any consumer (the Pipecat agent is the first one)

## Target Locations (locked)

These are the 5 locations we populate and analyze. Locked in — don't add or remove without asking.

1. Fort Liberty, NC (35.139, -78.997) — try "Fort Liberty" first, fall back to "Fort Bragg" for Wikipedia lookups
2. Naval Station Norfolk, VA (36.9466, -76.3013)
3. Joint Base Lewis-McChord, WA (47.0876, -122.5726)
4. Naval Base San Diego, CA (32.6839, -117.1286)
5. Shack15, San Francisco, CA (37.7955, -122.3937) — civilian venue, only the Geo Feature gets populated, no military entities

If cached data exists for other locations, ignore them unless explicitly asked. What's actually on disk in `backend/data/cached/` today: `creech_afb.json`, `fort_liberty.json`, `norfolk_naval.json`, plus `strava_samples/` for area51, fort_liberty, norfolk, ocean_control, san_francisco. Of the locked targets, only Fort Liberty and Norfolk have top-level cached samples; the other three (JBLM, San Diego, Shack15) need fresh OSINT pulls.

## Palantir Foundry

**Source of truth for action and link apiNames: `scripts/test_foundry.py`.** Run it (or read the constants in `backend/ai/palantir_integration.py`) before writing any new ontology-touching code. Foundry auto-generates these names in non-obvious ways — do NOT invent names from intuition or copy them from chat. The action map and link tables below are mirrored from that script's verified output; if they ever disagree, the script wins and CLAUDE.md needs an update.

- Hostname: `nshackathon.palantirfoundry.com` (env var: `FOUNDRY_HOSTNAME`)
- Auth: Bearer token via `FOUNDRY_TOKEN` — **NOT OAuth**. Send `Authorization: Bearer $FOUNDRY_TOKEN` on REST calls. The legacy stub at `backend/ai/palantir_integration.py` references an OSDK + ConfidentialClientAuth flow; ignore that for the new write path.
- Ontology: "NatSec Hackathon Ontology"
  - apiName: `ontology-57308d1b-c039-44ef-9dbe-196eb41a717c`
  - RID: `ri.ontology.main.ontology.41fccd0c-2180-4c1d-841d-8a488d1abb46` (set as `FOUNDRY_ONTOLOGY_RID`)
- Object types we own: `GhostlineGeoFeature`, `GhostlineUnit`, `GhostlinePlatform`, `GhostlineSensor`, `GhostlineCommsAsset`, `CascadeRisk`, `AdversaryAction`, plus the pre-existing `OpsecAssessment`. **Do not modify object type schemas** — they are locked in.
- The ontology also contains 20 `Example*` types (ExampleAircraft, ExampleUnit, etc.) owned by the hackathon organizers. We can't add provenance properties to those, which is why we built parallel `Ghostline*` types. Ignore the `Example*` types unless we explicitly need to read from them.
- Every Ghostline* / CascadeRisk / AdversaryAction object has provenance properties: `source_url`, `retrieved_at`, `source_type`, `confidence`. These are non-negotiable on every entity we create.
- Link types (deployed on the default branch):
  - `GhostlineGeoFeature -hosts_unit-> GhostlineUnit`
  - `GhostlineUnit -operates-> GhostlinePlatform`
  - `GhostlinePlatform -carries-> GhostlineSensor`
  - `GhostlineGeoFeature -has_comms-> GhostlineCommsAsset`
  - `CascadeRisk -analyzed_from-> OpsecAssessment`
  - `CascadeRisk -located_at-> GhostlineGeoFeature`
  - `AdversaryAction -responds_to-> CascadeRisk`
- **No `CascadeRisk -> Unit` link.** A many-to-many CascadeRisk-to-Unit link was intentionally skipped; instead `CascadeRisk` carries a `chain_entities` string array of compromised unit IDs (and other entity IDs in the cascade chain). Cascade Analyst writes into that array; query consumers read it. Don't try to traverse via a link that doesn't exist.

### Foundry object type RIDs

```
GhostlineGeoFeature   ri.ontology.main.object-type.f502f6e7-9188-4382-a1d2-d1f8347e9888
GhostlineUnit         ri.ontology.main.object-type.1840f19e-3617-480f-9ac6-abbf8e46d7c1
GhostlinePlatform     ri.ontology.main.object-type.b2ca81c6-1920-414e-876b-c0d75beb7e25
GhostlineSensor       ri.ontology.main.object-type.3b0b2a70-951b-4ba4-bc25-430619a34023
GhostlineCommsAsset   ri.ontology.main.object-type.988dfc5c-6f76-45fd-a8a8-9daa87dbf737
CascadeRisk           ri.ontology.main.object-type.37960cfc-5161-407a-a37f-3f796d85a4f2
AdversaryAction       ri.ontology.main.object-type.1d027012-9068-4930-93bb-98b00a1abe1b
OpsecAssessment       ri.ontology.main.object-type.a1d788a7-2fcc-44c2-bab3-b91caaba7dae
```

### Naming conventions (verified against the live tenant)

Foundry generated different naming styles for properties vs action parameters vs links. Memorize this — the populator must use both:

- **Property apiNames are camelCase**: `sourceUrl`, `retrievedAt`, `sourceType`, `confidence`, `featureId`, `unitId`, `chainEntities`, etc. This is what you get back when you read objects.
- **Action parameter names are kebab-case**: `source-url`, `retrieved-at`, `source-type`, `confidence`, `feature-id`, `chain-entities`, etc. This is what you must send when calling create-actions.
- **Required action params (the only ones marked `*` in step 7 output):** primary-key field + `name` for most types (e.g., `feature-id` and `name` for GhostlineGeoFeature). Everything else is optional from Foundry's POV but provenance is non-negotiable from ours.

### Create-action map (apiName per type)

```
GhostlineGeoFeature   -> create-ghostline-geo-feature
GhostlineUnit         -> create-ghostline-unit
GhostlinePlatform     -> create-ghostline-platform
GhostlineSensor       -> create-ghostline-sensor
GhostlineCommsAsset   -> create-ghostline-comms-asset
CascadeRisk           -> create-cascade-risk
AdversaryAction       -> create-adversary-action
OpsecAssessment       -> create-opsec-assessment
```

Invoke via `POST /api/v2/ontologies/{ont}/actions/{action-apiName}/apply` with `{"parameters": {"source-url": "...", ...}}`.

### Link apiNames (Foundry-generated, NOT our intended names)

Foundry auto-generated link apiNames based on the linked type, ignoring the human names from the design spec. The "intended" column is for humans reading the architecture; the "apiName" column is what you must put in the URL when querying linked objects.

**Forward direction (the side that points to a single target):**

| Source              | apiName                  | Target              | Card | Intended      |
| ------------------- | ------------------------ | ------------------- | ---- | ------------- |
| GhostlineUnit       | `geoFeature`             | GhostlineGeoFeature | ONE  | hosts_unit    |
| GhostlineCommsAsset | `geoFeature`             | GhostlineGeoFeature | ONE  | has_comms     |
| GhostlinePlatform   | `platforms`              | GhostlineUnit       | ONE  | operates      |
| GhostlineSensor     | `sensors`                | GhostlinePlatform   | ONE  | carries       |
| CascadeRisk         | `cascadeRisks`           | GhostlineGeoFeature | ONE  | located_at    |
| CascadeRisk         | `analyzedCascadeRisks`   | OpsecAssessment     | ONE  | analyzed_from |
| AdversaryAction     | `adversaryActions`       | CascadeRisk         | ONE  | responds_to   |

**Reverse direction (collection — fan out from a parent):**

| Source              | apiName            | Target              | Card |
| ------------------- | ------------------ | ------------------- | ---- |
| GhostlineGeoFeature | `units`            | GhostlineUnit       | MANY |
| GhostlineGeoFeature | `commsAssets`      | GhostlineCommsAsset | MANY |
| GhostlineGeoFeature | `geoFeature`       | CascadeRisk         | MANY |
| GhostlineUnit       | `unit`             | GhostlinePlatform   | MANY |
| GhostlinePlatform   | `platform`         | GhostlineSensor     | MANY |
| CascadeRisk         | `cascadeRisk`      | AdversaryAction     | MANY |
| OpsecAssessment     | `opsecAssessment`  | CascadeRisk         | MANY |

The naming is unintuitive (e.g., `OpsecAssessment.opsecAssessment` returns CascadeRisks). Don't try to reason about it — just look it up here.

### Provenance exception: OpsecAssessment

`OpsecAssessment` is the only object type without `sourceUrl/retrievedAt/sourceType/confidence`. It's a synthesized summary (10 props: location, exposureScore, threatBrief, etc.) — provenance lives on the upstream Ghostline* entities and CascadeRisk objects that feed into it. Do **not** try to pass `source-url` etc. to `create-opsec-assessment`; the action will reject them.

## OSINT data sources

All real, all public, all attributable. Never fabricate data — every entity in Palantir must trace back to a real source URL.

- OpenStreetMap Nominatim — geocoding (no key)
- Wikipedia REST API — base/unit infobox data
- Wikidata SPARQL — structured military data
- Exa.ai — semantic search for OSINT gaps (`EXA_API_KEY`)
- OpenStreetMap Overpass API — base perimeters and features
- ADS-B Exchange — live military aircraft (`ADSB_API_KEY`)
- Shodan — exposed infrastructure
- CelesTrak TLE — satellite orbit data

## Repo structure (what's relevant for new work)

- `backend/ai/` — where new modules live. Existing files are from the earlier architecture — see "Existing modules: reuse decisions" below.
- `backend/data/cached/` — cached OSINT samples (Fort Liberty, Norfolk Naval, Creech AFB). Cache raw API responses here for audit and replay.
- `scripts/` — one-off scripts (`test_foundry.py` lives here).
- `backend/app/` — legacy `OPSEC Mirror` FastAPI scaffold (collectors, synthesis, SQLite, SSE). Don't extend it.
- `backend/ai/voice_server.py` — the **only** sanctioned HTTP surface for cross-team consumers (Pipecat voice agent + deck.gl frontend). Thin FastAPI wrapper over `query_api` / `realtime_enrichment` — all real logic lives in the underlying Python modules; this file is transport only. Add new endpoints here if (and only if) cross-team consumers need them; don't add them to `backend/app/`.

## Existing modules: reuse decisions

- `threat_brief.py` — **REUSE.** The LLM threat brief generator. Cascade Analyst will call into it with cascade context.
- `score_calculator.py` — **REUSE.** The weighted exposure score formula is fine.
- `mitigation_engine.py` — **REUSE.** Cascade Analyst will use its mitigation outputs as alternatives to the upstream cascade mitigation.
- `pipeline.py` — **REUSE PARTIALLY.** The orchestrator pattern is good, but the Palantir write call needs to be updated to use the Bearer token approach.
- `palantir_integration.py` — **REPLACE.** The OSDK / `ConfidentialClientAuth` approach is wrong, and it reads `FOUNDRY_HOST` instead of `FOUNDRY_HOSTNAME`. Replace with simple Bearer token REST calls reading `FOUNDRY_HOSTNAME`.
- `strava_analyzer.py`, `adsb_analyzer.py`, `satellite_analyzer.py` — **KEEP.** They produce the per-layer scores that feed into OPSEC Assessment writes. Don't delete.

## Common commands

```bash
# Backend install (editable)
cd backend && python -m pip install -e .[dev]

# Backend tests
cd backend && python -m pytest
cd backend && python -m pytest tests/test_collectors.py::test_name  # single test

# Run a one-off ai module test harness
python -m backend.ai.test_all

# Legacy scaffold (only if you need to touch it)
pnpm dev            # runs frontend + backend together
pnpm dev:backend    # uvicorn app.main:app --reload --app-dir backend
pnpm dev:frontend
pnpm lint && pnpm build
```

## Coding conventions

- Python 3.11+
- Use ultrathink for complex modules (image processing, multi-source data fusion, agent prompts)
- Spawn subagents when modules are independent and can be built in parallel
- Always add a `--dry-run` mode to population scripts and verify before writing to Palantir
- Cache raw API responses to disk for audit and replay
- Every external API call gets a timeout (5s default) and graceful error handling
- Never crash the demo path — degrade gracefully when a source is unreachable

## What NOT to do

- Don't fabricate ontology data — every entity must have a real `source_url`
- Don't write to Palantir without `--dry-run` verification first
- Don't modify object type schemas during the build (locked in via AI FDE)
- Don't extend the legacy `backend/app/` FastAPI scaffold. New cross-team endpoints belong in `backend/ai/voice_server.py` (the thin transport wrapper over `query_api` / `realtime_enrichment`) — keep real logic in the underlying Python modules so it stays testable without HTTP.
- Don't push broken code to `main` — work on `voice-agent`
