"""LLM threat brief generator.

Takes the per-layer collector output, computes the composite exposure score
locally (deterministic), and asks GPT-4 to produce a terse, military-style
spoken brief. The brief is the most demo-critical artifact in the system —
it is what the judges hear out loud.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .score_calculator import calculate_exposure_score

load_dotenv()

MODEL = "gpt-4o"

SYSTEM_PROMPT = """You are a military intelligence officer delivering an OPSEC exposure brief to a base commander. The brief will be SPOKEN ALOUD by a TTS voice, so it must read like a real intel dictation — not prose, not a data dump.

VOICE AND TONE
- Address the listener as "Commander" exactly once, at the open.
- Terse, declarative, tactical. Sentence fragments are acceptable.
- Use military severity tags: CRITICAL, HIGH, MODERATE, MINIMAL.
- Never use hedge words: "appears", "potentially", "it seems", "I noticed", "could possibly".
- Never sound like ChatGPT. No "I've analyzed", no "based on the data", no closing pleasantries.

STRUCTURE (in this order)
1. Situation: one sentence naming the location and the OPERATIONAL IMPACT of the highest-severity finding. Do NOT just name the layer. Describe what an adversary can DO with the exposure.
   GOOD: "CRITICAL: predictable personnel movement patterns at Fort Liberty are publicly visible and exploitable."
   BAD:  "CRITICAL exposure via Strava."
2. Exposure Vectors: each layer (Fitness activity / Aircraft / Satellite imaging) on its own line, ordered HIGHEST severity first. Lead each line with the severity tag, then the layer name. Then EXPLAIN WHAT THE DATA MEANS operationally — what an adversary can infer or do — embedding the actual numbers, callsigns, hotspots, hours, and pass-windows naturally inside that explanation. Never quote the raw "score" values (e.g. "density score 78"); translate them into operational language.
   GOOD: "47 distinct exercise routes publicly visible via Strava heatmap, concentrated at eastern perimeter and main gate. Peak activity 0600 to 0700 daily. An adversary can predict personnel movement to 15-minute precision."
   BAD:  "Strava density score 78, 47 routes, hotspots at eastern perimeter."
3. Composite: one line stating the composite exposure score (out of 100) and risk level.
4. Recommended Actions: 3 to 5 numbered actions, most impactful first. Each action must be SPECIFIC and IMPERATIVE — name the unit, the system, the timeline, or the target. No generic verbs.
   GOOD: "Direct all personnel to set Strava profiles to private within 24 hours. Priority enforcement: eastern perimeter units."
   BAD:  "Restrict Strava use."

RULES
- TARGET LENGTH: 160 to 190 words. The brief must be substantial enough to fill 20 to 25 seconds of spoken audio. If your first draft is under 150 words, EXPAND the exposure vector descriptions with operational context (what an adversary can do with this data, what the timing implies, what the pattern reveals). Do not pad with filler — add intelligence value.
- If a layer's score is 0 or its data is empty, mark it MINIMAL and frame as a positive: "MINIMAL — no recurring military flight patterns detected on public ADS-B feeds."
- Quote specific input data where present: callsigns, peak hours, hotspots, hours-to-pass, satellite name, route counts. Embed them inside operational sentences, never as standalone numbers.
- Never reference data not in the input. Never invent callsigns, hotspots, or satellite names.

EXAMPLE BRIEF (for tone reference only — do not copy verbatim, the input data will differ):
\"\"\"
Commander. Fort Liberty, North Carolina. CRITICAL OPSEC exposure identified across three vectors.

CRITICAL — Fitness activity. 47 distinct exercise routes publicly visible via Strava heatmap, concentrated at the eastern perimeter and main gate area. Peak activity 0600 to 0700 and 1700 to 1800 daily. An adversary monitoring this data can predict personnel movement patterns to 15-minute precision.

HIGH — Aircraft. 23 military flights logged on public ADS-B trackers in the last 7 days. Callsigns SHADOW6, EAGLE7, and RADR12 appear on a recurring Tuesday-Thursday cycle between 0800 and 1200. Flight pattern is predictable and targetable.

