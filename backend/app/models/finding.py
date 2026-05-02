from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GeoPoint(BaseModel):
    lat: float
    lon: float


class Finding(BaseModel):
    source: Literal["strava", "adsb", "satellite", "exa", "system"]
    title: str
    severity: Literal["low", "medium", "high", "critical"]
    summary: str
    evidence_url: str | None = None
    geo: GeoPoint | None = None
    ts: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
