from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.core.geocoding_service import geocoding_service

router = APIRouter()


class ReverseGeocodeRequest(BaseModel):
    latitude: float
    longitude: float


class ReverseGeocodeResponse(BaseModel):
    formatted_address: str
    zip: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    place_id: Optional[str] = None


@router.post("/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(request: ReverseGeocodeRequest):
    """Reverse geocode coordinates to get ZIP code, county, etc."""
    result = await geocoding_service.reverse_geocode(request.latitude, request.longitude)
    
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Could not reverse geocode coordinates"
        )
    
    return ReverseGeocodeResponse(
        formatted_address=result.get("formatted_address", ""),
        zip=result.get("zip"),
        county=result.get("county"),
        state=result.get("state"),
        city=result.get("city"),
        place_id=result.get("place_id"),
    )

