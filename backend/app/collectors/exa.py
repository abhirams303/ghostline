from datetime import datetime, timezone

from app.collectors.base import BaseCollector
from app.models.finding import Finding
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload


class ExaCollector(BaseCollector):
    source = "exa"

    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        finding = Finding(
            source="exa",
            title="Open-source chatter placeholder",
            severity="low",
            summary="News and public-web enrichment is scaffolded but disabled by default in this outline.",
            ts=datetime.now(timezone.utc),
            metadata={"status": "stub", "collector": self.source},
        )
        return [finding], []
