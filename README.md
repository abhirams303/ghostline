# OPSEC Mirror

Defensive OSINT mirror that estimates what an adversary could infer from public traces around a base, route anchor, or operating area.

## What This Repo Is

This repo is an outline scaffold for the first version of the product, not a finished intelligence platform.

Today it includes:

- a `pnpm`-managed Next.js frontend shell
- a FastAPI backend with typed request and response models
- stubbed live-collector interfaces for `strava`, `adsb`, `satellite`, and `exa`
- cached demo payloads for rehearsed presentations
- streaming threat-brief scaffolding over SSE

It does not yet include production-grade live integrations for the data sources.

## Current Product Shape

User flow:

1. Enter a target location.
2. Run analysis in `live` or `demo` mode.
3. Backend fans out across collectors in parallel.
4. Findings are scored and summarized into a threat-brief preview.
5. Frontend renders evidence cards, layer toggles, and a map-shell surface.

## Stack

- Frontend: Next.js 16, React 19, Tailwind CSS, deck.gl shell
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

## Environment Files

Use these files:

- root reference: [.env.example](</C:/Users/lipey/Code/forge/.env.example>)
- backend runtime template: [backend/.env.example](</C:/Users/lipey/Code/forge/backend/.env.example>)
- frontend runtime template: [frontend/.env.local.example](</C:/Users/lipey/Code/forge/frontend/.env.local.example>)

Important notes:

- The root `.env.example` is just a shared reference.
- The backend reads `backend/.env`.
- The frontend reads `frontend/.env.local`.
- Live collector credentials are intentionally optional right now because most collectors are still interface-level.

## Project Structure

```text
opsec-mirror/
├── backend/                # FastAPI service, models, collectors, synthesis
├── frontend/               # Next.js app shell
├── docs/                   # Architecture, ethics, demo script, agent context
├── scripts/                # Setup, deploy, and cache helper scripts
├── AGENTS.md               # Agent operating instructions for this repo
├── package.json            # Root workspace scripts
└── pnpm-workspace.yaml     # pnpm workspace definition
```

## Important Docs

- [docs/PROJECT_CONTEXT.md](</C:/Users/lipey/Code/forge/docs/PROJECT_CONTEXT.md>)
- [docs/ARCHITECTURE.md](</C:/Users/lipey/Code/forge/docs/ARCHITECTURE.md>)
- [docs/ETHICS.md](</C:/Users/lipey/Code/forge/docs/ETHICS.md>)
- [docs/DEMO_SCRIPT.md](</C:/Users/lipey/Code/forge/docs/DEMO_SCRIPT.md>)

## Team Conventions

- Default mode is `live`; use `demo` only for rehearsed or offline-safe runs.
- Cached demo files in `backend/data/cached/` are committed artifacts, not throwaway output.
- Keep collector integrations isolated to `backend/app/collectors/`.
- Keep API contract changes mirrored across:
  - `backend/app/models/`
  - `frontend/src/types/findings.ts`
  - `docs/PROJECT_CONTEXT.md`

## Known Gaps

- The map is a shell, not a full deck.gl + Mapbox implementation yet.
- Collector classes return placeholder findings instead of real vendor responses.
- LLM synthesis is scaffolded but not wired to Anthropic or OpenAI APIs.
- Palantir AIP is still a typed placeholder client.

## Agent Notes

If you are working through an agent, read [AGENTS.md](</C:/Users/lipey/Code/forge/AGENTS.md>) and [docs/PROJECT_CONTEXT.md](</C:/Users/lipey/Code/forge/docs/PROJECT_CONTEXT.md>) before changing architecture, contracts, or collector behavior.
