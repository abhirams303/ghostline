# Architecture

## Flow

Frontend (`Next.js` single-page shell) sends a target request to `POST /analyze`.

The backend:

1. Validates the request.
2. Runs live collectors in parallel.
3. Falls back to cached demo data only when the request is explicitly `demo`, or when live collection yields nothing and fallback is enabled.
4. Computes category scores.
5. Returns map layers, findings, and a threat-brief preview plus a `run_id`.
6. Frontend subscribes to `/stream/{run_id}` for incremental narrative updates.

## Current Collector Posture

- `Strava`: interface scaffold with live-path placeholder output
- `ADSB`: interface scaffold with live-path placeholder output
- `Satellite`: interface scaffold with revisit-window placeholder output
- `Exa`: enrichment scaffold, disabled by policy until wired

## Boundaries

- No Danti integration in this version
- No scraping-heavy implementation baked into the initial scaffold
- Cached demo packs remain available for rehearsal and backup
