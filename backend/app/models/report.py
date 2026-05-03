from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.finding import Finding
from app.models.location import LocationInput


class ScoreBreakdown(BaseModel):
    movement: int = 0
    personnel: int = 0
    facility: int = 0
    aerial: int = 0
    aggregate: int = 0


class MapLayerPayload(BaseModel):
    id: str
    type: Literal["heatmap", "path", "marker", "polygon", "footprint"]
    visible: bool = True
    data: list[dict] = Field(default_factory=list)


class SourceStatus(BaseModel):
    source: Literal["strava", "adsb", "satellite", "exa"]
    status: Literal["ok", "disabled", "missing_config", "upstream_error", "no_data"]
    message: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    run_id: str
    target: LocationInput
    mode: Literal["demo", "live"]
    generated_at: datetime
    score: ScoreBreakdown
    findings: list[Finding]
    layers: list[MapLayerPayload]
    source_statuses: list[SourceStatus] = Field(default_factory=list)
    narrative_preview: str
    ethics_banner: str = (
        "For defensive OPSEC assessment only. Do not use to target or facilitate harm."
    )
