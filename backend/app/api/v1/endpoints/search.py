"""
Search API Endpoints

Provides unified search functionality:
- Pin drop (single parcel)
- Polygon search (spatial query)
- ZIP code search (with filters)
- Natural language search (Claude-parsed)
- Category search (LBCS codes)
- Brand search (Google Places)
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from datetime import datetime

from app.core.search_service import (
    search_service, SearchQuery, SearchFilters, SearchType,
    SearchResult, SearchResultParcel, PROPERTY_CATEGORIES
)
from app.core.search_nlp_service import nlp_search_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================

class PointLocation(BaseModel):
    lat: float
    lng: float


class ViewportBounds(BaseModel):
    minLat: float
    maxLat: float
    minLng: float
    maxLng: float


class SearchFiltersRequest(BaseModel):
    category_id: Optional[str] = None
    min_acres: Optional[float] = None
    max_acres: Optional[float] = None


class SearchRequest(BaseModel):
    """Unified search request."""
    search_type: str = Field(..., description="pin, polygon, zip, nlp, category, brand")
    
    # Geography (one depending on search_type)
    point: Optional[PointLocation] = None
    polygon_geojson: Optional[Dict[str, Any]] = None
    zip_code: Optional[str] = None
    viewport: Optional[ViewportBounds] = None
    state_code: Optional[str] = None
    
    # For NLP
    query: Optional[str] = None
    
    # For brand
    brand_name: Optional[str] = None
    
    # Filters
    filters: Optional[SearchFiltersRequest] = None
    
    # Options
    preview_only: bool = False
    limit: int = Field(default=500, le=1000)
    offset: int = 0


class ParcelResponse(BaseModel):
    """Single parcel in search results."""
    parcel_id: str
    address: Optional[str]
    owner: Optional[str]
    lat: float
    lng: float
    area_acres: Optional[float]
    area_sqft: Optional[float]
    land_use: Optional[str]
    zoning: Optional[str]
    year_built: Optional[int]
    polygon_geojson: Optional[Dict[str, Any]]
    lbcs_activity: Optional[int] = None
    lbcs_activity_desc: Optional[str] = None
    brand_name: Optional[str] = None
    place_id: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response."""
    success: bool
    search_type: str
    total_count: int
    parcels: List[ParcelResponse]
    preview_only: bool = False
    error: Optional[str] = None
    search_session_id: Optional[str] = None


class NLPParseRequest(BaseModel):
    """Request to parse natural language query."""
    query: str
    viewport: Optional[ViewportBounds] = None


class NLPParseResponse(BaseModel):
    """Parsed NLP query result."""
    success: bool
    original_query: str
    parsed: Dict[str, Any]
    suggested_search_type: str
    requires_additional_input: bool = False
    message: Optional[str] = None


class CategoryInfo(BaseModel):
    """Property category information."""
    id: str
    label: str
    description: str
    icon: str


class CategoriesResponse(BaseModel):
    """Available property categories."""
    categories: List[CategoryInfo]


# ============================================================
# Endpoints
# ============================================================

