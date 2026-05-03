"""GHOSTLINE voice server — HTTP bridge for the Pipecat voice agent + deck.gl frontend.

Wraps the read-only query_api and realtime_enrichment functions in a thin
FastAPI surface. CORS is fully open so the deck.gl frontend and the
Pipecat client can call from any origin.

This is the ONE sanctioned HTTP surface for cross-team consumers — the
underlying query functions still hold all the real logic; this file is
a transport layer.

Run:
    uvicorn backend.ai.voice_server:app --host 0.0.0.0 --port 8000

Endpoints:
    GET /health
    GET /voice/get_assessment?location=...
    GET /voice/get_cascade?location=...
    GET /voice/get_adversary_actions?location=...
    GET /voice/compare_locations
    GET /voice/recommend_mitigations?location=...
    GET /voice/get_provenance?entity_id=...
    GET /voice/get_full_picture?location=...
    GET /voice/get_current_state?lat=...&lon=...&location_name=...
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .query_api import (
    compare_locations,
    get_adversary_actions,
    get_assessment,
    get_cascade,
    get_full_picture,
    get_provenance,
    recommend_mitigations,
)
from .realtime_enrichment import get_full_current_state

log = logging.getLogger("ghostline.voice_server")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="GHOSTLINE Voice Server",
    description="HTTP bridge for the Pipecat voice agent and deck.gl frontend.",
    version="0.1.0",
)

# Fully-open CORS — cross-team consumers (Pipecat client, deck.gl frontend)
# call from arbitrary localhost ports. allow_credentials must be False when
# allow_origins is "*" per the CORS spec.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_for_error(err_msg: str) -> int:
    """Pick an HTTP status from the error message produced by the query layer."""
    e = (err_msg or "").lower()
    if "not configured" in e or "missing" in e:
        return 503  # Service unavailable — backend not wired up
    if "no " in e and ("found" in e or "available" in e):
        return 404
    if "could not infer" in e or "invalid" in e:
        return 400
    return 500


def _wrap(result: Any) -> JSONResponse:
    """Map a {"error": ...} dict to a non-2xx response; otherwise pass through 200."""
    if isinstance(result, dict) and "error" in result:
        return JSONResponse(status_code=_status_for_error(result["error"]), content=result)
    return JSONResponse(status_code=200, content=result)


# ---------------------------------------------------------------------------
# Service / discovery endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "ghostline-voice-server",
        "version": "0.1.0",
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "ghostline-voice-server",
        "endpoints": [
            "/health",
            "/voice/get_assessment?location=...",
            "/voice/get_cascade?location=...",
            "/voice/get_adversary_actions?location=...",
            "/voice/compare_locations",
            "/voice/recommend_mitigations?location=...",
            "/voice/get_provenance?entity_id=...",
            "/voice/get_full_picture?location=...",
            "/voice/get_current_state?lat=...&lon=...&location_name=...",
        ],
        "docs": "/docs",
    }


# ---------------------------------------------------------------------------
# Voice agent endpoints (wrap query_api)
# ---------------------------------------------------------------------------

@app.get("/voice/get_assessment")
def voice_get_assessment(
    location: str = Query(..., min_length=1, description="Location name; fuzzy match supported."),
) -> JSONResponse:
    return _wrap(get_assessment(location))


@app.get("/voice/get_cascade")
def voice_get_cascade(
    location: str = Query(..., min_length=1),
) -> JSONResponse:
    return _wrap(get_cascade(location))


@app.get("/voice/get_adversary_actions")
def voice_get_adversary_actions(
    location: str = Query(..., min_length=1),
) -> JSONResponse:
    # Returns a list (possibly empty); never an {"error": ...} dict.
    return JSONResponse(status_code=200, content=get_adversary_actions(location))


@app.get("/voice/compare_locations")
def voice_compare_locations() -> JSONResponse:
    return JSONResponse(status_code=200, content=compare_locations())


@app.get("/voice/recommend_mitigations")
def voice_recommend_mitigations(
    location: str = Query(..., min_length=1),
) -> JSONResponse:
    return _wrap(recommend_mitigations(location))


@app.get("/voice/get_provenance")
def voice_get_provenance(
    entity_id: str = Query(..., min_length=1, description="Any ontology primary key."),
) -> JSONResponse:
    return _wrap(get_provenance(entity_id))


@app.get("/voice/get_full_picture")
def voice_get_full_picture(
    location: str = Query(..., min_length=1),
) -> JSONResponse:
    return _wrap(get_full_picture(location))


# ---------------------------------------------------------------------------
# Realtime endpoint (wraps realtime_enrichment)
# ---------------------------------------------------------------------------

@app.get("/voice/get_current_state")
def voice_get_current_state(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    location_name: str = Query(..., min_length=1),
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content=get_full_current_state(lat, lon, location_name),
    )
