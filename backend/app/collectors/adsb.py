from datetime import datetime, timezone

from app.collectors.base import BaseCollector
from app.models.finding import Finding, GeoPoint
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload


class ADSBCollector(BaseCollector):
    source = "adsb"

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        finding = Finding(
            source="adsb",
            title="Repeated aircraft approach pattern",
            severity="medium",
            summary="Flight-track clustering suggests regular aviation activity that could aid timing analysis.",
            geo=GeoPoint(lat=request.target.lat + 0.05, lon=request.target.lon - 0.04),
            ts=datetime.now(timezone.utc),
            metadata={"status": "stub", "collector": self.source},
        )
        layer = MapLayerPayload(
            id="adsb-paths",
            type="path",
            data=[
                {
                    "path": [
                        [request.target.lon - 0.1, request.target.lat - 0.08],
                        [request.target.lon, request.target.lat],
                        [request.target.lon + 0.12, request.target.lat + 0.04],
                    ]
                }
            ],
        )
        return [finding], [layer]
