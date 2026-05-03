# OPSEC Mirror

Defensive OSINT mirror that estimates what an adversary could infer from public traces around a base, route anchor, or operating area.

## What This Repo Is

This repo is an outline scaffold for the first version of the product, not a finished intelligence platform.

Today it includes:

- a `pnpm`-managed Next.js command deck frontend
- a voice-server MissionReport endpoint for the command deck and Pipecat agent
- a FastAPI backend with typed request and response models
- server-side OpenStreetMap Nominatim geocoding for custom location strings
- a real Mapbox + deck.gl map surface with interactive overlays and synthetic fallback geometry
- a production-hardened live ADS-B Exchange collector, a live Exa collector, an opt-in Strava global heatmap collector, and a scaffolded `satellite` collector
- a local SQLite evidence store for analysis runs, findings, and deduped source documents
- cached demo payloads for rehearsed presentations
- OpenAI-backed threat-brief synthesis with fallback preview generation
- SSE threat-brief replay over chunked narrative output

It does not yet include production-grade live integrations for every data source, but ADS-B is hardened for production-style live use and Strava is available behind an opt-in collector path.

## Current Product Shape

User flow:

1. Talk to the voice agent or type into the command deck.
2. Location commands instantly focus the deck.gl map surface.
3. Assessment commands call the voice-server `/voice/mission_report` integration first.
4. Backend query APIs resolve cached or live Ghostline data, including the remote MissionReport adapter.
5. The frontend renders command activity, score strips, findings, layer toggles, and the live Mapbox + deck.gl surface.

## Command Deck Integration

The primary local UI is the command deck at `http://localhost:3000`.

- Typed location commands such as `show naval base san diego` or `go to fort liberty` focus the map immediately.
- Assessment commands such as `analyze naval base san diego` call `GET /voice/mission_report` on the voice bridge first.
- If the voice bridge cannot return a MissionReport, the frontend falls back to `/voice/get_assessment`, then the original `/analyze` API shape, then local demo context.
- Pipecat voice connection starts through `POST /api/pipecat/start`; live voice requires the Pipecat Cloud and provider keys listed in the env templates.

## Stack

- Frontend: Next.js 16, React 19, Tailwind CSS, Mapbox, deck.gl
- Backend: FastAPI, Pydantic, async collectors
- Package management: `pnpm` for the frontend workspace
- Python packaging: editable `backend/` package

## Quick Start

### Prerequisites

- Node.js 24+
- `pnpm` 10+
- Python 3.11+

### 1. Install dependencies

Frontend:

```powershell
pnpm install
```

Backend:

```powershell
cd backend
python -m pip install -e .[dev]
cd ..
```

### 2. Create local env files

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.local.example frontend/.env.local
```

### 3. Start the app

Frontend only:

```powershell
pnpm dev:frontend
```

Command-deck backend bridge only:

```powershell
pnpm dev:backend
```

Both:

```powershell
pnpm dev
```

Frontend runs at `http://localhost:3000`.
The command-deck backend bridge runs at `http://localhost:8000`.

## Verification

Frontend:

```powershell
pnpm lint
pnpm build
```

Backend:

```powershell
cd backend
python -m pytest
cd ..
```

Browser smoke path:

1. Start `pnpm dev`.
2. Open `http://localhost:3000`.
3. Enter `analyze naval base san diego`.
4. Confirm the UI shows `NAVAL BASE SAN DIEGO` and the voice bridge logs a `GET /voice/mission_report` request.

Manual Strava heatmap smoke check:

```powershell
cd backend
python scripts/smoke_strava.py
cd ..
```

## Environment Files

Use these files:

- root reference: [.env.example](./.env.example)
- backend runtime template: [backend/.env.example](./backend/.env.example)
- frontend runtime template: [frontend/.env.local.example](./frontend/.env.local.example)

Important notes:

- The root `.env.example` is just a shared reference.
- The backend reads `backend/.env`.
- The frontend reads `frontend/.env.local`.
- Live analysis persistence defaults to `backend/data/runtime/opsec_mirror.sqlite3`.
- Set `NEXT_PUBLIC_MAPBOX_TOKEN` in `frontend/.env.local` to enable the real basemap.
- Set `PIPECAT_CLOUD_API_KEY` in `frontend/.env.local` to enable live Pipecat voice startup through the Next.js API route.
- Set `OPENAI_API_KEY` in `backend/.env` to enable real synthesis.
- Set `ADSBEXCHANGE_API_KEY` in `backend/.env` to enable the live ADS-B collector.
- Set `EXA_API_KEY` in `backend/.env` to enable the live Exa news/web collector.
- Nominatim geocoding uses no API key, but keep `OPSEC_MIRROR_NOMINATIM_USER_AGENT` identifying this application; public Nominatim is intended for local/light usage only.
- ADS-B performs bounded multi-snapshot sampling, emits marker and short-track layers, filters invalid out-of-radius rows, and reports collector health states such as disabled, missing configuration, upstream error, and no-data.
- The Strava heatmap path requires local `STRAVA_CF_KEY_PAIR_ID`, `STRAVA_CF_POLICY`, and `STRAVA_CF_SIGNATURE` values in `backend/.env` and only runs when `OPSEC_MIRROR_STRAVA_ENABLED=true`.

## Project Structure

```text
opsec-mirror/
|-- backend/                # FastAPI app plus Ghostline voice bridge/query APIs
|-- frontend/               # Next.js command deck
|-- docs/                   # Architecture, ethics, demo script, agent context
|-- scripts/                # Setup, deploy, and cache helper scripts
|-- AGENTS.md               # Agent operating instructions for this repo
|-- package.json            # Root workspace scripts
`-- pnpm-workspace.yaml     # pnpm workspace definition
```

## Important Docs

- [docs/PROJECT_CONTEXT.md](./docs/PROJECT_CONTEXT.md)
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)
- [docs/ETHICS.md](./docs/ETHICS.md)
- [docs/DEMO_SCRIPT.md](./docs/DEMO_SCRIPT.md)

## Team Conventions

- Default mode is `live`; use `demo` only for rehearsed or offline-safe runs.
- Cached demo files in `backend/data/cached/` and `backend/ai/demo_cache/` are committed artifacts, not throwaway output.
- Keep collector integrations isolated to `backend/app/collectors/`.
- Keep command-deck data adapters isolated to `frontend/src/services/`.
- Keep API contract changes mirrored across:
  - `backend/app/models/`
  - `frontend/src/types/findings.ts`
  - `frontend/src/domain/types.ts`
  - `docs/PROJECT_CONTEXT.md`

## Known Gaps

- ADS-B and Exa are live; Strava is available behind an opt-in cookie-backed collector path; `satellite` still returns placeholder findings.
- Exa now performs multi-query news/public-web gathering with deduplication and scoring, but still lacks richer observability and runbook-grade production operations.
- SSE currently replays a completed narrative in chunks instead of token-streaming directly from OpenAI.
- Palantir AIP is still a typed placeholder client.

## Agent Notes

If you are working through an agent, read [AGENTS.md](./AGENTS.md) and [docs/PROJECT_CONTEXT.md](./docs/PROJECT_CONTEXT.md) before changing architecture, contracts, or collector behavior.