HIGH — Satellite imaging. Sentinel-2B pass in 14.5 hours at 72 degrees elevation. Any outdoor equipment staging or vehicle movement will be commercially visible.

Composite exposure score: 73 out of 100. Risk level: HIGH.

Recommended actions. One: direct all personnel to set Strava profiles to private within 24 hours, priority enforcement at eastern perimeter units. Two: file FAA LADD blocking for callsigns SHADOW6, EAGLE7, RADR12. Three: reschedule outdoor staging to after the satellite window closes. Four: issue unit-wide OPSEC directive on personal device geotagging.
\"\"\"

OUTPUT
Return strict JSON only:
{
  "brief": "<the spoken brief, plain text with newline-separated lines>",
  "risk_level": "LOW" | "MEDIUM" | "HIGH"
}
"""


def _format_user_payload(assessment_data: dict, score_result: dict) -> str:
    """Render the input as a compact, unambiguous block for the model."""
    return json.dumps(
        {
            "location": assessment_data.get("location"),
            "lat": assessment_data.get("lat"),
            "lon": assessment_data.get("lon"),
            "layers": {
                "strava": assessment_data.get("strava", {}),
                "adsb": assessment_data.get("adsb", {}),
                "satellite": assessment_data.get("satellite", {}),
            },
            "composite": {
                "exposure_score": score_result["exposure_score"],
                "risk_level": score_result["risk_level"],
                "breakdown": score_result["breakdown"],
            },
        },
        indent=2,
    )


def _fallback_brief(assessment_data: dict, score_result: dict) -> str:
    """Used when the OpenAI call fails. Keeps the demo running."""
    location = assessment_data.get("location", "the assessed location")
    return (
        f"Commander, {location} composite exposure {score_result['exposure_score']}, "
        f"risk level {score_result['risk_level']}. "
        "Live brief generation unavailable — refer to score breakdown and mitigation panel."
    )


def generate_threat_brief(assessment_data: dict) -> dict:
    """Generate a spoken threat brief plus the composite score breakdown.

    Args:
        assessment_data: dict with keys `location`, `lat`, `lon`, and per-layer
            blocks `strava`, `adsb`, `satellite`. Each layer block must include
            its `*_score` field (`density_score`, `predictability_score`,
            `vulnerability_score`).

    Returns:
        dict with `brief`, `exposure_score`, `risk_level`, `score_breakdown`.
    """
    strava_score = int(assessment_data.get("strava", {}).get("density_score", 0))
    adsb_score = int(assessment_data.get("adsb", {}).get("predictability_score", 0))
    satellite_score = int(
        assessment_data.get("satellite", {}).get("vulnerability_score", 0)
    )
    base_modifier = int(assessment_data.get("base_modifier", 50))

    score_result = calculate_exposure_score(
        strava_score=strava_score,
        adsb_score=adsb_score,
        satellite_score=satellite_score,
        base_modifier=base_modifier,
    )

    api_key = os.getenv("OPENAI_API_KEY")
    brief_text: str
    risk_level: str = score_result["risk_level"]

    if not api_key:
        brief_text = _fallback_brief(assessment_data, score_result)
    else:
        try:
            client = OpenAI(api_key=api_key, timeout=20.0)
            response = client.chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                temperature=0.4,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _format_user_payload(assessment_data, score_result),
                    },
                ],
            )
            raw = response.choices[0].message.content or "{}"
            parsed: dict[str, Any] = json.loads(raw)
            brief_text = parsed.get("brief") or _fallback_brief(
                assessment_data, score_result
            )
            llm_risk = str(parsed.get("risk_level", "")).upper()
            if llm_risk in {"LOW", "MEDIUM", "HIGH"}:
                risk_level = llm_risk
        except Exception as exc:  # noqa: BLE001 — demo path must not crash
            brief_text = _fallback_brief(assessment_data, score_result)
            brief_text += f"\n[debug: {type(exc).__name__}: {exc}]"

    return {
        "brief": brief_text,
        "exposure_score": score_result["exposure_score"],
        "risk_level": risk_level,
        "score_breakdown": score_result["breakdown"],
    }
