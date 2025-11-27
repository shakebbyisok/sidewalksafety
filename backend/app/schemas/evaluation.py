from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class EvaluationResponse(BaseModel):
    id: UUID
    deal_id: UUID
    deal_score: Optional[float] = None
    parking_lot_area_sqft: Optional[float] = None
    crack_density_percent: Optional[float] = None
    damage_severity: Optional[str] = None
    estimated_repair_cost: Optional[float] = None
    estimated_job_value: Optional[float] = None
    satellite_image_url: Optional[str] = None
    parking_lot_mask: Optional[Dict[str, Any]] = None
    crack_detections: Optional[List[Dict[str, Any]]] = None
    evaluation_metadata: Optional[Dict[str, Any]] = None
    evaluated_at: datetime

    class Config:
        from_attributes = True


class DealWithEvaluation(BaseModel):
    id: UUID
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
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str
    created_at: datetime
    evaluation: Optional[EvaluationResponse] = None

    class Config:
        from_attributes = True

