"""Pipecat function tools that bridge teammate's voice agent to our query API.

The bot in ~/Desktop/bang_sec/pipecat-dummy-agent/bot.py owns voice plumbing
(Daily transport, Deepgram STT, OpenAI LLM, Cartesia TTS, RTVI). We add tool
*handlers* without touching that repo — `integrated_bot.py` imports the
schemas + register helper from this module and slots them into his existing
ToolsSchema and llm.register_function pattern.

Every handler:
  - HTTP-GETs our voice_server (default http://localhost:8765, override with
    GHOSTLINE_VOICE_SERVER_URL) so production deployment can point bot and
    voice_server at separate hosts. We do NOT import query_api directly —
    that keeps the bot loosely coupled to the Foundry side.
  - Pushes an RTVI server message so the deck.gl frontend can update panels.
    Message types follow teammate's `command-deck.<kind>` convention; we use
    `command-deck.intel.<kind>` to namespace ours alongside his existing
    `command-deck.location` / `command-deck.location-request`. His current
    frontend ignores types it doesn't handle, so this is purely additive
    until he wires up panel handlers.
  - Calls `params.result_callback(...)` with a compact dict the LLM can
    narrate, separate from the richer payload sent to the frontend.

No modifications to teammate's repo are required.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import httpx
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.services.llm_service import FunctionCallParams

VOICE_SERVER_URL = os.getenv("GHOSTLINE_VOICE_SERVER_URL", "http://localhost:8765").rstrip("/")
HTTP_TIMEOUT_SECONDS = float(os.getenv("GHOSTLINE_VOICE_SERVER_TIMEOUT", "8.0"))


# ---------------------------------------------------------------------------
# Tool schemas (LLM tool descriptions)
# ---------------------------------------------------------------------------

GET_ASSESSMENT_TOOL = FunctionSchema(
    name="get_location_assessment",
    description=(
        "Get the OPSEC exposure assessment for a location. Use when the operator "
        "asks about exposure, risk, threat level, threat brief, or how exposed a "
        "base or installation is. Returns the composite exposure score (0-100), "
        "the LOW/MEDIUM/HIGH risk level, the three sub-scores (strava, aircraft, "
        "satellite), and a spoken-style threat brief."
    ),
    properties={
        "location": {
            "type": "string",
            "description": (
                "Location name. Fuzzy match — 'Norfolk' resolves to 'Naval Station "
                "Norfolk', 'Bragg' to 'Fort Liberty', 'JBLM' to 'Joint Base "
                "Lewis-McChord'."
            ),
        }
    },
    required=["location"],
)

GET_CASCADE_TOOL = FunctionSchema(
    name="get_cascade_analysis",
    description=(
        "Get the cascade-risk analysis showing how surface OPSEC exposure "
        "propagates through linked operational entities (units, platforms, "
        "sensors). Use when the operator asks about cascade risk, downstream "
        "compromise, what intelligence the adversary could infer, or how surface "
        "exposure amplifies. Returns chain depth, real entity names from the "
        "ontology, and the LLM-narrated intelligence-compromised + recommended "
        "upstream mitigation."
    ),
    properties={
        "location": {
            "type": "string",
            "description": "Location name. Fuzzy match supported.",
        }
    },
    required=["location"],
)

GET_ADVERSARY_ACTIONS_TOOL = FunctionSchema(
    name="get_adversary_actions",
    description=(
        "Get the predicted adversary actions for a location's cascade. Use when "
        "the operator asks what an adversary would DO, what attacks are likely, "
        "what targets are at risk, or asks about specific exploitation patterns. "
        "Returns 1-3 actions, each with action_type (surveillance / disruption / "
        "kinetic_planning / deception / interdiction), the targeted entity name "
        "from the chain (unit / platform / sensor), an immediate / days / weeks / "
        "months timeline, and a one-sentence rationale."
    ),
    properties={
        "location": {
            "type": "string",
            "description": "Location name. Fuzzy match supported.",
        }
    },
    required=["location"],
)

COMPARE_LOCATIONS_TOOL = FunctionSchema(
    name="compare_all_locations",
    description=(
        "Rank every populated location by cascade score, highest risk first. Use "
        "when the operator asks 'which base is most exposed', 'show the leader"
        "board', 'compare bases', or any cross-location comparison question. "
        "Returns one row per location with cascade score, risk level, and chain "
        "depth — ready to read aloud."
    ),
    properties={},
    required=[],
)

GET_LIVE_SITUATION_TOOL = FunctionSchema(
    name="get_live_situation",
    description=(
        "Get the realtime situation snapshot for a location: live aircraft within "
        "25 nautical miles via FlightRadar24, upcoming satellite passes (Sentinel-1A/"
        "B, Sentinel-2A/B) with the next pass's ground track, and recent news. Use "
        "when the operator asks 'what's happening right now at X', 'are there "
        "flights overhead', 'when does the next satellite pass', or any current"
        "-state question. Coordinates are resolved automatically from the location's "
        "GhostlineGeoFeature in Foundry."
    ),
    properties={
        "location": {
            "type": "string",
            "description": "Location name. Fuzzy match supported.",
        }
    },
    required=["location"],
)

INTELLIGENCE_TOOLS = [
    GET_ASSESSMENT_TOOL,
    GET_CASCADE_TOOL,
    GET_ADVERSARY_ACTIONS_TOOL,
    COMPARE_LOCATIONS_TOOL,
    GET_LIVE_SITUATION_TOOL,
]


# ---------------------------------------------------------------------------
# HTTP helper + arg helper
# ---------------------------------------------------------------------------

async def _voice_server_get(path: str, params: dict | None = None) -> Any:
    """GET against the voice_server. Returns parsed JSON (dict or list) or
    None on transport-level failure. A 4xx with a JSON `{"error": "..."}` body
    is parsed and returned (the handlers branch on the `error` key)."""
    url = f"{VOICE_SERVER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, params=params)
        # voice_server returns its standard {"error": "..."} dict on 404/503/500.
        if resp.status_code in (200, 404, 400, 500, 503):
            try:
                return resp.json()
            except ValueError:
                return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 — never break the voice loop
        logger.warning("voice_server fetch failed for {}: {}", path, exc)
        return None


def _string_arg(arguments: Mapping[str, Any], key: str) -> str | None:
    v = arguments.get(key)
    return v.strip() if isinstance(v, str) and v.strip() else None


# ---------------------------------------------------------------------------
# Handlers — closure-based to capture rtvi, matching teammate's pattern.
# ---------------------------------------------------------------------------

def _make_get_assessment_handler(rtvi: RTVIProcessor):
    async def handle(params: FunctionCallParams) -> None:
        location = _string_arg(params.arguments, "location")
        if not location:
            await params.result_callback({"success": False, "error": "location is required"})
            return
        data = await _voice_server_get("/voice/get_assessment", {"location": location})
        if data is None or (isinstance(data, dict) and "error" in data):
            err = (data or {}).get("error", "voice_server unreachable")
            await rtvi.send_server_message({
                "type": "command-deck.intel.assessment",
                "ok": False,
                "location": location,
                "error": err,
            })
            await params.result_callback({"success": False, "error": err})
            return
        await rtvi.send_server_message({
            "type": "command-deck.intel.assessment",
            "ok": True,
            "location": data.get("location"),
            "exposure_score": data.get("exposure_score"),
            "risk_level": data.get("risk_level"),
            "brief": data.get("brief"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "scores": {
                "strava": data.get("strava_score"),
                "aircraft": data.get("aircraft_score"),
                "satellite": data.get("satellite_score"),
            },
            "foundry_url": data.get("foundry_url"),
        })
        await params.result_callback({
            "success": True,
            "location": data.get("location"),
            "exposure_score": data.get("exposure_score"),
            "risk_level": data.get("risk_level"),
            "brief": data.get("brief"),
            "scores": {
                "strava": data.get("strava_score"),
                "aircraft": data.get("aircraft_score"),
                "satellite": data.get("satellite_score"),
            },
        })
    return handle


def _make_get_cascade_handler(rtvi: RTVIProcessor):
    async def handle(params: FunctionCallParams) -> None:
        location = _string_arg(params.arguments, "location")
        if not location:
            await params.result_callback({"success": False, "error": "location is required"})
            return
        data = await _voice_server_get("/voice/get_cascade", {"location": location})
        if data is None or (isinstance(data, dict) and "error" in data):
            err = (data or {}).get("error", "voice_server unreachable")
            await rtvi.send_server_message({
                "type": "command-deck.intel.cascade",
                "ok": False,
                "location": location,
                "error": err,
            })
            await params.result_callback({"success": False, "error": err})
            return
        units = data.get("linked_units") or []
        platforms = data.get("linked_platforms") or []
        sensors = data.get("linked_sensors") or []
        chain_summary = (
            f"{len(units)} unit{'s' if len(units) != 1 else ''}, "
            f"{len(platforms)} platform{'s' if len(platforms) != 1 else ''}, "
            f"{len(sensors)} sensor{'s' if len(sensors) != 1 else ''}"
        )
        await rtvi.send_server_message({
            "type": "command-deck.intel.cascade",
            "ok": True,
            "location": data.get("location"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "cascade_score": data.get("cascade_score"),
            "risk_level": data.get("risk_level"),
            "chain_depth": data.get("chain_depth"),
            "linked_units": units,
            "linked_platforms": platforms,
            "linked_sensors": sensors,
            "intelligence_compromised": data.get("intelligence_compromised", ""),
            "recommended_mitigation": data.get("recommended_mitigation", ""),
            "confidence": data.get("confidence"),
            "foundry_url": data.get("foundry_url"),
        })
        await params.result_callback({
            "success": True,
            "location": data.get("location"),
            "cascade_score": data.get("cascade_score"),
            "risk_level": data.get("risk_level"),
            "chain_depth": data.get("chain_depth"),
            "chain_summary": chain_summary,
            "intelligence_compromised": data.get("intelligence_compromised", ""),
            "recommended_mitigation": data.get("recommended_mitigation", ""),
        })
    return handle


def _make_get_adversary_actions_handler(rtvi: RTVIProcessor):
    async def handle(params: FunctionCallParams) -> None:
        location = _string_arg(params.arguments, "location")
        if not location:
            await params.result_callback({"success": False, "error": "location is required"})
            return
        data = await _voice_server_get("/voice/get_adversary_actions", {"location": location})
        if data is None:
            await rtvi.send_server_message({
                "type": "command-deck.intel.adversary-actions",
                "ok": False,
                "location": location,
                "error": "voice_server unreachable",
            })
            await params.result_callback({"success": False, "error": "voice_server unreachable"})
            return
        actions = data if isinstance(data, list) else []
        await rtvi.send_server_message({
            "type": "command-deck.intel.adversary-actions",
            "ok": True,
            "location": location,
            "count": len(actions),
            "actions": actions,
        })
        # Compact narration view for the LLM — drop the foundry_url verbosity.
        compact = [
            {
                "type": a.get("action_type"),
                "target": a.get("target_entity_name"),
                "timeline": a.get("timeline"),
                "rationale": a.get("rationale"),
                "capability": a.get("capability_required"),
            }
            for a in actions
        ]
        await params.result_callback({
            "success": True,
            "location": location,
            "count": len(actions),
            "actions": compact,
        })
    return handle


def _make_compare_locations_handler(rtvi: RTVIProcessor):
    async def handle(params: FunctionCallParams) -> None:
        data = await _voice_server_get("/voice/compare_locations")
        if data is None:
            await rtvi.send_server_message({
                "type": "command-deck.intel.compare",
                "ok": False,
                "error": "voice_server unreachable",
            })
            await params.result_callback({"success": False, "error": "voice_server unreachable"})
            return
        rows = data if isinstance(data, list) else []
        await rtvi.send_server_message({
            "type": "command-deck.intel.compare",
            "ok": True,
            "count": len(rows),
            "rows": rows,
        })
        compact = [
            {
                "location": r.get("location"),
                "cascade_score": r.get("cascade_score"),
                "risk_level": r.get("risk_level"),
                "chain_depth": r.get("chain_depth"),
            }
            for r in rows
        ]
        await params.result_callback({
            "success": True,
            "count": len(rows),
            "ranked": compact,
        })
    return handle


def _make_get_live_situation_handler(rtvi: RTVIProcessor):
    async def handle(params: FunctionCallParams) -> None:
        location = _string_arg(params.arguments, "location")
        if not location:
            await params.result_callback({"success": False, "error": "location is required"})
            return

        # Resolve coords via the assessment lookup so we don't duplicate the
        # fuzzy-name resolver here. One extra hop, but cached on both sides.
        a = await _voice_server_get("/voice/get_assessment", {"location": location})
        if a is None or (isinstance(a, dict) and "error" in a):
            err = (a or {}).get("error", "couldn't resolve location for live state")
            await rtvi.send_server_message({
                "type": "command-deck.intel.live",
                "ok": False,
                "location": location,
                "error": err,
            })
            await params.result_callback({"success": False, "error": err})
            return

        lat, lon, location_name = a.get("lat"), a.get("lon"), a.get("location") or location
        live = await _voice_server_get(
            "/voice/get_current_state",
            {"lat": lat, "lon": lon, "location_name": location_name},
        )
        if live is None or not isinstance(live, dict) or "sources_succeeded" not in live:
            err = "voice_server unreachable" if live is None else (live.get("error") or "live state unavailable")
            await rtvi.send_server_message({
                "type": "command-deck.intel.live",
                "ok": False,
                "location": location_name,
                "error": err,
            })
            await params.result_callback({"success": False, "error": err})
            return

        aircraft = live.get("aircraft") or {}
        sat = live.get("satellite") or {}
        next_pass = sat.get("next_pass") or {}
        news = live.get("news") or {}

        await rtvi.send_server_message({
            "type": "command-deck.intel.live",
            "ok": True,
            "location": location_name,
            "lat": lat,
            "lon": lon,
            "aircraft": aircraft,
            "satellite": sat,
            "news": news,
            "sources_succeeded": live.get("sources_succeeded", []),
        })

        await params.result_callback({
            "success": True,
            "location": location_name,
            "aircraft": {
                "count": aircraft.get("aircraft_count", 0),
                "military_count": aircraft.get("military_count", 0),
                "source": aircraft.get("source"),
                "data_available": aircraft.get("data_available", False),
            },
            "next_satellite_pass": {
                "satellite": next_pass.get("satellite"),
                "rise_utc": next_pass.get("rise_utc"),
                "max_elevation_deg": next_pass.get("max_elevation_deg"),
                "passes_in_window": sat.get("passes_in_window", 0),
            } if next_pass else None,
            "news": {
                "article_count": news.get("article_count", 0),
                "first_title": ((news.get("articles") or [{}])[0] or {}).get("title"),
            },
            "sources_succeeded": live.get("sources_succeeded", []),
        })
    return handle


# ---------------------------------------------------------------------------
# Public registration helper — call once after building the LLM service.
# ---------------------------------------------------------------------------

def register_intelligence_tools(llm: Any, rtvi: RTVIProcessor) -> None:
    """Register all five intelligence tool handlers on the LLM service.

    Mirrors teammate's pattern:

        llm.register_function("set_active_location", _make_…(rtvi))
        register_intelligence_tools(llm, rtvi)       # <- add this line
    """
    llm.register_function("get_location_assessment", _make_get_assessment_handler(rtvi))
    llm.register_function("get_cascade_analysis", _make_get_cascade_handler(rtvi))
    llm.register_function("get_adversary_actions", _make_get_adversary_actions_handler(rtvi))
    llm.register_function("compare_all_locations", _make_compare_locations_handler(rtvi))
    llm.register_function("get_live_situation", _make_get_live_situation_handler(rtvi))
    logger.info("Registered 5 GHOSTLINE intelligence tools (voice_server={})", VOICE_SERVER_URL)