@router.post("/search", response_model=SearchResponse)
async def execute_search(request: SearchRequest):
    """
    Execute a property search.
    
    Supports multiple search types:
    - pin: Single parcel lookup by lat/lng
    - polygon: Spatial query within drawn polygon
    - zip: Parcels within ZIP code (requires filters)
    - category: Search by property type (LBCS codes)
    - brand: Search for franchise/brand locations
    - nlp: Natural language query (will be parsed first)
    """
    logger.info(f"🔍 Search request: type={request.search_type}")
    
    try:
        # Handle NLP search type - parse first
        if request.search_type == "nlp":
            if not request.query:
                raise HTTPException(status_code=400, detail="Query required for NLP search")
            
            # Parse the query
            viewport_dict = None
            if request.viewport:
                viewport_dict = {
                    "minLat": request.viewport.minLat,
                    "maxLat": request.viewport.maxLat,
                    "minLng": request.viewport.minLng,
                    "maxLng": request.viewport.maxLng,
                }
            
            parsed_query = await nlp_search_service.parse_query(
                request.query,
                current_viewport=viewport_dict,
            )
            
            # Execute the parsed query
            result = await search_service.search(
                query=parsed_query,
                preview_only=request.preview_only,
            )
        else:
            # Build query from request
            search_type = _map_search_type(request.search_type)
            
            filters = SearchFilters()
            if request.filters:
                filters = SearchFilters(
                    category_id=request.filters.category_id,
                    min_acres=request.filters.min_acres,
                    max_acres=request.filters.max_acres,
                )
            
            viewport_dict = None
            if request.viewport:
                viewport_dict = {
                    "minLat": request.viewport.minLat,
                    "maxLat": request.viewport.maxLat,
                    "minLng": request.viewport.minLng,
                    "maxLng": request.viewport.maxLng,
                }
            
            point_dict = None
            if request.point:
                point_dict = {"lat": request.point.lat, "lng": request.point.lng}
            
            query = SearchQuery(
                search_type=search_type,
                point=point_dict,
                polygon_geojson=request.polygon_geojson,
                zip_code=request.zip_code,
                viewport=viewport_dict,
                state_code=request.state_code,
                brand_name=request.brand_name,
                filters=filters,
                limit=request.limit,
                offset=request.offset,
            )
            
            result = await search_service.search(
                query=query,
                preview_only=request.preview_only,
            )
        
        # Convert result to response
        parcels = [
            ParcelResponse(
                parcel_id=p.parcel_id,
                address=p.address,
                owner=p.owner,
                lat=p.lat,
                lng=p.lng,
                area_acres=p.area_acres,
                area_sqft=p.area_sqft,
                land_use=p.land_use,
                zoning=p.zoning,
                year_built=p.year_built,
                polygon_geojson=p.polygon_geojson,
                lbcs_activity=p.lbcs_activity,
                lbcs_activity_desc=p.lbcs_activity_desc,
                brand_name=p.brand_name,
                place_id=p.place_id,
            )
            for p in result.parcels
        ]
        
        return SearchResponse(
            success=result.success,
            search_type=result.search_type.value,
            total_count=result.total_count,
            parcels=parcels,
            preview_only=result.preview_only,
            error=result.error,
            search_session_id=result.search_session_id,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/parse-nlp", response_model=NLPParseResponse)
async def parse_nlp_query(request: NLPParseRequest):
    """
    Parse a natural language query without executing it.
    
    Useful for showing the user what we understood and letting them adjust.
    """
    try:
        viewport_dict = None
        if request.viewport:
            viewport_dict = {
                "minLat": request.viewport.minLat,
                "maxLat": request.viewport.maxLat,
                "minLng": request.viewport.minLng,
                "maxLng": request.viewport.maxLng,
            }
        
        parsed = await nlp_search_service.parse_query(
            request.query,
            current_viewport=viewport_dict,
        )
        
        # Build parsed info for response
        parsed_info = {
            "search_type": parsed.search_type.value,
            "category_id": parsed.filters.category_id,
            "brand_name": parsed.brand_name,
            "zip_code": parsed.zip_code,
            "state_code": parsed.state_code,
            "min_acres": parsed.filters.min_acres,
            "max_acres": parsed.filters.max_acres,
        }
        
        # Check if we need more input
        requires_input = False
        message = None
        
        if parsed.search_type == SearchType.CATEGORY:
            if not parsed.zip_code and not parsed.viewport and not parsed.polygon_geojson:
                requires_input = True
                message = "Please specify a location (ZIP code or draw an area on the map)"
        
        return NLPParseResponse(
            success=True,
            original_query=request.query,
            parsed=parsed_info,
            suggested_search_type=parsed.search_type.value,
            requires_additional_input=requires_input,
            message=message,
        )
        
    except Exception as e:
        logger.error(f"NLP parse error: {e}")
        return NLPParseResponse(
            success=False,
            original_query=request.query,
            parsed={},
            suggested_search_type="category",
            requires_additional_input=True,
            message=f"Could not understand query: {str(e)}",
        )


@router.get("/search/categories", response_model=CategoriesResponse)
async def get_categories():
    """
    Get available property categories for search.
    """
    categories = [
        CategoryInfo(
            id=cat_id,
            label=cat["label"],
            description=cat["description"],
            icon=cat["icon"],
        )
        for cat_id, cat in PROPERTY_CATEGORIES.items()
    ]
    
    return CategoriesResponse(categories=categories)


@router.get("/search/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=2),
):
    """
    Get search suggestions for partial query.
    """
    suggestions = await nlp_search_service.suggest_completions(query)
    return {"suggestions": suggestions}


class CountyResponse(BaseModel):
    """County data."""
    fips: str
    name: str
    state: str
    full_name: str


class CountySearchResponse(BaseModel):
    """County search results."""
    counties: List[CountyResponse]


class CountyBoundaryResponse(BaseModel):
    """County boundary data."""
    fips: str
    name: str
    state: str
    boundary: Optional[Dict[str, Any]]


@router.get("/search/counties", response_model=CountySearchResponse)
async def search_counties(
    query: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, le=50),
):
    """
    Search US counties by name (autocomplete).
    
    Returns matching counties for the search query.
    """
    from app.core.county_service import county_service
    
    counties = await county_service.search_counties(query, limit)
    
    return CountySearchResponse(
        counties=[
            CountyResponse(
                fips=c.fips,
                name=c.name,
                state=c.state,
                full_name=c.full_name,
            )
            for c in counties
        ]
    )


@router.get("/search/counties/{fips}/boundary", response_model=CountyBoundaryResponse)
async def get_county_boundary(
    fips: str,
):
    """
    Get GeoJSON boundary for a county.
    
    Args:
        fips: 5-digit FIPS code (e.g., "48113" for Dallas County, TX)
    """
    from app.core.county_service import county_service
    
    county = await county_service.get_county_by_fips(fips)
    if not county:
        raise HTTPException(status_code=404, detail=f"County not found: {fips}")
    
    boundary = await county_service.get_county_boundary(fips)
    
    return CountyBoundaryResponse(
        fips=fips,
        name=county.name,
        state=county.state,
        boundary=boundary,
    )


def _map_search_type(search_type_str: str) -> SearchType:
    """Map string to SearchType enum."""
    mapping = {
        "pin": SearchType.PIN,
        "polygon": SearchType.POLYGON,
        "zip": SearchType.ZIP,
        "county": SearchType.COUNTY,
        "nlp": SearchType.NLP,
        "category": SearchType.CATEGORY,
        "brand": SearchType.BRAND,
    }
    
    if search_type_str not in mapping:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid search type: {search_type_str}. Valid: {list(mapping.keys())}"
        )
    
    return mapping[search_type_str]
