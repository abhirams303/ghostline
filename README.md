# OPSEC Mirror

Defensive OSINT mirror that estimates what an adversary could infer from public traces around a base, route anchor, or operating area.

## What This Repo Is

This repo is an outline scaffold for the first version of the product, not a finished intelligence platform.

Today it includes:

- a `pnpm`-managed Next.js frontend shell
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

1. Enter a target location.
2. Preset targets resolve locally; custom locations resolve through backend `/geocode`.
3. Run analysis in `live` or `demo` mode.
4. Backend fans out across collectors in parallel.
5. Findings are scored and summarized into a threat-brief preview.
6. Frontend renders evidence cards, layer toggles, and a live Mapbox + deck.gl map surface.

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

Backend only:

```powershell
pnpm dev:backend
```

Both:

```powershell
pnpm dev
```

Frontend runs at `http://localhost:3000`.
Backend runs at `http://localhost:8000`.

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
- Set `OPENAI_API_KEY` in `backend/.env` to enable real synthesis.
- Set `ADSBEXCHANGE_API_KEY` in `backend/.env` to enable the live ADS-B collector.
- Set `EXA_API_KEY` in `backend/.env` to enable the live Exa news/web collector.
- Nominatim geocoding uses no API key, but keep `OPSEC_MIRROR_NOMINATIM_USER_AGENT` identifying this application; public Nominatim is intended for local/light usage only.
- ADS-B performs bounded multi-snapshot sampling, emits marker and short-track layers, filters invalid out-of-radius rows, and reports collector health states such as disabled, missing configuration, upstream error, and no-data.
- The Strava heatmap path requires local `STRAVA_CF_KEY_PAIR_ID`, `STRAVA_CF_POLICY`, and `STRAVA_CF_SIGNATURE` values in `backend/.env` and only runs when `OPSEC_MIRROR_STRAVA_ENABLED=true`.

## Project Structure

```text
opsec-mirror/
|-- backend/                # FastAPI service, models, collectors, synthesis
|-- frontend/               # Next.js app shell
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
- Cached demo files in `backend/data/cached/` are committed artifacts, not throwaway output.
- Keep collector integrations isolated to `backend/app/collectors/`.
- Keep API contract changes mirrored across:
  - `backend/app/models/`
  - `frontend/src/types/findings.ts`
  - `docs/PROJECT_CONTEXT.md`

## Known Gaps

- ADS-B and Exa are live; Strava is available behind an opt-in cookie-backed collector path; `satellite` still returns placeholder findings.
- Exa now performs multi-query news/public-web gathering with deduplication and scoring, but still lacks richer observability and runbook-grade production operations.
- SSE currently replays a completed narrative in chunks instead of token-streaming directly from OpenAI.
- Palantir AIP is still a typed placeholder client.

## Agent Notes

If you are working through an agent, read [AGENTS.md](./AGENTS.md) and [docs/PROJECT_CONTEXT.md](./docs/PROJECT_CONTEXT.md) before changing architecture, contracts, or collector behavior.
