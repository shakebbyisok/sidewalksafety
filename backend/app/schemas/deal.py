from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class DealBase(BaseModel):
    business_name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    county: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    category: Optional[str] = None


class DealCreate(DealBase):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    places_id: Optional[str] = None
    apollo_id: Optional[str] = None


class DealResponse(DealBase):
    id: UUID
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    places_id: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GeographicSearchRequest(BaseModel):
    area_type: str  # "zip" or "county"
    value: str  # zip code or county name
    state: Optional[str] = None  # Required if county


class GeographicSearchResponse(BaseModel):
    job_id: str
    status: str
    message: str


class DealMapResponse(BaseModel):
    """Deal response optimized for map display."""
    id: UUID
    business_name: str
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str
    deal_score: Optional[float] = None
    estimated_job_value: Optional[float] = None
    damage_severity: Optional[str] = None

    class Config:
        from_attributes = True

