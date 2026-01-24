"""
API endpoints for US boundary data (states, counties, zips, urban areas)
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from app.core.boundary_service import get_boundary_service

router = APIRouter()


class BoundaryLayer(BaseModel):
    id: str
    name: str
    available: bool
    size_mb: float
    loaded: bool


class BoundarySearchResult(BaseModel):
    id: str
    name: str
    properties: dict


@router.get("/layers", response_model=List[BoundaryLayer])
async def get_available_layers():
    """Get list of available boundary layers"""
    service = get_boundary_service()
    return service.get_available_layers()


@router.get("/layer/{layer_id}")
async def get_layer(
    layer_id: str,
    min_lng: Optional[float] = Query(None, description="Minimum longitude"),
    min_lat: Optional[float] = Query(None, description="Minimum latitude"),
    max_lng: Optional[float] = Query(None, description="Maximum longitude"),
    max_lat: Optional[float] = Query(None, description="Maximum latitude"),
    limit: int = Query(50000, le=100000, description="Max features to return")
):
    """
    Get boundary layer as GeoJSON.
    
    All layers can load all features. ZIPs layer (33k features) may take 30-60s to load.
    """
    service = get_boundary_service()
    
    valid_layers = ["states", "counties", "zips", "urban_areas"]
    if layer_id not in valid_layers:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid layer. Must be one of: {valid_layers}"
        )
    
    # If bounds provided, filter by viewport
    if all(v is not None for v in [min_lng, min_lat, max_lng, max_lat]):
        return service.get_layer_within_bounds(
            layer_id, min_lng, min_lat, max_lng, max_lat, limit
        )
    
    # Load all features for any layer
    result = service.get_layer(layer_id)
    
    # Apply limit if needed
    features = result.get("features", [])
    if len(features) > limit:
        result["features"] = features[:limit]
        result["truncated"] = True
        result["total_in_layer"] = len(features)
    
    return result


@router.get("/layer/{layer_id}/search")
async def search_layer(
    layer_id: str,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, le=100)
):
    """Search boundaries by name within a layer"""
    service = get_boundary_service()
    
    valid_layers = ["states", "counties", "zips", "urban_areas"]
    if layer_id not in valid_layers:
        raise HTTPException(status_code=400, detail=f"Invalid layer")
    
    results = service.search_boundaries(layer_id, q, limit)
    return {"results": results, "count": len(results)}


@router.get("/layer/{layer_id}/{boundary_id}")
async def get_boundary(layer_id: str, boundary_id: str):
    """Get a specific boundary by ID"""
    service = get_boundary_service()
    
    valid_layers = ["states", "counties", "zips", "urban_areas"]
    if layer_id not in valid_layers:
        raise HTTPException(status_code=400, detail=f"Invalid layer")
    
    feature = service.get_boundary_by_id(layer_id, boundary_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Boundary not found")
    
    return feature


@router.post("/layer/{layer_id}/preload")
async def preload_layer(layer_id: str):
    """Preload a boundary layer into cache"""
    service = get_boundary_service()
    
    valid_layers = ["states", "counties", "zips", "urban_areas"]
    if layer_id not in valid_layers:
        raise HTTPException(status_code=400, detail=f"Invalid layer")
    
    # Load the layer (this caches it)
    result = service.get_layer(layer_id)
    feature_count = len(result.get("features", []))
    
    return {
        "layer": layer_id,
        "loaded": True,
        "feature_count": feature_count
    }


@router.delete("/cache")
async def clear_cache(layer_id: Optional[str] = None):
    """Clear boundary cache"""
    service = get_boundary_service()
    service.clear_cache(layer_id)
    return {"cleared": layer_id or "all"}


@router.get("/point")
async def get_boundary_at_point(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    layer: str = Query("zips", description="Layer to search: zips, counties, or states")
):
    """
    Find the boundary (ZIP, county, or state) that contains a given point.
    
    Click-to-select functionality: user clicks on map, we return the boundary.
    """
    service = get_boundary_service()
    
    valid_layers = ["states", "counties", "zips"]
    if layer not in valid_layers:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid layer. Must be one of: {valid_layers}"
        )
    
    feature = service.get_boundary_at_point(layer, lat, lng)
    
    if not feature:
        return {
            "found": False,
            "layer": layer,
            "lat": lat,
            "lng": lng,
            "boundary": None
        }
    
    props = feature.get("properties", {})
    
    return {
        "found": True,
        "layer": layer,
        "lat": lat,
        "lng": lng,
        "boundary": {
            "id": props.get("id", ""),
            "name": props.get("name", ""),
            "properties": props,
            "geometry": feature.get("geometry")
        }
    }


@router.get("/point/all")
async def get_all_boundaries_at_point(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude")
):
    """
    Get all boundary info at a point (ZIP, county, state).
    
    Useful for getting full context about a location.
    """
    service = get_boundary_service()
    
    result = service.get_boundary_info_at_point(lat, lng)
    
    return {
        "lat": lat,
        "lng": lng,
        "boundaries": result
    }
