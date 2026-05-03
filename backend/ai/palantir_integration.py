"""Palantir Foundry REST client — Bearer-token, no SDK, no OAuth.

Reads FOUNDRY_HOSTNAME, FOUNDRY_TOKEN, and FOUNDRY_ONTOLOGY_RID from the
project-root .env file. All ontology writes go through apply_action(); reads
go through get_object / list_objects / get_linked_objects.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — action and link apiNames (verified against live tenant)
# ---------------------------------------------------------------------------

ACTIONS: dict[str, str] = {
    "GhostlineGeoFeature":  "create-ghostline-geo-feature",
    "GhostlineUnit":        "create-ghostline-unit",
    "GhostlinePlatform":    "create-ghostline-platform",
    "GhostlineSensor":      "create-ghostline-sensor",
    "GhostlineCommsAsset":  "create-ghostline-comms-asset",
    "CascadeRisk":          "create-cascade-risk",
    "AdversaryAction":      "create-adversary-action",
    "OpsecAssessment":      "create-opsec-assessment",
}

# Forward direction (source points to a single target)
LINKS_FORWARD: dict[tuple[str, str], str] = {
    ("GhostlineUnit",       "GhostlineGeoFeature"): "geoFeature",
    ("GhostlineCommsAsset", "GhostlineGeoFeature"): "geoFeature",
    ("GhostlinePlatform",   "GhostlineUnit"):       "platforms",
    ("GhostlineSensor",     "GhostlinePlatform"):   "sensors",
    ("CascadeRisk",         "GhostlineGeoFeature"): "cascadeRisks",
    ("CascadeRisk",         "OpsecAssessment"):     "analyzedCascadeRisks",
    ("AdversaryAction",     "CascadeRisk"):         "adversaryActions",
}

# Reverse direction (collection — one-to-many fanouts)
LINKS_REVERSE: dict[tuple[str, str], str] = {
    ("GhostlineGeoFeature", "GhostlineUnit"):       "units",
    ("GhostlineGeoFeature", "GhostlineCommsAsset"): "commsAssets",
    ("GhostlineGeoFeature", "CascadeRisk"):         "geoFeature",
    ("GhostlineUnit",       "GhostlinePlatform"):   "unit",
    ("GhostlinePlatform",   "GhostlineSensor"):     "platform",
    ("CascadeRisk",         "AdversaryAction"):     "cascadeRisk",
    ("OpsecAssessment",     "CascadeRisk"):         "opsecAssessment",
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FoundryError(RuntimeError):
    """Foundry-specific failure (HTTP error, missing config, etc.)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WRAP_PAIRS = (("<", ">"), ('"', '"'), ("'", "'"), ("`", "`"))


def _strip_wrappers(value: str) -> str:
    """Strip whitespace and a single pair of wrapping <>, "", '', or `` chars."""
    v = value.strip()
    for left, right in _WRAP_PAIRS:
        if len(v) >= 2 and v.startswith(left) and v.endswith(right):
            v = v[1:-1].strip()
            break
    return v


