# Architecture

## Flow

Frontend (`Next.js` command deck) runs on `http://localhost:3000` and uses the Ghostline voice bridge on `http://localhost:8000` as its preferred integration surface.

Primary command deck flow:

1. User types or speaks a command such as `show naval base san diego` or `analyze naval base san diego`.
2. Location-only commands focus the local deck.gl map surface immediately.
3. Assessment commands call `GET /voice/mission_report?location=...`.
4. `backend/ai/voice_server.py` delegates report shaping to `backend/ai/frontend_adapter.py`.
5. The adapter reads through `backend/ai/query_api.py`, which uses Foundry when configured and `backend/ai/demo_cache/` fallback data when live dependencies are unavailable.
6. The command deck renders a `MissionReport` with scores, findings, layers, narrative, and AIP sync state.

Compatibility flow:

Frontend can still fall back to the original backend request path by sending a target request to `POST /analyze`.

The backend:

1. Validates the request.
2. Runs live collectors in parallel.
3. Persists the run, normalized findings, and deduped source documents into local SQLite storage.
4. Falls back to cached demo data only when the request is explicitly `demo`, or when live collection yields nothing and fallback is enabled.
5. Computes category scores.
6. Calls OpenAI synthesis when `OPENAI_API_KEY` is configured, otherwise uses the local fallback narrative builder.
7. Returns map layers, findings, and a threat-brief preview plus a `run_id`.
8. Legacy frontend consumers can subscribe to `/stream/{run_id}` for incremental narrative updates.

## Frontend Map Posture

- The frontend now uses a real Mapbox basemap rendered through `react-map-gl/mapbox`.
- Collector `layers` and `findings` are translated into interactive `deck.gl` overlays in the browser.
- Before a report loads, the map shows synthetic fallback overlays so the surface remains demonstrable.
- The command deck keeps map commands and assessment commands in one conversation bar so typed and Pipecat voice input drive the same routing code.

## Voice And Pipecat Posture

- `POST /api/pipecat/start` is a Next.js route that starts a Pipecat Cloud session when `PIPECAT_CLOUD_API_KEY` is configured.
- Pipecat server messages can request a command-deck location change, and final user transcripts are routed through the same command parser used by typed input.
- Live voice requires Pipecat, Daily, Deepgram, Cartesia, and OpenAI-style provider keys as documented in the env templates.

## Current Collector Posture

- `Strava`: interface scaffold with live-path placeholder output
- `ADSB`: live ADS-B Exchange snapshot collector with normalized aircraft markers and heuristic findings
- `Satellite`: interface scaffold with revisit-window placeholder output
- `Exa`: live news/public-web search collector using the Exa search API

## Boundaries

- No Danti integration in this version
- No scraping-heavy implementation baked into the initial scaffold
- Cached demo packs remain available for rehearsal and backup
- Local verification artifacts such as `.codex-*`, `test-results/`, and `playwright-report/` are ignored and should not be committed
- The current SSE endpoint replays narrative chunks after synthesis; it is not yet a true provider-token stream
- The ADS-B collector currently uses one live snapshot per analysis, not burst sampling or full historical track retrieval

## Persistence Posture

- Live analysis runs are stored in a local SQLite database under `backend/data/runtime/` by default.
- Repeated runs add new `search_runs` rows but upsert source evidence by provider ID, canonical URL, or a stable content fingerprint.
- This persistence layer is intended for collector caching and evidence history, not as a substitute for the source provider’s system of record.
