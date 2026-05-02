from typing import Literal

from pydantic import BaseModel, Field


class RoutePoint(BaseModel):
    lat: float
    lon: float


class LocationInput(BaseModel):
    name: str = Field(..., description="Human-readable target name.")
    lat: float
    lon: float
    radius_km: float = Field(default=15, ge=1, le=250)


class AnalyzeRequest(BaseModel):
    target: LocationInput
    mode: Literal["demo", "live"] = "demo"
    route: list[RoutePoint] = Field(default_factory=list)
    unit_id: str | None = None