def _normalize_hostname(raw: str) -> str:
    h = _strip_wrappers(raw)
    for prefix in ("https://", "http://"):
        if h.startswith(prefix):
            h = h[len(prefix):]
    return h.rstrip("/")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FoundryClient:
    """Minimal Foundry REST client using a static Bearer token."""

    _RETRY_STATUSES = {429, 500, 502, 503, 504}
    _MAX_ATTEMPTS = 3

    def __init__(
        self,
        hostname: Optional[str] = None,
        token: Optional[str] = None,
        ontology_rid: Optional[str] = None,
        timeout: int = 10,
    ) -> None:
        import os

        raw_host = hostname or os.getenv("FOUNDRY_HOSTNAME", "")
        raw_token = token or os.getenv("FOUNDRY_TOKEN", "")
        raw_rid = ontology_rid or os.getenv("FOUNDRY_ONTOLOGY_RID", "")

        host = _normalize_hostname(raw_host)
        tok = _strip_wrappers(raw_token)
        rid = _strip_wrappers(raw_rid)

        if not host:
            raise FoundryError("FOUNDRY_HOSTNAME is not set or empty")
        if not tok:
            raise FoundryError("FOUNDRY_TOKEN is not set or empty")
        if not rid:
            raise FoundryError("FOUNDRY_ONTOLOGY_RID is not set or empty")

        self._base = f"https://{host}"
        self._rid = rid
        self._timeout = timeout

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {tok}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Internal retry helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> requests.Response:
        url = f"{self._base}{path}"
        delay = 1.0
        last_exc: Optional[Exception] = None

        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                resp = self._session.request(
                    method, url, params=params, json=json, timeout=self._timeout
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self._MAX_ATTEMPTS:
                    log.debug("Attempt %d/%d failed (network): %s — retrying in %.0fs",
                              attempt, self._MAX_ATTEMPTS, exc, delay)
                    time.sleep(delay)
                    delay *= 2
                continue

            if resp.status_code not in self._RETRY_STATUSES:
                return resp

            if attempt < self._MAX_ATTEMPTS:
                log.debug("Attempt %d/%d got HTTP %d — retrying in %.0fs",
                          attempt, self._MAX_ATTEMPTS, resp.status_code, delay)
                time.sleep(delay)
                delay *= 2
            else:
                body_preview = (resp.text or "")[:500]
                log.error("Terminal failure HTTP %d for %s %s: %s",
                          resp.status_code, method, url, body_preview)
                raise FoundryError(
                    f"HTTP {resp.status_code} from {method} {url}: {body_preview}"
                )

        # Reached only if all attempts raised RequestException
        raise FoundryError(
            f"Network error after {self._MAX_ATTEMPTS} attempts on {method} {url}: {last_exc}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_action(self, action_apiname: str, parameters: dict) -> dict:
        """Invoke a Foundry action and return the parsed JSON response."""
        log.info("Invoking action: %s", action_apiname)
        path = f"/api/v2/ontologies/{self._rid}/actions/{action_apiname}/apply"
        body = {"parameters": parameters, "options": {"returnEdits": "ALL"}}
        resp = self._request("POST", path, json=body)
        if not resp.ok:
            body_preview = (resp.text or "")[:500]
            log.error("Action %s failed HTTP %d: %s", action_apiname, resp.status_code, body_preview)
            raise FoundryError(
                f"HTTP {resp.status_code} applying action '{action_apiname}': {body_preview}"
            )
        return resp.json() if resp.text.strip() else {}

    def get_object(self, object_type: str, primary_key: str) -> Optional[dict]:
        """Fetch a single object by primary key. Returns None on 404."""
        path = f"/api/v2/ontologies/{self._rid}/objects/{object_type}/{primary_key}"
        resp = self._request("GET", path)
        if resp.status_code == 404:
            return None
        if not resp.ok:
            raise FoundryError(
                f"HTTP {resp.status_code} fetching {object_type}/{primary_key}: "
                f"{(resp.text or '')[:500]}"
            )
        return resp.json()

    def list_objects(self, object_type: str, page_size: int = 50) -> list[dict]:
        """Return the first page of objects of the given type."""
        path = f"/api/v2/ontologies/{self._rid}/objects/{object_type}"
        resp = self._request("GET", path, params={"pageSize": page_size})
        if not resp.ok:
            raise FoundryError(
                f"HTTP {resp.status_code} listing {object_type}: "
                f"{(resp.text or '')[:500]}"
            )
        return (resp.json() or {}).get("data", [])

    def get_linked_objects(
        self,
        source_type: str,
        source_pk: str,
        link_apiname: str,
        page_size: int = 50,
    ) -> list[dict]:
        """Return linked objects. Returns [] on 404."""
        path = (
            f"/api/v2/ontologies/{self._rid}/objects/"
            f"{source_type}/{source_pk}/links/{link_apiname}"
        )
        resp = self._request("GET", path, params={"pageSize": page_size})
        if resp.status_code == 404:
            return []
        if not resp.ok:
            raise FoundryError(
                f"HTTP {resp.status_code} fetching links "
                f"{source_type}/{source_pk}/{link_apiname}: "
                f"{(resp.text or '')[:500]}"
            )
        return (resp.json() or {}).get("data", [])


# ---------------------------------------------------------------------------
# Backward-compatible smoke-test helper
# ---------------------------------------------------------------------------

def write_assessment_to_palantir(assessment: dict) -> bool:
    """Legacy helper used by backend.ai.test_all.

    Newer writeback paths use the explicit assessment_writeback module. This
    wrapper keeps the historical smoke script importable and preserves its
    "skip without creds" behavior.
    """
    try:
        client = FoundryClient()
    except FoundryError as exc:
        log.warning("Skipping Palantir write: %s", exc)
        return False

    score_breakdown = assessment.get("score_breakdown") or {}
    location = str(assessment.get("location") or "Unknown")
    safe_location = "".join(ch.lower() if ch.isalnum() else "-" for ch in location).strip("-") or "unknown"
    params = {
        "assessment-id": assessment.get("assessment_id") or f"smoke-{safe_location}-{int(time.time())}",
        "location-name": location,
        "assessment-timestamp": assessment.get("assessment_timestamp") or datetime.now(timezone.utc).isoformat(),
        "exposure-score": int(assessment.get("exposure_score") or 0),
        "aircraft-predictability-score": int(
            score_breakdown.get("adsb") or score_breakdown.get("aircraft") or 0
        ),
        "satellite-vulnerability-score": int(
            score_breakdown.get("satellite") or score_breakdown.get("facility") or 0
        ),
        "strava-density-score": int(score_breakdown.get("strava") or score_breakdown.get("movement") or 0),
        "latitude": float(assessment.get("lat") or 0.0),
        "longitude": float(assessment.get("lon") or 0.0),
        "threat-brief": str(assessment.get("brief") or ""),
    }

    try:
        client.apply_action(ACTIONS["OpsecAssessment"], params)
    except FoundryError as exc:
        log.error("Palantir assessment smoke write failed: %s", exc)
        return False
    return True


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.WARNING)
    try:
        client = FoundryClient()
        objects = client.list_objects("OpsecAssessment", page_size=1)
        print(f"OK: client works ({len(objects)} OpsecAssessment objects in tenant)")
    except FoundryError as exc:
        print(f"FoundryError: {exc}", file=sys.stderr)
        sys.exit(1)
