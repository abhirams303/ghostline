"""Palantir Foundry write path — STUB.

Once the Foundry team hands over Developer Console credentials, fill in the
constants below and the `_invoke_create_action` body. Until then,
`write_assessment_to_palantir` logs the payload and returns False so the
demo flow keeps moving when run without Foundry.

What we need from the Palantir team onsite
-------------------------------------------
1. OAuth client_id + client_secret  (Developer Console → "Create application").
   Scopes required:
     - api:ontologies-read
     - api:ontologies-write
2. Ontology RID  (the NatSec Hackathon Ontology)         e.g. "ri.ontology.main.ontology.<uuid>"
3. Action API name for "Create OPSEC Assessment"         e.g. "create-opsec-assessment"
4. Action API name for "Update Exposure Score"           e.g. "update-exposure-score"
5. The OSDK package name generated for our project       (installed via
   `pip install <package-from-foundry>` — Foundry serves it directly).

Environment variables to set
----------------------------
    FOUNDRY_HOST=https://nshackathon.palantirfoundry.com
    FOUNDRY_CLIENT_ID=...
    FOUNDRY_CLIENT_SECRET=...
    FOUNDRY_ONTOLOGY_RID=...

OSDK call sketch (fill in once package is installed)
----------------------------------------------------
    from foundry_sdk_runtime.auth import ConfidentialClientAuth
    from <generated_osdk_pkg> import FoundryClient
    from <generated_osdk_pkg>.ontology.actions import create_opsec_assessment

    auth = ConfidentialClientAuth(
        client_id=os.environ["FOUNDRY_CLIENT_ID"],
        client_secret=os.environ["FOUNDRY_CLIENT_SECRET"],
        hostname=os.environ["FOUNDRY_HOST"],
        scopes=["api:ontologies-read", "api:ontologies-write"],
    )
    client = FoundryClient(auth=auth, hostname=os.environ["FOUNDRY_HOST"])
    client.ontology.actions.create_opsec_assessment(
        assessment_id=...,
        location_name=...,
        latitude=...,
        longitude=...,
        exposure_score=...,
        strava_density_score=...,
        aircraft_predictability_score=...,
        satellite_vulnerability_score=...,
        assessment_timestamp=...,
        threat_brief=...,
    )
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

FOUNDRY_HOST = os.getenv("FOUNDRY_HOST", "https://nshackathon.palantirfoundry.com")
FOUNDRY_CLIENT_ID = os.getenv("FOUNDRY_CLIENT_ID")
FOUNDRY_CLIENT_SECRET = os.getenv("FOUNDRY_CLIENT_SECRET")
FOUNDRY_ONTOLOGY_RID = os.getenv("FOUNDRY_ONTOLOGY_RID")


def _build_action_payload(assessment_result: dict) -> dict:
    """Map our internal assessment result to the OPSEC Assessment action params."""
    breakdown = assessment_result.get("score_breakdown", {})

    def _raw(layer: str) -> int:
        return int(breakdown.get(layer, {}).get("raw", 0))

    return {
        "assessment_id": assessment_result.get("assessment_id") or str(uuid.uuid4()),
        "location_name": assessment_result.get("location", "UNKNOWN"),
        "latitude": float(assessment_result.get("lat", 0.0)),
        "longitude": float(assessment_result.get("lon", 0.0)),
        "exposure_score": int(assessment_result.get("exposure_score", 0)),
        "strava_density_score": _raw("strava"),
        "aircraft_predictability_score": _raw("adsb"),
        "satellite_vulnerability_score": _raw("satellite"),
        "assessment_timestamp": assessment_result.get(
            "assessment_timestamp"
        )
        or datetime.now(timezone.utc).isoformat(),
        "threat_brief": assessment_result.get("brief", ""),
    }


def _invoke_create_action(payload: dict) -> bool:
    """TODO: replace this stub with a real OSDK call once credentials land.

    See the module docstring for the exact code to drop in here.
    """
    raise NotImplementedError(
        "Palantir OSDK call not wired yet — see backend/ai/palantir_integration.py "
        "module docstring for the credentials and code we need."
    )


def write_assessment_to_palantir(assessment_result: dict) -> bool:
    """Push an assessment object into the OPSEC Assessment ontology.

    Returns True on a successful write, False on any failure. Never raises —
    the demo path must continue even when Foundry is unreachable.
    """
    payload = _build_action_payload(assessment_result)

    if not (FOUNDRY_CLIENT_ID and FOUNDRY_CLIENT_SECRET and FOUNDRY_ONTOLOGY_RID):
        log.warning(
            "Palantir credentials not configured — skipping write for %s",
            payload["location_name"],
        )
        log.info("Would-write payload: %s", payload)
        return False

    try:
        return bool(_invoke_create_action(payload))
    except NotImplementedError as exc:
        log.warning("Palantir write skipped: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("Palantir write failed: %s", exc)
        return False
