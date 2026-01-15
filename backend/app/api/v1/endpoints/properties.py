"""
Properties API - Renamed from parking_lots but keeps same URL structure for frontend compatibility.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from geoalchemy2.shape import to_shape
from pydantic import BaseModel
from shapely.geometry import mapping

from app.db.base import get_db
from app.models.property import Property
from app.models.property_business import PropertyBusiness
from app.models.business import Business
from app.models.user import User
from app.models.scoring_prompt import ScoringPrompt
from app.core.dependencies import get_current_user
from app.core.property_imagery_pipeline import property_imagery_pipeline
from app.core.regrid_service import regrid_service
from app.core.usage_tracking_service import usage_tracking_service
from app.core.vlm_analysis_service import vlm_analysis_service
from app.core.apollo_enrichment_service import apollo_enrichment_service
from app.core.lead_enrichment_service import lead_enrichment_service
from app.core.llm_enrichment_service import llm_enrichment_service, EnrichmentStep
from geoalchemy2.shape import from_shape
import json
from shapely.geometry import Point
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class PropertyPreviewRequest(BaseModel):
    """Request for property preview at a location."""
    lat: float
    lng: float
    address: Optional[str] = None
    zoom: int = 20


class AnalyzePropertyRequest(BaseModel):
    """Request to analyze a property with VLM."""
    scoring_prompt_id: Optional[str] = None  # ID of saved prompt, or None to use custom
    custom_prompt: Optional[str] = None  # Custom prompt text


class RegridLookupResponse(BaseModel):
    """Response for fast Regrid lookup."""
    has_parcel: bool
    location: dict
    parcel: Optional[dict] = None
    polygon_geojson: Optional[dict] = None
    error: Optional[str] = None


def property_to_response(prop: Property) -> dict:
    """Convert Property model to response dict."""
    centroid = to_shape(prop.centroid)
    
    # Determine if "evaluated" for frontend compatibility
    is_evaluated = prop.status in ["imagery_captured", "analyzed"]
    
    response = {
        "id": prop.id,
        "centroid": {"lat": centroid.y, "lng": centroid.x},
        "latitude": centroid.y,
        "longitude": centroid.x,
        "area_m2": float(prop.area_m2) if prop.area_m2 else None,
        "area_sqft": float(prop.area_sqft) if prop.area_sqft else None,
        "address": prop.address,
        "status": prop.status,
        "created_at": prop.created_at,
        "updated_at": prop.updated_at,
        # Frontend compatibility fields
        "is_evaluated": is_evaluated,
        "condition_score": float(prop.asphalt_condition_score) if prop.asphalt_condition_score else (float(prop.lead_score) if prop.lead_score else None),
        "paved_area_sqft": float(prop.area_sqft) if prop.area_sqft else None,
        "property_boundary_source": "regrid" if prop.regrid_id else "estimated",
        # Top-level Regrid fields for frontend convenience
        "regrid_owner": prop.regrid_owner,
        "property_category": prop.property_category,
        # Regrid data (nested for backwards compatibility)
        "regrid": {
            "id": prop.regrid_id,
            "apn": prop.regrid_apn,
            "owner": prop.regrid_owner,
            "land_use": prop.regrid_land_use,
            "zoning": prop.regrid_zoning,
            "year_built": prop.regrid_year_built,
            "area_acres": float(prop.regrid_area_acres) if prop.regrid_area_acres else None,
        } if prop.regrid_id else None,
        # Lead scoring
        "lead_score": float(prop.lead_score) if prop.lead_score else None,
        "lead_quality": prop.lead_quality,
        # VLM Analysis
        "paved_percentage": float(prop.paved_percentage) if prop.paved_percentage else None,
        "building_percentage": float(prop.building_percentage) if prop.building_percentage else None,
        "landscaping_percentage": float(prop.landscaping_percentage) if prop.landscaping_percentage else None,
        "asphalt_condition_score": float(prop.asphalt_condition_score) if prop.asphalt_condition_score else None,
        "analysis_notes": prop.analysis_notes,
        "analyzed_at": prop.analyzed_at.isoformat() if prop.analyzed_at else None,
        # Discovery
        "discovery_source": prop.discovery_source,
        "business_type_tier": prop.business_type_tier,
        # Lead Enrichment - Contact Data
        "contact": {
            "name": prop.contact_name or prop.contact_company,  # Use company name if no contact name
            "first_name": prop.contact_first_name,
            "last_name": prop.contact_last_name,
            "email": prop.contact_email,
            "phone": prop.contact_phone,
            "title": prop.contact_title,
            "linkedin_url": prop.contact_linkedin_url,
            "company": prop.contact_company,
            "company_website": prop.contact_company_website,
            "enriched_at": prop.enriched_at.isoformat() if prop.enriched_at else None,
            "source": prop.enrichment_source,
            "status": prop.enrichment_status,
        } if prop.contact_name or prop.contact_email or prop.contact_phone or prop.contact_company else None,
        # LLM enrichment steps (can be simple strings or detailed objects)
        "enrichment_steps": json.loads(prop.enrichment_steps) if prop.enrichment_steps else None,
        "enrichment_detailed_steps": None,  # Will be populated below if available
        "enrichment_flow": None,  # Will be populated below
    }
    
    # Process enrichment steps
    if response["enrichment_steps"]:
        steps_data = response["enrichment_steps"]
        # Check if it's detailed steps (list of dicts) or simple steps (list of strings)
        if steps_data and isinstance(steps_data[0], dict):
            # Detailed steps
            response["enrichment_detailed_steps"] = steps_data
            # Generate simple flow from detailed steps
            simple_steps = [step.get("description", "") for step in steps_data]
            response["enrichment_flow"] = " → ".join(simple_steps)
        else:
            # Simple steps
            response["enrichment_flow"] = " → ".join(steps_data)
    
    # Add Regrid polygon if available
    if prop.regrid_polygon:
        try:
            regrid_geom = to_shape(prop.regrid_polygon)
            if hasattr(regrid_geom, 'exterior'):
                response["geometry"] = {
                    "type": "Polygon",
                    "coordinates": [list(regrid_geom.exterior.coords)]
                }
        except Exception:
            pass
    
    return response


@router.get("")
def list_properties(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    status: Optional[str] = Query(None),
    min_lead_score: Optional[float] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all properties for the current user."""
    query = (
        db.query(Property)
        .filter(Property.user_id == current_user.id)
        .options(
            selectinload(Property.businesses)
            .joinedload(PropertyBusiness.business)
        )
    )
    
    if status:
        query = query.filter(Property.status == status)
    
    if min_lead_score:
        query = query.filter(Property.lead_score >= min_lead_score)
    
    properties = query.order_by(Property.created_at.desc()).offset(skip).limit(limit).all()
    
    results = []
    for prop in properties:
        prop_dict = property_to_response(prop)
        
        # Get primary business
        primary_business = None
        for pb in prop.businesses:
            if pb.is_primary and pb.business:
                primary_business = {
                    "id": pb.business.id,
                    "name": pb.business.name,
                    "phone": pb.business.phone,
                    "category": pb.business.category,
                }
                break
        
        prop_dict["business"] = primary_business
        results.append(prop_dict)
    
    return {
        "results": results,  # Frontend expects "results" not "items"
        "total": len(results),
        "skip": skip,
        "limit": limit,
    }


