from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import json
import asyncio
import logging

from app.db.base import get_db
from app.models.user import User
from app.schemas.discovery import (
    DiscoveryRequest,
    DiscoveryJobResponse,
    DiscoveryStatusResponse,
    DiscoveryResultsResponse,
    DiscoveryFilters,
    DiscoveryStep,
    DiscoveryProgress,
    DiscoveryMode,
    BUSINESS_TYPE_OPTIONS,
    PropertyCategoryEnum,
    PROPERTY_CATEGORY_LBCS_RANGES,
)
from app.core.dependencies import get_current_user
from app.core.discovery_orchestrator import discovery_orchestrator, DiscoveryMode as OrchestratorMode
from app.core.geocoding_service import geocoding_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/business-types")
async def get_business_type_options():
    """
    Get available business type options for discovery (business_first mode).
    
    Returns a list of business types grouped by tier (premium, high, standard).
    Use these IDs in the `business_type_ids` field when starting discovery.
    """
    return {
        "tiers": [
            {
                "id": "premium",
                "label": "Premium (High Success Rate)",
                "icon": "trophy",
                "description": "Apartments, condos, mobile homes - actual properties with parking",
                "types": BUSINESS_TYPE_OPTIONS["premium"],
            },
            {
                "id": "high",
                "label": "High Priority",
                "icon": "star",
                "description": "Commercial properties with large parking areas",
                "types": BUSINESS_TYPE_OPTIONS["high"],
            },
            {
                "id": "standard",
                "label": "Standard",
                "icon": "map-pin",
                "description": "Other businesses that may have parking lots",
                "types": BUSINESS_TYPE_OPTIONS["standard"],
            },
        ]
    }


@router.get("/property-categories")
async def get_property_category_options():
    """
    Get available property category options for Regrid-first discovery.
    
    Returns property categories that map to LBCS (Land Based Classification Standards) codes.
    Use these IDs in the `property_categories` field when starting regrid_first discovery.
    """
    return {
        "categories": [
            {
                "id": PropertyCategoryEnum.MULTI_FAMILY.value,
                "label": "Multi-Family Residential",
                "icon": "building",
                "description": "Apartments, condos, townhomes (LBCS 1200-1299)",
                "lbcs_ranges": PROPERTY_CATEGORY_LBCS_RANGES[PropertyCategoryEnum.MULTI_FAMILY],
            },
            {
                "id": PropertyCategoryEnum.RETAIL.value,
                "label": "Retail & Shopping",
                "icon": "shopping-cart",
                "description": "Shopping centers, stores, malls (LBCS 2200-2599)",
                "lbcs_ranges": PROPERTY_CATEGORY_LBCS_RANGES[PropertyCategoryEnum.RETAIL],
            },
            {
                "id": PropertyCategoryEnum.OFFICE.value,
                "label": "Office Buildings",
                "icon": "briefcase",
                "description": "Office buildings, business parks (LBCS 2100-2199)",
                "lbcs_ranges": PROPERTY_CATEGORY_LBCS_RANGES[PropertyCategoryEnum.OFFICE],
            },
            {
                "id": PropertyCategoryEnum.INDUSTRIAL.value,
                "label": "Industrial & Warehouse",
                "icon": "factory",
                "description": "Warehouses, distribution centers (LBCS 2600-2799)",
                "lbcs_ranges": PROPERTY_CATEGORY_LBCS_RANGES[PropertyCategoryEnum.INDUSTRIAL],
            },
            {
                "id": PropertyCategoryEnum.INSTITUTIONAL.value,
                "label": "Institutional",
                "icon": "landmark",
                "description": "Churches, schools, hospitals (LBCS 3500, 4100-4299)",
                "lbcs_ranges": PROPERTY_CATEGORY_LBCS_RANGES[PropertyCategoryEnum.INSTITUTIONAL],
            },
        ]
    }


