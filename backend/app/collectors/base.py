from abc import ABC, abstractmethod

from app.models.finding import Finding
from app.models.location import AnalyzeRequest
from app.models.report import MapLayerPayload


class BaseCollector(ABC):
    source: str

    @abstractmethod
    async def collect(
        self,
        request: AnalyzeRequest,
    ) -> tuple[list[Finding], list[MapLayerPayload]]:
        raise NotImplementedError
