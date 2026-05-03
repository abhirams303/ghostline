from fastapi import APIRouter, HTTPException, Query

from app.models.location import LocationInput
from app.utils.geocoder import GeocodeError, geocode_location

router = APIRouter(prefix="/geocode", tags=["geocode"])


@router.get("", response_model=LocationInput)
async def geocode(q: str = Query(..., description="Free-form location query.")) -> LocationInput:
    if not q.strip():
        raise HTTPException(status_code=400, detail="Geocode query cannot be blank.")

    try:
        target = await geocode_location(q)
    except GeocodeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if target is None:
        raise HTTPException(status_code=404, detail="Location could not be resolved.")

    return target