@router.post("", response_model=DiscoveryJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_discovery(
    request: DiscoveryRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start property discovery process.
    
    This is an async operation. Returns a job_id that can be used to check status.
    
    Three discovery modes available:
    
    **business_first** (default):
    1. Find businesses via Google Places by type (apartments, shopping centers)
    2. Get property data from Regrid
    3. Fetch satellite imagery and run VLM analysis
    4. Return prioritized leads
    
    **contact_first**:
    1. Find contacts via Apollo (owners, principals at RE companies)
    2. Search Regrid for properties owned by their companies
    3. Fetch satellite imagery and run VLM analysis
    4. Return leads with contact data
    
    **regrid_first** (RECOMMENDED - comprehensive coverage):
    1. Query Regrid directly by LBCS property classification codes
    2. Find ALL properties of selected types in the area (not just Google-listed)
    3. Fetch satellite imagery and run VLM analysis
    4. Enrich with contact data from Google Places + Apollo
    """
    # Determine which mode to use
    is_contact_first = request.mode == DiscoveryMode.CONTACT_FIRST
    is_regrid_first = request.mode == DiscoveryMode.REGRID_FIRST
    
    # Validate request based on mode
    if is_contact_first:
        # Contact-first mode requires city or state
        if not request.city and not request.state:
            raise HTTPException(
                status_code=400,
                detail="City or state is required for contact_first mode"
            )
        # Area polygon not needed for contact-first
        area_polygon = None
    elif is_regrid_first:
        # Regrid-first mode requires area and property categories
        if request.area_type == "county" and not request.state:
            raise HTTPException(
                status_code=400,
                detail="State is required for county search"
            )
        
        # Get or create polygon with metadata for geographic filtering
        if request.area_type == "polygon":
            area_polygon = request.polygon.model_dump()
        else:
            area_polygon = await geocoding_service.get_area_polygon(
                request.area_type.value,
                request.value,
                request.state
            )
            
            if not area_polygon:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not geocode {request.area_type.value}: {request.value}"
                )
            
            # Add metadata for Regrid query
            if not area_polygon.get("properties"):
                area_polygon["properties"] = {}
            
            if request.area_type.value == "zip":
                area_polygon["properties"]["zip_code"] = request.value
            area_polygon["properties"]["state"] = request.state
    else:
        # Business-first mode validation
        if request.area_type == "county" and not request.state:
            raise HTTPException(
                status_code=400,
                detail="State is required for county search"
            )
        
        if request.area_type == "polygon" and not request.polygon:
            raise HTTPException(
                status_code=400,
                detail="Polygon is required when area_type is 'polygon'"
            )
        
        # Get or create polygon
        if request.area_type == "polygon":
            area_polygon = request.polygon.model_dump()
        else:
            area_polygon = await geocoding_service.get_area_polygon(
                request.area_type.value,
                request.value,
                request.state
            )
            
            if not area_polygon:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not geocode {request.area_type.value}: {request.value}"
                )
    
    # Create job
    job_id = uuid4()
    filters = request.filters or DiscoveryFilters()
    
    # Override max_lots if max_results is provided in request
    if request.max_results:
        filters.max_lots = request.max_results
        filters.max_businesses = request.max_results
    
    # Initialize job status BEFORE starting background task (so status endpoint works immediately)
    discovery_orchestrator.initialize_job(job_id, current_user.id)
    
    # Set orchestrator mode
    if is_contact_first:
        orchestrator_mode = OrchestratorMode.CONTACT_FIRST
    elif is_regrid_first:
        orchestrator_mode = OrchestratorMode.REGRID_FIRST
    else:
        orchestrator_mode = OrchestratorMode.BUSINESS_FIRST
    
    # Convert tiers to strings if provided
    tier_strings = None
    if request.tiers:
        tier_strings = [t.value for t in request.tiers]
    
    # Convert property categories to strings if provided
    property_category_strings = None
    if request.property_categories:
        property_category_strings = [c.value for c in request.property_categories]
    
    # Start discovery in background
    background_tasks.add_task(
        discovery_orchestrator.start_discovery,
        job_id,
        current_user.id,
        area_polygon,
        filters,
        db,
        orchestrator_mode,
        tier_strings,
        request.business_type_ids,
        request.scoring_prompt,
        # Contact-first mode parameters
        request.city,
        request.state,
        request.job_titles,
        request.industries,
        # Regrid-first mode parameters
        property_category_strings,
        request.min_acres,
        request.max_acres,
    )
    
    if is_contact_first:
        location = f"{request.city or 'Any'}, {request.state or 'Any'}"
        mode_desc = f"contact-first [{location}]"
    elif is_regrid_first:
        categories = property_category_strings or ["multi_family"]
        mode_desc = f"regrid-first [{', '.join(categories)}]"
    else:
        mode_desc = "business-first"
        if tier_strings:
            mode_desc += f" [{', '.join(tier_strings)}]"
    
    return DiscoveryJobResponse(
        job_id=job_id,
        status=DiscoveryStep.QUEUED,
        message=f"Discovery started ({mode_desc}). Use GET /discover/{{job_id}} to check status.",
        estimated_completion=datetime.utcnow() + timedelta(minutes=5),
    )


@router.get("/{job_id}", response_model=DiscoveryStatusResponse)
async def get_discovery_status(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """
    Get status of a discovery job.
    
    Returns current step, progress metrics, and any errors.
    """
    job = discovery_orchestrator.get_job_status(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Discovery job not found"
        )
    
    # Verify ownership
    if job.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view this job"
        )
    
    return DiscoveryStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        started_at=job["started_at"],
        completed_at=job.get("completed_at"),
        error=job.get("error"),
    )


@router.get("/{job_id}/results", response_model=DiscoveryResultsResponse)
async def get_discovery_results(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
):
    """
    Get results summary of a completed discovery job.
    """
    job = discovery_orchestrator.get_job_status(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Discovery job not found"
        )
    
    if job.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to view this job"
        )
    
    if job["status"] != DiscoveryStep.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job['status'].value}"
        )
    
    progress = job["progress"]
    
    return DiscoveryResultsResponse(
        job_id=job_id,
        status=job["status"],
        results={
            "parking_lots_found": progress.parking_lots_found,
            "parking_lots_evaluated": progress.parking_lots_evaluated,
            "businesses_loaded": progress.businesses_loaded,
            "associations_made": progress.associations_made,
            "high_value_leads": progress.high_value_leads,
        },
        message=f"Found {progress.parking_lots_found} parking lots. {progress.high_value_leads} high-value leads identified.",
    )


@router.post("/stream")
async def stream_discovery(
    request: DiscoveryRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream discovery progress via Server-Sent Events (SSE).
    
    Returns real-time progress updates as the discovery runs.
    Each message is a JSON object with type, message, and optional data.
    
    Message types:
    - started: Discovery has started
    - searching: Searching for properties
    - found: Found parcels/properties
    - processing: Processing a specific property
    - imagery: Fetching satellite imagery
    - analyzing: Running AI analysis
    - scoring: Lead scored
    - enriching: Finding contact info
    - contact_found: Contact info found
    - progress: Generic progress update
    - complete: Discovery finished
    - error: An error occurred
    """
    # Validate and prepare request (same as start_discovery)
    is_contact_first = request.mode == DiscoveryMode.CONTACT_FIRST
    is_regrid_first = request.mode == DiscoveryMode.REGRID_FIRST
    
    # Validate request based on mode
    if is_contact_first:
        if not request.city and not request.state:
            raise HTTPException(status_code=400, detail="City or state is required for contact_first mode")
        area_polygon = None
    elif is_regrid_first:
        if request.area_type == "county" and not request.state:
            raise HTTPException(status_code=400, detail="State is required for county search")
        
        if request.area_type == "polygon":
            area_polygon = request.polygon.model_dump()
        else:
            area_polygon = await geocoding_service.get_area_polygon(
                request.area_type.value, request.value, request.state
            )
            if not area_polygon:
                raise HTTPException(status_code=400, detail=f"Could not geocode {request.area_type.value}: {request.value}")
            
            if not area_polygon.get("properties"):
                area_polygon["properties"] = {}
            if request.area_type.value == "zip":
                area_polygon["properties"]["zip_code"] = request.value
            area_polygon["properties"]["state"] = request.state
    else:
        if request.area_type == "county" and not request.state:
            raise HTTPException(status_code=400, detail="State is required for county search")
        if request.area_type == "polygon" and not request.polygon:
            raise HTTPException(status_code=400, detail="Polygon is required when area_type is 'polygon'")
        
        if request.area_type == "polygon":
            area_polygon = request.polygon.model_dump()
        else:
            area_polygon = await geocoding_service.get_area_polygon(
                request.area_type.value, request.value, request.state
            )
            if not area_polygon:
                raise HTTPException(status_code=400, detail=f"Could not geocode {request.area_type.value}: {request.value}")
    
    # Prepare parameters
    job_id = uuid4()
    filters = request.filters or DiscoveryFilters()
    if request.max_results:
        filters.max_lots = request.max_results
        filters.max_businesses = request.max_results
    
    if is_contact_first:
        orchestrator_mode = OrchestratorMode.CONTACT_FIRST
    elif is_regrid_first:
        orchestrator_mode = OrchestratorMode.REGRID_FIRST
    else:
        orchestrator_mode = OrchestratorMode.BUSINESS_FIRST
    
    tier_strings = [t.value for t in request.tiers] if request.tiers else None
    property_category_strings = [c.value for c in request.property_categories] if request.property_categories else None
    
    async def event_generator():
        """Generate SSE events from discovery progress."""
        try:
            # Stream progress from orchestrator
            async for progress in discovery_orchestrator.stream_discovery(
                job_id=job_id,
                user_id=current_user.id,
                area_polygon=area_polygon,
                filters=filters,
                db=db,
                mode=orchestrator_mode,
                tiers=tier_strings,
                business_type_ids=request.business_type_ids,
                scoring_prompt=request.scoring_prompt,
                city=request.city,
                state=request.state,
                job_titles=request.job_titles,
                industries=request.industries,
                property_categories=property_category_strings,
                min_acres=request.min_acres,
                max_acres=request.max_acres,
            ):
                # Check if client disconnected
                if await http_request.is_disconnected():
                    logger.info(f"[Stream] Client disconnected, stopping discovery stream")
                    break
                
                # Send SSE event
                yield f"data: {json.dumps(progress)}\n\n"
                
        except Exception as e:
            logger.error(f"[Stream] Error during discovery: {e}")
            error_event = {
                "type": "error",
                "message": f"Discovery failed: {str(e)}",
                "icon": "❌"
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )

