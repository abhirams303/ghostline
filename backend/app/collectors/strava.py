from datetime import datetime, timezone

from app.collectors.base import BaseCollector
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload


class StravaCollector(BaseCollector):
    source = "strava"

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        finding = Finding(
            source="strava",
            title="Mobility heat signature near target perimeter",
            severity="high",
            summary="Exercise traces indicate repeated movement corridors adjacent to the target area.",
            geo=GeoPoint(lat=request.target.lat, lon=request.target.lon),
            ts=datetime.now(timezone.utc),
            metadata={"status": "stub", "collector": self.source},
        )
        layer = MapLayerPayload(
            id="strava-heatmap",
            type="heatmap",
            data=[
                {
                    "position": [request.target.lon, request.target.lat],
                    "weight": 0.9,
                }
            ],
        )
        return [finding], [layer]