@router.get("/map")
def get_properties_for_map(
    bounds_sw_lat: Optional[float] = Query(None),
    bounds_sw_lng: Optional[float] = Query(None),
    bounds_ne_lat: Optional[float] = Query(None),
    bounds_ne_lng: Optional[float] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get properties as GeoJSON for map display."""
    query = (
        db.query(Property)
        .filter(Property.user_id == current_user.id)
        .options(
            selectinload(Property.businesses)
            .joinedload(PropertyBusiness.business)
        )
    )
    
    # Filter by bounds if provided
    if all([bounds_sw_lat, bounds_sw_lng, bounds_ne_lat, bounds_ne_lng]):
        envelope = func.ST_MakeEnvelope(
            bounds_sw_lng, bounds_sw_lat,
            bounds_ne_lng, bounds_ne_lat,
            4326
        )
        query = query.filter(
            func.ST_Intersects(
                func.ST_SetSRID(Property.centroid, 4326),
                envelope
            )
        )
    
    properties = query.limit(1000).all()
    
    features = []
    for prop in properties:
        centroid = to_shape(prop.centroid)
        
        # Get primary business name
        business_name = None
        for pb in prop.businesses:
            if pb.is_primary and pb.business:
                business_name = pb.business.name
                break
        
        # Frontend compatibility
        is_evaluated = prop.status in ["imagery_captured", "analyzed"]
        
        # Get display name: business name > contact company > address
        display_name = business_name or prop.contact_company or prop.address
        
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [centroid.x, centroid.y]
            },
            "properties": {
                "id": str(prop.id),
                "business_name": business_name,
                "display_name": display_name,
                "address": prop.address,
                "lead_score": float(prop.lead_score) if prop.lead_score else None,
                "lead_quality": prop.lead_quality,
                "status": prop.status,
                "regrid_owner": prop.regrid_owner,
                "property_category": prop.property_category,
                # Contact/enrichment data
                "contact_company": prop.contact_company,
                "contact_phone": prop.contact_phone,
                "contact_email": prop.contact_email,
                "enrichment_status": prop.enrichment_status,
                # Frontend compatibility
                "is_evaluated": is_evaluated,
                "condition_score": float(prop.asphalt_condition_score) if prop.asphalt_condition_score else (float(prop.lead_score) if prop.lead_score else None),
                "paved_area_sqft": float(prop.area_sqft) if prop.area_sqft else None,
                "property_boundary_source": "regrid" if prop.regrid_id else "estimated",
                "has_business": business_name is not None,
                "has_contact": prop.contact_email is not None or prop.contact_phone is not None,
                "business_type_tier": prop.business_type_tier,
                "discovery_source": prop.discovery_source,
            }
        })
    
    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/regrid-lookup")
async def regrid_lookup(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fast Regrid parcel lookup - NO satellite imagery.
    
    Returns parcel data and polygon GeoJSON within ~1 second.
    Use this for instant feedback when user clicks on map.
    """
    try:
        parcel = await regrid_service.get_validated_parcel(lat, lng)
        
        # Track Regrid API usage (subscription-based, quota tracking only)
        usage_tracking_service.log_api_call(
            db=db,
            user_id=current_user.id,
            service="regrid",
            operation="parcel_lookup",
            metadata={"lat": lat, "lng": lng, "found": parcel is not None and parcel.polygon is not None}
        )
        
        if parcel and parcel.polygon:
            polygon_geojson = mapping(parcel.polygon)
            
            return {
                "has_parcel": True,
                "location": {"lat": lat, "lng": lng},
                "parcel": {
                    "parcel_id": parcel.parcel_id,
                    "address": parcel.address,
                    "owner": parcel.owner,
                    "land_use": parcel.land_use,
                    "zoning": parcel.zoning,
                    "year_built": parcel.year_built,
                    "area_acres": parcel.area_acres,
                    "area_sqm": parcel.area_m2,
                    "apn": parcel.apn,
                },
                "polygon_geojson": polygon_geojson,
            }
        else:
            return {
                "has_parcel": False,
                "location": {"lat": lat, "lng": lng},
                "parcel": None,
                "polygon_geojson": None,
                "error": "No parcel found at this location",
            }
    except Exception as e:
        return {
            "has_parcel": False,
            "location": {"lat": lat, "lng": lng},
            "parcel": None,
            "polygon_geojson": None,
            "error": str(e),
        }


@router.get("/{property_id}")
def get_property(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get single property with full details."""
    prop = (
        db.query(Property)
        .filter(
            Property.id == property_id,
            Property.user_id == current_user.id
        )
        .options(
            selectinload(Property.businesses)
            .joinedload(PropertyBusiness.business)
        )
        .first()
    )
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    response = property_to_response(prop)
    
    # Add satellite image
    if prop.satellite_image_base64:
        response["satellite_image_base64"] = prop.satellite_image_base64
    
    # Add all businesses
    businesses = []
    for pb in prop.businesses:
        if pb.business:
            biz = pb.business
            businesses.append({
                "id": biz.id,
                "name": biz.name,
                "phone": biz.phone,
                "email": biz.email,
                "website": biz.website,
                "category": biz.category,
                "is_primary": pb.is_primary,
                "match_score": float(pb.match_score) if pb.match_score else None,
            })
    
    response["businesses"] = businesses
    
    # Get primary business
    primary = next((b for b in businesses if b.get("is_primary")), None)
    response["business"] = primary
    
    # Build property_analysis structure for frontend compatibility
    regrid_polygon_geojson = None
    if prop.regrid_polygon:
        try:
            regrid_geom = to_shape(prop.regrid_polygon)
            if hasattr(regrid_geom, 'exterior'):
                regrid_polygon_geojson = {
                    "type": "Polygon",
                    "coordinates": [list(regrid_geom.exterior.coords)]
                }
        except Exception:
            pass
    
    response["property_analysis"] = {
        "status": prop.status,
        "property_boundary": {
            "source": "regrid" if prop.regrid_id else None,
            "parcel_id": prop.regrid_id,
            "owner": prop.regrid_owner,
            "apn": prop.regrid_apn,
            "land_use": prop.regrid_land_use,
            "zoning": prop.regrid_zoning,
            "polygon": regrid_polygon_geojson,
        } if prop.regrid_id else None,
        "paved_percentage": float(prop.paved_percentage) if prop.paved_percentage else None,
        "asphalt_condition_score": float(prop.asphalt_condition_score) if prop.asphalt_condition_score else None,
        "analysis_notes": prop.analysis_notes,
        "analyzed_at": prop.analyzed_at.isoformat() if prop.analyzed_at else None,
        "images": {
            "wide_satellite": prop.satellite_image_base64,
        },
    }
    
    return response


@router.get("/{property_id}/businesses")
def get_property_businesses(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all businesses associated with a property."""
    prop = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    associations = (
        db.query(PropertyBusiness)
        .filter(PropertyBusiness.property_id == property_id)
        .options(joinedload(PropertyBusiness.business))
        .order_by(PropertyBusiness.match_score.desc())
        .all()
    )
    
    results = []
    for assoc in associations:
        biz = assoc.business
        if biz:
            biz_location = to_shape(biz.location) if biz.location else None
            results.append({
                "id": biz.id,
                "name": biz.name,
                "phone": biz.phone,
                "email": biz.email,
                "website": biz.website,
                "address": biz.address,
                "category": biz.category,
                "match_score": float(assoc.match_score) if assoc.match_score else None,
                "distance_meters": float(assoc.distance_meters) if assoc.distance_meters else None,
                "is_primary": assoc.is_primary,
                "location": {"lat": biz_location.y, "lng": biz_location.x} if biz_location else None,
            })
    
    return results


@router.post("/preview")
async def preview_property_at_location(
    request: PropertyPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Preview and SAVE a property at a clicked location.
    
    Fetches Regrid polygon and satellite imagery for the clicked coordinates,
    then saves the property to the database (without business contact data).
    """
    result = await property_imagery_pipeline.get_property_image(
        lat=request.lat,
        lng=request.lng,
        address=request.address,
        zoom=request.zoom,
        draw_boundary=True,
        save_debug=True,  # Save for debugging
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error_message or "Failed to get property data")
    
    # Create centroid point
    centroid_point = Point(request.lng, request.lat)
    
    # Check if property already exists at this location (within ~50m)
    existing = db.query(Property).filter(
        Property.user_id == current_user.id,
        func.ST_DWithin(
            Property.centroid,
            func.ST_SetSRID(func.ST_MakePoint(request.lng, request.lat), 4326),
            0.0005  # ~50 meters in degrees
        )
    ).first()
    
    if existing:
        # Update existing property
        db_property = existing
        db_property.satellite_image_base64 = result.image_base64
        db_property.satellite_zoom_level = str(request.zoom)
        db_property.satellite_fetched_at = datetime.utcnow()
    else:
        # Create new property
        db_property = Property(
            user_id=current_user.id,
            centroid=from_shape(centroid_point, srid=4326),
            address=result.parcel.address if result.parcel else request.address,
            discovery_source="map_click",
            status="imagery_captured",
            satellite_image_base64=result.image_base64,
            satellite_zoom_level=str(request.zoom),
            satellite_fetched_at=datetime.utcnow(),
        )
        db.add(db_property)
    
    # Add Regrid data if available
    if result.parcel:
        db_property.regrid_id = result.parcel.parcel_id
        db_property.regrid_apn = result.parcel.apn
        db_property.regrid_owner = result.parcel.owner
        db_property.regrid_land_use = result.parcel.land_use
        db_property.regrid_zoning = result.parcel.zoning
        db_property.regrid_year_built = str(result.parcel.year_built) if result.parcel.year_built else None
        db_property.regrid_area_acres = result.parcel.area_acres
        db_property.regrid_fetched_at = datetime.utcnow()
        
        if result.polygon:
            db_property.regrid_polygon = from_shape(result.polygon, srid=4326)
    
    # Set area
    db_property.area_m2 = result.area_sqm
    db_property.area_sqft = result.area_sqft
    
    db.commit()
    db.refresh(db_property)
    
    # Track usage: Regrid (subscription quota) - Satellite is FREE (raw tiles)
    usage_tracking_service.log_api_call(
        db=db,
        user_id=current_user.id,
        service="regrid",
        operation="property_preview",
        property_id=db_property.id,
        metadata={"lat": request.lat, "lng": request.lng, "found": result.parcel is not None}
    )
    # Note: Google satellite tiles via contextily are FREE (raw tile server, not official API)
    
    # Build response
    response = {
        "success": True,
        "saved": True,
        "property_id": str(db_property.id),
        "is_new": existing is None,
        "location": {"lat": request.lat, "lng": request.lng},
        "image_base64": result.image_base64,
        "image_size": {"width": result.image_size[0], "height": result.image_size[1]},
        "area_sqm": result.area_sqm,
        "area_sqft": result.area_sqft,
    }
    
    # Add polygon GeoJSON if available
    if result.polygon:
        response["polygon"] = mapping(result.polygon)
    
    # Add Regrid parcel data if available
    if result.parcel:
        response["regrid"] = {
            "parcel_id": result.parcel.parcel_id,
            "apn": result.parcel.apn,
            "address": result.parcel.address,
            "owner": result.parcel.owner,
            "land_use": result.parcel.land_use,
            "zoning": result.parcel.zoning,
            "year_built": result.parcel.year_built,
            "area_acres": result.parcel.area_acres,
            "area_sqm": result.parcel.area_m2,
        }
    else:
        response["regrid"] = None
        response["boundary_source"] = "estimated"
    
    return response


@router.post("/{property_id}/analyze")
async def analyze_property(
    property_id: UUID,
    request: AnalyzePropertyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run VLM analysis on a property to score it as a lead.
    
    Requires the property to have a satellite image captured.
    Uses either a saved scoring prompt or custom prompt.
    """
    # Get property
    prop = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    if not prop.satellite_image_base64:
        raise HTTPException(status_code=400, detail="Property has no satellite image. Capture imagery first.")
    
    # Get scoring prompt
    scoring_prompt = None
    if request.scoring_prompt_id:
        saved_prompt = db.query(ScoringPrompt).filter(
            ScoringPrompt.id == request.scoring_prompt_id,
            ScoringPrompt.user_id == current_user.id
        ).first()
        if saved_prompt:
            scoring_prompt = saved_prompt.prompt
    elif request.custom_prompt:
        scoring_prompt = request.custom_prompt
    
    # If no prompt provided, use default
    if not scoring_prompt:
        # Check for user's default prompt
        default_prompt = db.query(ScoringPrompt).filter(
            ScoringPrompt.user_id == current_user.id,
            ScoringPrompt.is_default == True
        ).first()
        if default_prompt:
            scoring_prompt = default_prompt.prompt
    
    # Get user's OpenRouter key if enabled
    user_openrouter_key = None
    if current_user.use_own_openrouter_key and current_user.openrouter_api_key:
        user_openrouter_key = current_user.openrouter_api_key
        logger.info(f"Using user's OpenRouter API key for analysis")
    
    # Build property context
    property_context = {
        "address": prop.address,
        "owner": prop.regrid_owner,
        "land_use": prop.regrid_land_use,
        "area_acres": float(prop.regrid_area_acres) if prop.regrid_area_acres else None,
        "zoning": prop.regrid_zoning,
    }
    
    # Run VLM analysis
    logger.info(f"Running VLM analysis on property {property_id}")
    vlm_result = await vlm_analysis_service.analyze_property(
        image_base64=prop.satellite_image_base64,
        scoring_prompt=scoring_prompt,
        property_context=property_context,
        user_api_key=user_openrouter_key,
    )
    
    if not vlm_result.success:
        raise HTTPException(status_code=500, detail=f"VLM analysis failed: {vlm_result.error_message}")
    
    # Update property with results
    prop.lead_score = vlm_result.lead_score
    prop.lead_quality = (
        'high' if vlm_result.lead_score >= 70 
        else 'medium' if vlm_result.lead_score >= 40 
        else 'low'
    )
    prop.analysis_notes = vlm_result.reasoning
    prop.analyzed_at = datetime.utcnow()
    prop.status = "analyzed"
    
    # Store surface breakdown if available
    if vlm_result.observations:
        prop.paved_percentage = vlm_result.observations.paved_area_pct
        prop.building_percentage = vlm_result.observations.building_pct
        prop.landscaping_percentage = vlm_result.observations.landscaping_pct
        prop.asphalt_condition_score = (
            90 if vlm_result.observations.condition == 'critical' else
            70 if vlm_result.observations.condition == 'poor' else
            50 if vlm_result.observations.condition == 'fair' else
            30 if vlm_result.observations.condition == 'good' else
            10  # excellent
        )
    
    db.commit()
    db.refresh(prop)
    
    # Log VLM usage
    usage_tracking_service.log_openrouter_call(
        db=db,
        user_id=current_user.id,
        property_id=prop.id,
        model=vlm_analysis_service.DEFAULT_MODEL,
        tokens_used=vlm_result.usage.total_tokens if vlm_result.usage else 0,
        actual_cost=vlm_result.usage.cost if vlm_result.usage else 0,
        metadata={"operation": "single_property_analysis"},
    )
    
    return {
        "success": True,
        "property_id": str(prop.id),
        "lead_score": vlm_result.lead_score,
        "lead_quality": prop.lead_quality,
        "confidence": vlm_result.confidence,
        "reasoning": vlm_result.reasoning,
        "observations": {
            "paved_area_pct": vlm_result.observations.paved_area_pct if vlm_result.observations else None,
            "building_pct": vlm_result.observations.building_pct if vlm_result.observations else None,
            "landscaping_pct": vlm_result.observations.landscaping_pct if vlm_result.observations else None,
            "condition": vlm_result.observations.condition if vlm_result.observations else None,
            "visible_issues": vlm_result.observations.visible_issues if vlm_result.observations else [],
        } if vlm_result.observations else None,
        "usage": {
            "tokens": vlm_result.usage.total_tokens if vlm_result.usage else None,
            "cost": vlm_result.usage.cost if vlm_result.usage else None,
        } if vlm_result.usage else None,
    }


@router.post("/{property_id}/enrich")
async def enrich_property(
    property_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Enrich a property with Property Manager contact information.
    
    Uses LLM-powered enrichment:
    1. LLM plans search strategy based on property type
    2. Searches relevant sources (apartments.com, Google Places, etc.)
    3. Analyzes pages to extract contact info
    4. Selects best contact from collected data
    
    Returns contact details and enrichment steps for UI visualization.
    """
    # Get property
    prop = db.query(Property).filter(
        Property.id == property_id,
        Property.user_id == current_user.id
    ).first()
    
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    
    # Check if already enriched with contact
    if prop.enrichment_status == "success" and (prop.contact_email or prop.contact_phone):
        # Return existing enrichment with steps if available
        steps = json.loads(prop.enrichment_steps) if prop.enrichment_steps else []
        
        return {
            "success": True,
            "property_id": str(prop.id),
            "already_enriched": True,
            "contact": {
                "name": prop.contact_name,
                "first_name": prop.contact_first_name,
                "last_name": prop.contact_last_name,
                "email": prop.contact_email,
                "phone": prop.contact_phone,
                "title": prop.contact_title,
                "linkedin_url": prop.contact_linkedin_url,
                "company": prop.contact_company,
            },
            "enrichment_steps": steps,
            "enrichment_flow": " → ".join(steps) if steps else None,
            "enriched_at": prop.enriched_at.isoformat() if prop.enriched_at else None,
        }
    
    # Determine property type from LBCS or property_category
    property_type = prop.property_category or "commercial"
    if prop.lbcs_structure:
        lbcs_code = int(prop.lbcs_structure)
        if 1200 <= lbcs_code < 1300:
            property_type = "multi_family"
        elif 2100 <= lbcs_code < 2200:
            property_type = "office"
        elif 2200 <= lbcs_code < 2300:
            property_type = "retail"
        elif 2600 <= lbcs_code < 2800:
            property_type = "industrial"
    
    logger.info(f"LLM Enriching property {property_id}")
    logger.info(f"  Address: {prop.address}")
    logger.info(f"  Property type: {property_type}")
    
    # Run LLM-powered enrichment
    result = await llm_enrichment_service.enrich(
        address=prop.address or "",
        property_type=property_type,
        owner_name=prop.regrid_owner,
        lbcs_code=int(prop.lbcs_structure) if prop.lbcs_structure else None,
    )
    
    # Update property with results
    prop.enriched_at = datetime.utcnow()
    
    # Store enrichment steps for UI (always save detailed steps with URLs)
    # Detailed steps include URL, source, confidence for rich display
    detailed_steps = result.detailed_steps or []
    steps = result.steps or []
    
    if detailed_steps:
        # Store detailed steps as JSON (includes URL, source, confidence)
        prop.enrichment_steps = json.dumps([step.to_dict() for step in detailed_steps])
    elif steps:
        # Fallback to simple steps if no detailed steps
        prop.enrichment_steps = json.dumps(steps)
    
    if result.success and result.contact:
        contact = result.contact
        prop.contact_name = contact.name
        prop.contact_first_name = contact.first_name
        prop.contact_last_name = contact.last_name
        prop.contact_email = contact.email
        prop.contact_phone = contact.phone
        prop.contact_title = contact.title
        prop.contact_company = result.management_company
        prop.contact_company_website = result.management_website
        prop.enrichment_source = "llm_enrichment"
        prop.enrichment_status = "success"
        
        logger.info(f"  ✅ LLM Enrichment successful")
        logger.info(f"     Contact: {contact.name or 'N/A'}")
        logger.info(f"     Email: {contact.email or 'N/A'}")
        logger.info(f"     Phone: {contact.phone or 'N/A'}")
        logger.info(f"     Company: {result.management_company or 'N/A'}")
        logger.info(f"     Confidence: {result.confidence:.0%}")
    else:
        prop.enrichment_status = "not_found"
        logger.info(f"  ⚠️ No contact found")
        if result.error_message:
            logger.info(f"     Error: {result.error_message}")
    
    db.commit()
    db.refresh(prop)
    
    # Log usage
    usage_tracking_service.log_api_call(
        db=db,
        user_id=current_user.id,
        service="llm_enrichment",
        operation="lead_enrichment",
        property_id=prop.id,
        metadata={
            "property_type": property_type,
            "success": result.success,
            "contact_found": result.contact is not None,
            "management_company": result.management_company,
            "tokens_used": result.tokens_used,
            "estimated_cost": result.estimated_cost,
            "steps_count": len(result.steps),
        }
    )
    
    # Build response with detailed steps
    detailed_steps_dict = [step.to_dict() for step in result.detailed_steps] if result.detailed_steps else []
    # Generate simple steps for flow string and backwards compatibility
    simple_steps = [step.to_simple_string() for step in result.detailed_steps] if result.detailed_steps else steps
    
    if result.success and result.contact:
        contact = result.contact
        return {
            "success": True,
            "property_id": str(prop.id),
            "already_enriched": False,
            "property_type": property_type,
            "contact": {
                "name": contact.name,
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "email": contact.email,
                "phone": contact.phone,
                "title": contact.title,
                "company": result.management_company,
                "company_website": result.management_website,
            },
            "enrichment_steps": simple_steps,
            "enrichment_detailed_steps": detailed_steps_dict,
            "enrichment_flow": " → ".join(simple_steps) if simple_steps else None,
            "confidence": result.confidence,
            "tokens_used": result.tokens_used,
            "enriched_at": prop.enriched_at.isoformat(),
        }
    else:
        return {
            "success": False,
            "property_id": str(prop.id),
            "property_type": property_type,
            "enrichment_steps": simple_steps,
            "enrichment_detailed_steps": detailed_steps_dict,
            "enrichment_flow": " → ".join(simple_steps) if simple_steps else None,
            "tokens_used": result.tokens_used,
            "error": result.error_message or "No contact information found",
        }

