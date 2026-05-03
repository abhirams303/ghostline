from fastapi import APIRouter, HTTPException, Query

from app.collectors.strava import collect_strava_heatmap

router = APIRouter(prefix="/collect", tags=["collect"])


@router.post("/strava")
async def collect_strava(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    zoom: int = Query(13, ge=1, le=20),
) -> dict:
    try:
        return await collect_strava_heatmap(lat=lat, lon=lon, zoom=zoom)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

