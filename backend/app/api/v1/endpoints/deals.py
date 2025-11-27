from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.db.base import get_db
from app.models.deal import Deal
from app.models.user import User
from app.schemas.deal import (
    DealCreate, DealResponse, GeographicSearchRequest, 
    GeographicSearchResponse, DealMapResponse
)
from app.core.scraper_service import scraper_service
from app.core.geocoding_service import geocoding_service
from app.core.dependencies import get_current_user
import uuid

router = APIRouter()


@router.post("/scrape", response_model=GeographicSearchResponse)
async def scrape_deals(
    request: GeographicSearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Scrape deals by geographic area.
    
    Cost note: Google Places API costs ~$32 per 1000 requests.
    Each query + pagination = multiple requests. Use max_deals to control costs.
    """
    max_deals = request.max_deals or 50
    job_id = str(uuid.uuid4())
    
    if request.area_type == "zip":
        deals_data = await scraper_service.scrape_by_zip(request.value, max_deals=max_deals)
    elif request.area_type == "county":
        if not request.state:
            raise HTTPException(status_code=400, detail="State required for county search")
        deals_data = await scraper_service.scrape_by_county(request.value, request.state, max_deals=max_deals)
    else:
        raise HTTPException(status_code=400, detail="area_type must be 'zip' or 'county'")
    
    # Geocode and save deals
    saved_count = 0
    for deal_data in deals_data:
        if not deal_data.get("latitude") or not deal_data.get("longitude"):
            geocode_result = await geocoding_service.geocode_address(deal_data["address"])
            if geocode_result:
                deal_data["latitude"] = float(geocode_result["latitude"])
                deal_data["longitude"] = float(geocode_result["longitude"])
                deal_data["places_id"] = geocode_result.get("place_id")
        
        db_deal = Deal(**deal_data, user_id=current_user.id)
        db.add(db_deal)
        saved_count += 1
    
    db.commit()
    
    return GeographicSearchResponse(
        job_id=job_id,
        status="completed",
        message=f"Scraped and saved {saved_count} deals"
    )


@router.get("", response_model=List[DealResponse])
def list_deals(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all deals for current user."""
    query = db.query(Deal).filter(Deal.user_id == current_user.id)
    if status:
        query = query.filter(Deal.status == status)
    return query.all()


@router.get("/map", response_model=List[DealMapResponse])
def get_deals_for_map(
    min_lat: Optional[float] = Query(None, description="Minimum latitude (bounding box)"),
    max_lat: Optional[float] = Query(None, description="Maximum latitude (bounding box)"),
    min_lng: Optional[float] = Query(None, description="Minimum longitude (bounding box)"),
    max_lng: Optional[float] = Query(None, description="Maximum longitude (bounding box)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get deals optimized for map display with evaluation scores."""
    query = db.query(Deal).filter(Deal.user_id == current_user.id)
    
    # Filter by bounding box if provided
    if min_lat is not None and max_lat is not None and min_lng is not None and max_lng is not None:
        query = query.filter(
            Deal.latitude >= min_lat,
            Deal.latitude <= max_lat,
            Deal.longitude >= min_lng,
            Deal.longitude <= max_lng
        )
    
    # Filter by status
    if status:
        query = query.filter(Deal.status == status)
    
    # Only return deals with coordinates
    query = query.filter(Deal.latitude.isnot(None), Deal.longitude.isnot(None))
    
    deals = query.all()
    
    # Build response with evaluation data
    result = []
    for deal in deals:
        evaluation = deal.evaluation
        result.append(DealMapResponse(
            id=deal.id,
            business_name=deal.business_name,
            address=deal.address,
            latitude=float(deal.latitude) if deal.latitude else None,
            longitude=float(deal.longitude) if deal.longitude else None,
            status=deal.status,
            deal_score=float(evaluation.deal_score) if evaluation and evaluation.deal_score else None,
            estimated_job_value=float(evaluation.estimated_job_value) if evaluation and evaluation.estimated_job_value else None,
            damage_severity=evaluation.damage_severity if evaluation else None,
        ))
    
    return result


@router.get("/{deal_id}", response_model=DealResponse)
def get_deal(
    deal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get deal by ID."""
    deal = db.query(Deal).filter(Deal.id == deal_id, Deal.user_id == current_user.id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal

