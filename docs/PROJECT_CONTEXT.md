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

- Next.js single-page frontend shell
- FastAPI backend with `POST /analyze`
- SSE endpoint at `GET /stream/{run_id}`
- typed request and response models
- live-by-default analysis path
- cached demo JSON payloads for specific preset locations
- placeholder collectors for `strava`, `adsb`, `satellite`, and `exa`

Not implemented yet:

- real source integrations
- real LLM synthesis provider calls
- true deck.gl/Mapbox rendering
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
Frontend (Next.js app shell)
  -> POST /analyze
Backend (FastAPI)
  -> parallel collectors
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
- main analyze endpoint: `backend/app/api/analyze.py`
- narrative stream behavior: `backend/app/api/stream.py`

## Current Runtime Behavior

### Analyze Mode

- frontend defaults to `live`
- backend uses cached JSON only when request mode is `demo`
- optional demo fallback can still be enabled through backend env

### Demo Targets

Cached demo payloads exist for:

- `Fort Liberty`
- `Norfolk Naval`
- `Creech AFB`

They live under `backend/data/cached/`.

## Collector Posture

Each collector should stay isolated in `backend/app/collectors/`.

Current expectation:

- `strava.py`: movement or heat-signature style findings
- `adsb.py`: aircraft track and timing-style findings
- `satellite.py`: revisit-window and imaging opportunity findings
- `exa.py`: public-web or news enrichment

Do not spread collector-specific parsing into API routes or frontend components.

## LLM Posture

The synthesis layer is intentionally thin right now.

- prompts live in `backend/app/synthesis/prompts.py`
- score computation lives in `backend/app/synthesis/scorer.py`
- run lifecycle and preview generation live in `backend/app/synthesis/synthesizer.py`

If you wire a real LLM:

- keep raw collector output structured
- keep the LLM focused on summarization and defensive recommendations
- do not let the model invent evidence sources

## Safety And Ethics Guardrails

This project is framed as defensive OPSEC tooling.

Always preserve:

- explicit defensive-use framing
- no instructions for harmful action
- no “how to target” synthesis behavior
- separation between demo-safe content and live source integrations

Reference: `docs/ETHICS.md`

## Frontend Expectations

The frontend is intentionally a single-page shell today.

Key components:

- `SearchBar.tsx`
- `Map.tsx`
- `ThreatBrief.tsx`
- `ExposureScore.tsx`
- `FindingCard.tsx`

If you expand the frontend:

- keep the first-run experience fast
- preserve the one-input demo flow
- avoid turning the landing interaction into a multi-step form

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

## Environment Setup

Local runtime files:

- `backend/.env`
- `frontend/.env.local`

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

## If You Change Something Important

Update these when relevant:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_CONTEXT.md`
- env example files
- mirrored frontend and backend types

## Recommended Next Steps

If no user instruction overrides this, the most sensible order is:

1. wire one real collector end-to-end
2. replace map-shell placeholders with actual deck.gl rendering
3. wire a real LLM synthesis provider
4. add route-based analysis beyond single-point targets
5. add Palantir AIP integration only after source and contract stability improve
