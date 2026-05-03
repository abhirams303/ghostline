# Project Context

This file is for coding agents and new contributors who need a fast, accurate picture of the repo before making changes.

## One-Sentence Summary

OPSEC Mirror is a defensive OSINT analysis app that shows what an adversary could infer from public traces around a target location.

## Product Goal

The product should let a user enter a place, route anchor, or later a unit-linked footprint and quickly see:

- exposed movement signals
- exposed personnel behavior signals
- exposed facility or infrastructure signals
- exposed aerial or revisit timing signals
- a synthesized threat brief describing what a public-data adversary could plausibly infer

## Current State

The repo is a scaffold, not a finished product.

Implemented now:

- Next.js command deck frontend shell
- voice-server `GET /voice/mission_report` adapter consumed by the command deck and Pipecat-facing integrations
- real Mapbox + deck.gl map rendering in the frontend
- server-side OpenStreetMap Nominatim geocoding at `GET /geocode`
- FastAPI backend with `POST /analyze`
- SSE endpoint at `GET /stream/{run_id}`
- typed request and response models
- live-by-default analysis path
- local SQLite persistence for runs, findings, and deduped source evidence
- cached demo JSON payloads for specific preset locations
- production-hardened ADS-B Exchange collector with bounded multi-snapshot sampling, path generation, and source-health reporting
- live Exa news/public-web collector
- opt-in Strava global heatmap collector path, disabled by default
- placeholder collector for `satellite`
- OpenAI-backed synthesis when `OPENAI_API_KEY` is configured
- local fallback narrative generation when OpenAI is not configured or the request fails
- manual Strava collection endpoint at `POST /collect/strava` for local validation and cache generation

Not implemented yet:

- production-grade source integrations
- Palantir AIP ontology push logic
- route and `unit_id` analysis beyond schema placeholders

## Non-Goals For The Current Scaffold

Do not assume this repo already supports:

- Danti
- production scraping
- authenticated intel feeds
- targeting workflows
- automated harmful action

## Architectural Shape

```text
Frontend (Next.js command deck)
  -> GET /voice/mission_report for Ghostline-backed deck reports
  -> GET /voice/get_assessment for supported-location geocoding fallback
  -> POST /analyze fallback when using the original backend app
Backend (FastAPI)
  -> parallel collectors
  -> local SQLite persistence
  -> scoring
  -> synthesized narrative preview
  -> run_id returned to client
Frontend
  -> GET /stream/{run_id}
```

## Source-of-Truth Files

If you are changing a contract, these files matter first:

- backend request schema: `backend/app/models/location.py`
- backend finding schema: `backend/app/models/finding.py`
- backend response schema: `backend/app/models/report.py`
- frontend mirrored types: `frontend/src/types/findings.ts`
- command deck report types: `frontend/src/domain/types.ts`
- command deck backend adapter: `frontend/src/services/palantirAdapter.ts`
- voice bridge MissionReport adapter: `backend/ai/frontend_adapter.py`
- voice bridge route surface: `backend/ai/voice_server.py`
- geocode endpoint: `backend/app/api/geocode.py`
- main analyze endpoint: `backend/app/api/analyze.py`
- narrative stream behavior: `backend/app/api/stream.py`

## Current Runtime Behavior

### Command Deck Mode

- frontend runs as a command deck on `http://localhost:3000`
- root `pnpm dev:backend` runs `backend.ai.voice_server:app` on `http://localhost:8000`
- assessment commands call `/voice/mission_report` first
- supported-location geocoding falls back through `/voice/get_assessment`
- custom target strings fall back through backend `/geocode` and then Mapbox when configured
- the original `/analyze` path remains as a compatibility fallback

### Analyze Mode

- frontend command-deck reports default to `live`
- backend uses cached JSON only when request mode is `demo`
- optional demo fallback can still be enabled through backend env

### Demo Targets

Cached app payloads exist for:

- `Fort Liberty`
- `Norfolk Naval`
- `Creech AFB`

They live under `backend/data/cached/`.

Voice bridge demo-cache payloads also exist under `backend/ai/demo_cache/` for the command deck and voice-agent locations, including `Fort Liberty`, `Naval Station Norfolk`, `Creech AFB`, `Joint Base Lewis-McChord`, `Naval Base San Diego`, and `Shack15`.

## Collector Posture

Each collector should stay isolated in `backend/app/collectors/`.

Current expectation:

- `strava.py`: movement or heat-signature style findings. When `OPSEC_MIRROR_STRAVA_ENABLED=true`, it fetches a 3x3 Strava global heatmap tile grid using local CloudFront cookies from `backend/.env`; otherwise it returns demo-safe stub findings.
- `adsb.py`: bounded live sampling of nearby aircraft with normalized markers, short-track layers, source-health reporting, and aerial-exposure findings.
- `satellite.py`: revisit-window and imaging opportunity findings.
- `exa.py`: live public-web or news enrichment via Exa search.

Do not spread collector-specific parsing into API routes or frontend components.

## LLM Posture

The synthesis layer is intentionally thin right now.

- prompts live in `backend/app/synthesis/prompts.py`
- score computation lives in `backend/app/synthesis/scorer.py`
- run lifecycle and preview generation live in `backend/app/synthesis/synthesizer.py`
- OpenAI request code lives in `backend/app/synthesis/openai_client.py`

Current behavior:

- if `OPENAI_API_KEY` is present, the backend calls the OpenAI Responses API
- if the key is missing or the call fails, the backend falls back to a local deterministic summary
- SSE replays the finished narrative in chunks; it is not token-by-token model streaming yet

If you extend the LLM path:

- keep raw collector output structured
- keep the LLM focused on summarization and defensive recommendations
- do not let the model invent evidence sources

## Safety And Ethics Guardrails

This project is framed as defensive OPSEC tooling.

Always preserve:

- explicit defensive-use framing
- no instructions for harmful action
- no "how to target" synthesis behavior
- separation between demo-safe content and live source integrations

Reference: `docs/ETHICS.md`

## Frontend Expectations

The frontend is a single-page command deck today.

Key components:

- `CommandDeckShell.tsx`
- `CommandDeck.tsx`
- `useCommandDeck.ts`
- `DeckMapSurface.tsx`
- `ConversationBar.tsx`
- `IntelPanel.tsx`
- `TopBar.tsx`

If you expand the frontend:

- keep the first-run experience fast
- preserve the one-input demo flow
- avoid turning the landing interaction into a multi-step form
- keep the deck's `/voice/mission_report` integration ahead of older fallback endpoints

## Backend Expectations

The backend should remain the orchestration layer.

Prefer:

- small API route modules
- typed models at the boundary
- collector logic outside routes
- synthesis logic outside routes

Avoid:

- embedding source-specific parsing in `main.py`
- duplicating schema definitions
- making the frontend know collector internals

### Geocoding

- `GET /geocode?q=<location>` wraps OpenStreetMap Nominatim and returns a `LocationInput`.
- Nominatim calls are server-side only so the backend can send a compliant identifying `User-Agent`.
- The wrapper caches normalized queries for `OPSEC_MIRROR_CACHE_TTL_SECONDS` and enforces at least 1 second between upstream Nominatim requests.
- Public Nominatim is suitable for local/light use only; production volume should use a dedicated Nominatim instance or commercial geocoder.

## Environment Setup

Local runtime files:

- `backend/.env`
- `frontend/.env.local`
- `backend/data/runtime/opsec_mirror.sqlite3` by default

Templates:

- `backend/.env.example`
- `frontend/.env.local.example`

The root `.env.example` is reference-only.

## Common Commands

Frontend install:

```powershell
pnpm install
```

Backend install:

```powershell
cd backend
python -m pip install -e .[dev]
```

Run frontend:

```powershell
pnpm dev:frontend
```

Run backend:

```powershell
pnpm dev:backend
```

This starts the command-deck voice bridge, not the original `app.main` FastAPI service.

Run frontend lint:

```powershell
pnpm lint
```

Run frontend build:

```powershell
pnpm build
```

Run backend tests:

```powershell
cd backend
python -m pytest
```

Run a manual Strava tile smoke check:

```powershell
cd backend
python scripts/smoke_strava.py
```

Browser smoke check:

```text
Open http://localhost:3000, enter "analyze naval base san diego", and confirm the deck updates to NAVAL BASE SAN DIEGO after a /voice/mission_report request.
```

## If You Change Something Important

Update these when relevant:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_CONTEXT.md`
- `AGENTS.md`
- `.gitignore` for generated local artifacts
- env example files
- mirrored frontend and backend types

## Recommended Next Steps

If no user instruction overrides this, the most sensible order is:

1. deepen ADS-B from bounded short-window sampling into richer track-history and corridor analysis
2. add richer Exa observability, diagnostics, and operational runbooks on top of the new multi-query evidence gathering and deduplication flow
3. upgrade SSE from replayed chunks to true provider streaming
4. add route-based analysis beyond single-point targets
5. add stronger map interactions such as fitting, clustering, and time-based layer playback
