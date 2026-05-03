from datetime import datetime, timezone
from typing import Any

import httpx

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload
from app.utils.geo import haversine_km, km_to_nautical_miles


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_altitude_ft(value: Any) -> float | None:
    if value is None:
        return None
    if value == "ground":
        return 0.0
    return _to_float(value)


class ADSBCollector(BaseCollector):
    source = "adsb"

    async def _fetch_aircraft_payload(self, request: AnalyzeRequest) -> dict[str, Any]:
        settings = get_settings()
        radius_nm = max(1, round(km_to_nautical_miles(request.target.radius_km)))
        url = (
            f"{settings.adsb_base_url.rstrip('/')}/api/aircraft/"
            f"lat/{request.target.lat}/lon/{request.target.lon}/dist/{radius_nm}/"
        )

        async with httpx.AsyncClient(timeout=settings.adsb_timeout_seconds) as client:
            response = await client.get(
                url,
                headers={"api-auth": settings.adsbexchange_api_key or ""},
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_aircraft(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("ac", "aircraft"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
        return []

    def _build_layers(
        self,
        aircraft_rows: list[dict[str, Any]],
    ) -> list[MapLayerPayload]:
        settings = get_settings()
        markers: list[dict[str, Any]] = []

        for aircraft in aircraft_rows[: settings.adsb_max_aircraft]:
            lat = _to_float(aircraft.get("lat"))
            lon = _to_float(aircraft.get("lon"))
            if lat is None or lon is None:
                continue

            markers.append(
                {
                    "hex": aircraft.get("hex"),
                    "flight": (aircraft.get("flight") or aircraft.get("callsign") or "").strip(),
                    "position": [lon, lat],
                    "altitudeFt": _to_altitude_ft(aircraft.get("alt_baro")),
                    "groundSpeedKts": _to_float(aircraft.get("gs")),
                    "trackDeg": _to_float(aircraft.get("track")),
                    "seenSeconds": _to_float(aircraft.get("seen")),
                }
            )

        if not markers:
            return []

        return [
            MapLayerPayload(
                id="adsb-live-markers",
                type="marker",
                data=markers,
            )
        ]

    def _build_findings(
        self,
        request: AnalyzeRequest,
        aircraft_rows: list[dict[str, Any]],
    ) -> list[Finding]:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        normalized_rows: list[dict[str, Any]] = []

        for aircraft in aircraft_rows:
            lat = _to_float(aircraft.get("lat"))
            lon = _to_float(aircraft.get("lon"))
            if lat is None or lon is None:
                continue

            normalized_rows.append(
                {
                    "hex": aircraft.get("hex"),
                    "flight": (aircraft.get("flight") or aircraft.get("callsign") or "").strip(),
                    "lat": lat,
                    "lon": lon,
                    "altitude_ft": _to_altitude_ft(aircraft.get("alt_baro")),
                    "distance_km": haversine_km(request.target.lat, request.target.lon, lat, lon),
                }
            )

        if not normalized_rows:
            return []

        total = len(normalized_rows)
        inner_ring_km = max(3.0, request.target.radius_km * 0.4)
        close_count = sum(1 for aircraft in normalized_rows if aircraft["distance_km"] <= inner_ring_km)
        low_altitude_count = sum(
            1
            for aircraft in normalized_rows
            if aircraft["altitude_ft"] is not None
            and aircraft["altitude_ft"] <= settings.adsb_low_altitude_threshold_ft
        )

        severity = "medium"
        if close_count >= 8 or low_altitude_count >= 5:
            severity = "high"
        elif total <= 3 and low_altitude_count == 0:
            severity = "low"

        findings = [
            Finding(
                source="adsb",
                title="Visible aircraft activity near target area",
                severity=severity,
                summary=(
                    f"Live ADS-B snapshot returned {total} aircraft within {request.target.radius_km:.0f} km of "
                    f"{request.target.name}, with {close_count} inside the inner exposure ring and "
                    f"{low_altitude_count} at or below {settings.adsb_low_altitude_threshold_ft} ft."
                ),
                evidence_url=(
                    f"https://globe.adsbexchange.com/?lat={request.target.lat}&lon={request.target.lon}&zoom=9"
                ),
                geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                ts=now,
                metadata={
                    "collector": self.source,
                    "aircraft_count": total,
                    "inner_ring_count": close_count,
                    "low_altitude_count": low_altitude_count,
                },
            )
        ]

        low_altitude_examples = [
            aircraft
            for aircraft in normalized_rows
            if aircraft["altitude_ft"] is not None
            and aircraft["altitude_ft"] <= settings.adsb_low_altitude_threshold_ft
        ][:3]

        if low_altitude_examples:
            findings.append(
                Finding(
                    source="adsb",
                    title="Low-altitude public traffic contributes to aerial visibility",
                    severity="medium" if low_altitude_count < 5 else "high",
                    summary=(
                        f"At least {low_altitude_count} aircraft in the snapshot were at or below "
                        f"{settings.adsb_low_altitude_threshold_ft} ft. Examples: "
                        f"{', '.join((aircraft['flight'] or aircraft['hex'] or 'unknown-aircraft') for aircraft in low_altitude_examples)}."
                    ),
                    evidence_url=(
                        f"https://globe.adsbexchange.com/?lat={request.target.lat}&lon={request.target.lon}&zoom=9"
                    ),
                    geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                    ts=now,
                    metadata={"collector": self.source},
                )
            )

        return findings

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        settings = get_settings()
        if not settings.adsb_enabled or not settings.adsbexchange_api_key:
            return [], []

        try:
            payload = await self._fetch_aircraft_payload(request)
        except httpx.HTTPError:
            return [], []

        aircraft_rows = self._extract_aircraft(payload)
        findings = self._build_findings(request, aircraft_rows)
        layers = self._build_layers(aircraft_rows)
        return findings, layers
