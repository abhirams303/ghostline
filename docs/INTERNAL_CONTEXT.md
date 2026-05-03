# Internal Context

This file captures current project-wide working context for local teammates and coding agents. Do not put secrets, API keys, cookies, or copied request headers in this file.

## Current Branch And Goal

- Branch: `codex-strava-integration`
- Current focus: make the Strava movement-exposure layer work end-to-end while preserving the existing OPSEC Mirror scaffold.
- Product framing: defensive OPSEC mirror, not targeting tooling. The app shows what public traces may reveal about a location the user is authorized to assess.

## Product Idea

OPSEC Mirror flips OSINT inward. Instead of helping an analyst investigate an external target, it helps a commander, OPSEC officer, base security manager, or red-team assessor see what an adversary could infer from public data about their own footprint.

Core demo story:

1. User enters a base or operating-area anchor.
2. Backend runs public-signal collectors.
3. Frontend displays evidence layers, exposure score, and a streamed threat brief.
4. Output focuses on exposure and mitigation, not operational targeting.

Primary hackathon value: the idea is easy to explain to military and defense-tech audiences: "What can they see about us from public traces alone?"

## Architecture Snapshot

- Frontend: Next.js single-page shell in `frontend/`
- Backend: FastAPI service in `backend/app/`
- Main endpoint: `POST /analyze`
- Narrative stream: `GET /stream/{run_id}`
- Collector boundary: `backend/app/collectors/`
- Backend schemas: `backend/app/models/`
- Mirrored frontend types: `frontend/src/types/findings.ts`
- Demo caches: `backend/data/cached/`

Keep source-specific parsing inside collectors. Keep API routes thin.

## Current Implementation State

Implemented:

- FastAPI backend with `POST /analyze`
- SSE threat-brief stream
- Typed Pydantic models
- Cached demo reports for Fort Liberty, Norfolk Naval, and Creech AFB
- Placeholder ADS-B, satellite, and Exa collectors
- Opt-in Strava global heatmap collector path
- Manual Strava smoke script
- Safe Strava collector tests that do not hit the live network

Still scaffolded:

- Real deck.gl/Mapbox rendering
- LLM provider calls
- Palantir AIP push logic
- Route and `unit_id` analysis behavior
- Production-grade live collector hardening

## Strava Integration Context

The Strava integration uses authenticated browser-derived CloudFront cookies for Global Heatmap tile access. There is no official public Strava API for these heatmap tiles.

Current tile URL pattern:

```text
https://content-a.strava.com/identified/globalheat/all/blue/{z}/{x}/{y}@2x.png?v=19
```

Current collector behavior:

- `OPSEC_MIRROR_STRAVA_ENABLED=false`: return demo-safe stub finding and layer.
- `OPSEC_MIRROR_STRAVA_ENABLED=true`: fetch a 3x3 tile grid around the target using local cookies from `backend/.env`.
- Empty or tiny PNGs are treated as no activity.
- Auth failures surface as runtime errors so they are caught before demos.

Relevant files:

- `backend/app/collectors/strava.py`
- `backend/scripts/smoke_strava.py`
- `backend/tests/test_strava_collector.py`
- `backend/.env.example`
- `backend/pyproject.toml`

Required local env names:

```text
OPSEC_MIRROR_STRAVA_ENABLED=true
STRAVA_CF_KEY_PAIR_ID=
STRAVA_CF_POLICY=
STRAVA_CF_SIGNATURE=
STRAVA_IDCF=
STRAVA_CF_EXPIRES=
```

Never commit `backend/.env` or copied cookie values. Rotate/sign out after the event if real cookies were pasted into chats or shared terminals.

## Local Environment State

- Homebrew provides `node`, `npm`, and `pnpm`.
- Backend Python dependencies are installed in `backend/.venv`.
- Frontend dependencies were not installed at the time this context was written unless a later user action changed that.
- `backend/.env` is ignored by git.
- Root `.env` and `backend/app/collectors/.env` are not used by the FastAPI settings path when commands are run from `backend/`.

Run backend commands from `backend/` so `.env` is loaded correctly:

```bash
cd backend
.venv/bin/python -m pytest
.venv/bin/python scripts/smoke_strava.py
.venv/bin/uvicorn app.main:app --reload --port 8000
```

If running smoke tests inside a sandboxed Codex command, live Strava DNS/network access may require explicit approval. Running directly in the local terminal avoids that sandbox restriction.

## Verification State

Last safe backend test command:

```bash
cd backend
.venv/bin/python -m pytest
```

Known passing state after Strava collector changes: 5 backend tests passed.

Manual Strava smoke status:

- The script imports correctly after adding the backend root to `sys.path`.
- A browser-copied cURL appeared to reach binary PNG output, which suggests the browser tile request worked.
- If Python smoke test returns `401`, refresh the Global Heatmap page, copy cookies from a live `content-a.strava.com/identified/globalheat/...` request, and update `backend/.env`.

## Immediate Next Steps

1. Get `backend/scripts/smoke_strava.py` returning a saved `test_tile.png`.
2. Confirm `POST /analyze` works with `OPSEC_MIRROR_STRAVA_ENABLED=true`.
3. Wire richer Strava layer data into the frontend map shell.
4. Keep demo cache usable even if live Strava auth fails.
5. Avoid adding more sources until the Strava visual path is demoable.

## Guardrails

- Defensive OPSEC framing must stay explicit.
- Do not add user-level Strava scraping or individual athlete lookup.
- Do not store PII.
- Do not let LLM synthesis invent evidence sources.
- Do not turn exposure findings into tactical targeting instructions.
