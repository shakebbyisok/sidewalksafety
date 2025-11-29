from pydantic import BaseModel, Field
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
    has_property_verified: Optional[bool] = False
    property_verification_method: Optional[str] = None
    property_type: Optional[str] = "parking_lot"


class DealResponse(DealBase):
    id: UUID
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    places_id: Optional[str] = None
    status: str
    has_property_verified: bool
    property_verification_method: Optional[str] = None
    property_type: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GeographicSearchRequest(BaseModel):
    area_type: str  # "zip" or "county"
    value: str  # zip code or county name
    state: Optional[str] = None  # Required if county
    max_deals: Optional[int] = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of deals to scrape (1-200, default: 50). Higher limits increase API costs."
    )


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

