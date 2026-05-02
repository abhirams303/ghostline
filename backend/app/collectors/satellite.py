from datetime import datetime, timedelta, timezone

from app.collectors.base import BaseCollector
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload


class SatelliteCollector(BaseCollector):
    source = "satellite"

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        next_pass = datetime.now(timezone.utc) + timedelta(hours=6)
        finding = Finding(
            source="satellite",
            title="Commercial revisit window within 6 hours",
            severity="medium",
            summary="Cached orbital estimate suggests another collection opportunity later today.",
            geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
            ts=next_pass,
            metadata={"status": "stub", "collector": self.source, "next_pass": next_pass.isoformat()},
        )
        layer = MapLayerPayload(
            id="satellite-footprint",
            type="footprint",
            data=[
                {
                    "center": [request.target.lon, request.target.lat],
                    "radiusKm": request.target.radius_km * 0.8,
                }
            ],
        )
        return [finding], [layer]
