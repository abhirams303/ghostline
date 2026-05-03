from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Any

import httpx

from app.collectors.base import BaseCollector
from app.config import get_settings
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload, SourceStatus
from app.utils.geo import haversine_km, km_to_nautical_miles

logger = logging.getLogger(__name__)


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

    def _normalize_aircraft(
        self,
        request: AnalyzeRequest,
        aircraft: dict[str, Any],
        snapshot_index: int,
    ) -> dict[str, Any] | None:
        lat = _to_float(aircraft.get("lat"))
        lon = _to_float(aircraft.get("lon"))
        if lat is None or lon is None:
            return None

        altitude_ft = _to_altitude_ft(aircraft.get("alt_baro"))
        track_deg = _to_float(aircraft.get("track"))
        distance_km = haversine_km(request.target.lat, request.target.lon, lat, lon)
        if distance_km > request.target.radius_km * 1.25:
            return None
        callsign = (aircraft.get("flight") or aircraft.get("callsign") or "").strip()
        hex_code = (aircraft.get("hex") or "").strip().lower() or None
        ident = hex_code or callsign or f"snapshot-{snapshot_index}-{lat:.4f}-{lon:.4f}"

        return {
            "id": ident,
            "hex": hex_code,
            "flight": callsign,
            "lat": lat,
            "lon": lon,
            "altitude_ft": altitude_ft,
            "ground_speed_kts": _to_float(aircraft.get("gs")),
            "track_deg": track_deg,
            "seen_seconds": _to_float(aircraft.get("seen")),
            "distance_km": distance_km,
            "snapshot_index": snapshot_index,
        }

    def _aggregate_tracks(
        self,
        request: AnalyzeRequest,
        snapshots: list[list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        aggregated: dict[str, dict[str, Any]] = {}

        for snapshot_index, aircraft_rows in enumerate(snapshots):
            for aircraft in aircraft_rows:
                normalized = self._normalize_aircraft(request, aircraft, snapshot_index)
                if not normalized:
                    continue

                key = normalized["id"]
                record = aggregated.setdefault(
                    key,
                    {
                        "id": key,
                        "hex": normalized["hex"],
                        "flight": normalized["flight"],
                        "points": [],
                        "altitudes": [],
                        "speeds": [],
                        "distances": [],
                        "tracks": [],
                    },
                )
                record["flight"] = record["flight"] or normalized["flight"]
                record["hex"] = record["hex"] or normalized["hex"]
                record["points"].append([normalized["lon"], normalized["lat"]])
                record["distances"].append(normalized["distance_km"])
                if normalized["altitude_ft"] is not None:
                    record["altitudes"].append(normalized["altitude_ft"])
                if normalized["ground_speed_kts"] is not None:
                    record["speeds"].append(normalized["ground_speed_kts"])
                if normalized["track_deg"] is not None:
                    record["tracks"].append(normalized["track_deg"])

        aircraft_summaries: list[dict[str, Any]] = []
        track_layers: list[dict[str, Any]] = []

        for record in aggregated.values():
            points = record["points"]
            avg_altitude = mean(record["altitudes"]) if record["altitudes"] else None
            avg_speed = mean(record["speeds"]) if record["speeds"] else None
            min_distance = min(record["distances"]) if record["distances"] else None
            point_count = len(points)
            heading_spread = 0.0
            if len(record["tracks"]) >= 2:
                heading_spread = max(record["tracks"]) - min(record["tracks"])

            aircraft_summary = {
                "id": record["id"],
                "hex": record["hex"],
                "flight": record["flight"],
                "position": points[-1],
                "altitudeFt": round(avg_altitude, 1)
                if avg_altitude is not None
                else None,
                "groundSpeedKts": round(avg_speed, 1)
                if avg_speed is not None
                else None,
                "minDistanceKm": round(min_distance, 2)
                if min_distance is not None
                else None,
                "sampleCount": point_count,
                "headingSpreadDeg": round(heading_spread, 1),
                "persistent": point_count > 1,
            }
            aircraft_summaries.append(aircraft_summary)

            if point_count >= 2:
                track_layers.append(
                    {
                        "path": points,
                        "flight": record["flight"],
                        "hex": record["hex"],
                        "sampleCount": point_count,
                        "minDistanceKm": round(min_distance, 2)
                        if min_distance is not None
                        else None,
                    }
                )

        aircraft_summaries.sort(
            key=lambda item: (
                item["minDistanceKm"] is None,
                item["minDistanceKm"] if item["minDistanceKm"] is not None else 999999,
                item["flight"] or item["hex"] or "",
            )
        )
        track_layers.sort(
            key=lambda item: (
                item["minDistanceKm"] is None,
                item["minDistanceKm"] if item["minDistanceKm"] is not None else 999999,
            )
        )

        return aircraft_summaries, track_layers

    def _build_layers(
        self,
        aircraft_summaries: list[dict[str, Any]],
        track_layers: list[dict[str, Any]],
    ) -> list[MapLayerPayload]:
        settings = get_settings()
        layers: list[MapLayerPayload] = []

        if aircraft_summaries:
            layers.append(
                MapLayerPayload(
                    id="adsb-live-markers",
                    type="marker",
                    data=aircraft_summaries[: settings.adsb_max_aircraft],
                )
            )

        if track_layers:
            layers.append(
                MapLayerPayload(
                    id="adsb-live-tracks",
                    type="path",
                    data=track_layers[: settings.adsb_max_aircraft],
                )
            )

        return layers

    def _build_findings(
        self,
        request: AnalyzeRequest,
        aircraft_summaries: list[dict[str, Any]],
        snapshot_count: int,
        status: SourceStatus,
    ) -> list[Finding]:
        settings = get_settings()
        now = datetime.now(timezone.utc)

        if not aircraft_summaries:
            if status.status == "no_data":
                return [
                    Finding(
                        source="adsb",
                        title="No public aircraft observed in current ADS-B window",
                        severity="low",
                        summary=(
                            f"ADS-B collection completed across {snapshot_count} sample windows but found no aircraft with valid "
                            f"positions inside the {request.target.radius_km:.0f} km search radius around {request.target.name}."
                        ),
                        evidence_url=(
                            f"https://globe.adsbexchange.com/?lat={request.target.lat}&lon={request.target.lon}&zoom=9"
                        ),
                        geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                        ts=now,
                        metadata={
                            "collector": self.source,
                            "status": status.status,
                            "snapshot_count": snapshot_count,
                            "aircraft_count": 0,
                        },
                    )
                ]
            return []

        total = len(aircraft_summaries)
        inner_ring_km = max(3.0, request.target.radius_km * 0.4)
        close_count = sum(
            1
            for aircraft in aircraft_summaries
            if aircraft["minDistanceKm"] is not None
            and aircraft["minDistanceKm"] <= inner_ring_km
        )
        low_altitude_count = sum(
            1
            for aircraft in aircraft_summaries
            if aircraft["altitudeFt"] is not None
            and aircraft["altitudeFt"] <= settings.adsb_low_altitude_threshold_ft
        )
        persistent_count = sum(
            1 for aircraft in aircraft_summaries if aircraft["sampleCount"] > 1
        )

        severity = "medium"
        if close_count >= 8 or low_altitude_count >= 5 or persistent_count >= 6:
            severity = "high"
        elif total <= 2 and low_altitude_count == 0 and persistent_count <= 1:
            severity = "low"

        findings = [
            Finding(
                source="adsb",
                title="Visible aircraft activity near target area",
                severity=severity,
                summary=(
                    f"ADS-B monitoring sampled {snapshot_count} windows and observed {total} distinct aircraft within "
                    f"{request.target.radius_km:.0f} km of {request.target.name}. {close_count} entered the inner exposure ring, "
                    f"{low_altitude_count} averaged at or below {settings.adsb_low_altitude_threshold_ft} ft, and "
                    f"{persistent_count} persisted across multiple samples."
                ),
                evidence_url=(
                    f"https://globe.adsbexchange.com/?lat={request.target.lat}&lon={request.target.lon}&zoom=9"
                ),
                geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                ts=now,
                metadata={
                    "collector": self.source,
                    "status": status.status,
                    "snapshot_count": snapshot_count,
                    "aircraft_count": total,
                    "inner_ring_count": close_count,
                    "low_altitude_count": low_altitude_count,
                    "persistent_count": persistent_count,
                },
            )
        ]

        persistent_examples = [
            aircraft for aircraft in aircraft_summaries if aircraft["sampleCount"] > 1
        ][:3]
        if persistent_examples:
            findings.append(
                Finding(
                    source="adsb",
                    title="Repeated aircraft presence indicates persistent aerial visibility",
                    severity="medium" if persistent_count < 4 else "high",
                    summary=(
                        f"{persistent_count} aircraft were observed in more than one ADS-B sample window. Examples: "
                        f"{', '.join((aircraft['flight'] or aircraft['hex'] or 'unknown-aircraft') for aircraft in persistent_examples)}."
                    ),
                    evidence_url=(
                        f"https://globe.adsbexchange.com/?lat={request.target.lat}&lon={request.target.lon}&zoom=9"
                    ),
                    geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                    ts=now,
                    metadata={
                        "collector": self.source,
                        "status": status.status,
                        "persistent_count": persistent_count,
                    },
                )
            )

        low_altitude_examples = [
            aircraft
            for aircraft in aircraft_summaries
            if aircraft["altitudeFt"] is not None
            and aircraft["altitudeFt"] <= settings.adsb_low_altitude_threshold_ft
        ][:3]
        if low_altitude_examples:
            findings.append(
                Finding(
                    source="adsb",
                    title="Low-altitude public traffic contributes to aerial visibility",
                    severity="medium" if low_altitude_count < 5 else "high",
                    summary=(
                        f"At least {low_altitude_count} distinct aircraft averaged at or below "
                        f"{settings.adsb_low_altitude_threshold_ft} ft during the sample window. Examples: "
                        f"{', '.join((aircraft['flight'] or aircraft['hex'] or 'unknown-aircraft') for aircraft in low_altitude_examples)}."
                    ),
                    evidence_url=(
                        f"https://globe.adsbexchange.com/?lat={request.target.lat}&lon={request.target.lon}&zoom=9"
                    ),
                    geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                    ts=now,
                    metadata={
                        "collector": self.source,
                        "status": status.status,
                        "low_altitude_count": low_altitude_count,
                    },
                )
            )

        return findings

    async def _collect_snapshots(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[list[dict[str, Any]]], SourceStatus]:
        settings = get_settings()

        if not settings.adsb_enabled:
            return [], SourceStatus(
                source="adsb",
                status="disabled",
                message="ADS-B collection is disabled by configuration.",
                details={"enabled": False},
            )

        if not settings.adsbexchange_api_key:
            return [], SourceStatus(
                source="adsb",
                status="missing_config",
                message="ADS-B Exchange API key is not configured.",
                details={"api_key_present": False},
            )

        snapshots: list[list[dict[str, Any]]] = []

        for sample_index in range(max(1, settings.adsb_snapshot_samples)):
            try:
                payload = await self._fetch_aircraft_payload(request)
            except httpx.TimeoutException:
                logger.warning("ADS-B snapshot %s timed out", sample_index + 1)
                return snapshots, SourceStatus(
                    source="adsb",
                    status="upstream_error",
                    message="ADS-B upstream request timed out.",
                    details={"sample_index": sample_index + 1},
                )
            except httpx.HTTPError as exc:
                logger.warning("ADS-B snapshot %s failed: %s", sample_index + 1, exc)
                return snapshots, SourceStatus(
                    source="adsb",
                    status="upstream_error",
                    message="ADS-B upstream request failed.",
                    details={"sample_index": sample_index + 1},
                )
            except ValueError:
                logger.warning(
                    "ADS-B snapshot %s returned malformed JSON", sample_index + 1
                )
                return snapshots, SourceStatus(
                    source="adsb",
                    status="upstream_error",
                    message="ADS-B upstream returned malformed data.",
                    details={"sample_index": sample_index + 1},
                )

            aircraft_rows = self._extract_aircraft(payload)
            snapshots.append(aircraft_rows)

            if (
                sample_index + 1 < settings.adsb_snapshot_samples
                and settings.adsb_snapshot_interval_seconds > 0
            ):
                await asyncio.sleep(settings.adsb_snapshot_interval_seconds)

        total_rows = sum(len(snapshot) for snapshot in snapshots)
        status = SourceStatus(
            source="adsb",
            status="ok" if total_rows > 0 else "no_data",
            message=(
                "ADS-B collection completed successfully."
                if total_rows > 0
                else "ADS-B collection completed but returned no aircraft data."
            ),
            details={
                "sample_count": len(snapshots),
                "raw_aircraft_rows": total_rows,
            },
        )
        return snapshots, status

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        snapshots, status = await self._collect_snapshots(request)
        if status.status in {"disabled", "missing_config", "upstream_error"}:
            return [
                Finding(
                    source="adsb",
                    title="ADS-B collection unavailable",
                    severity="low",
                    summary=status.message,
                    evidence_url=None,
                    geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
                    ts=datetime.now(timezone.utc),
                    metadata={
                        "collector": self.source,
                        "status": status.status,
                        **status.details,
                    },
                )
            ], []

        aircraft_summaries, track_layers = self._aggregate_tracks(request, snapshots)
        findings = self._build_findings(
            request, aircraft_summaries, len(snapshots), status
        )
        layers = self._build_layers(aircraft_summaries, track_layers)
        return findings, layers
