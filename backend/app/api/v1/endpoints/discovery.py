"""
Discovery API Endpoints

Fetches real parcel geometries from Regrid's MVT vector tiles.
Tiles are free (unlimited), only record queries count against quota.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging

from app.core.arcgis_parcel_service import get_parcel_discovery_service, DiscoveryParcel

logger = logging.getLogger(__name__)

router = APIRouter()


class DiscoveryQueryRequest(BaseModel):
    """Request to query parcels in an area"""
    geometry: Dict[str, Any]  # GeoJSON Polygon or MultiPolygon
    min_acres: Optional[float] = None
    max_acres: Optional[float] = None
    limit: int = 500


class ParcelResponse(BaseModel):
    """Individual parcel in response"""
    id: str
    address: str
    acreage: float
    apn: str
    regrid_id: str
    geometry: Dict[str, Any]
    centroid: Dict[str, float]
    owner: Optional[str] = None


class DiscoveryQueryResponse(BaseModel):
    """Response from parcel discovery query"""
    success: bool
    parcels: List[ParcelResponse]
    total_count: int
    error: Optional[str] = None


@router.post("/parcels", response_model=DiscoveryQueryResponse)
async def query_parcels(request: DiscoveryQueryRequest):
    """
    Query parcels within a given area with optional size filter.
    
    This uses ArcGIS Feature Service which doesn't count against Regrid API limits.
    
    Args:
        geometry: GeoJSON Polygon or MultiPolygon defining the search area
        min_acres: Minimum parcel size in acres (optional)
        max_acres: Maximum parcel size in acres (optional)
        limit: Maximum number of parcels to return (default 500)
    """
    try:
        logger.info(f"🔍 Discovery query: min_acres={request.min_acres}, max_acres={request.max_acres}, limit={request.limit}")
        
        # Validate geometry
        geom_type = request.geometry.get("type")
        if geom_type not in ["Polygon", "MultiPolygon"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid geometry type: {geom_type}. Must be Polygon or MultiPolygon."
            )
        
        # Query parcels
        service = get_parcel_discovery_service()
        parcels = await service.query_parcels_in_area(
            geometry=request.geometry,
            min_acres=request.min_acres,
            max_acres=request.max_acres,
            limit=request.limit,
        )
        
        logger.info(f"✅ Found {len(parcels)} parcels")
        
        # Convert to response format
        parcel_responses = [
            ParcelResponse(
                id=p.id,
                address=p.address,
                acreage=p.acreage,
                apn=p.apn,
                regrid_id=p.regrid_id,
                geometry=p.geometry,
                centroid=p.centroid,
                owner=getattr(p, 'owner', None),
            )
            for p in parcels
        ]
        
        return DiscoveryQueryResponse(
            success=True,
            parcels=parcel_responses,
            total_count=len(parcel_responses),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Discovery query error: {e}", exc_info=True)
        return DiscoveryQueryResponse(
            success=False,
            parcels=[],
            total_count=0,
            error=str(e),
        )


class ProcessParcelsRequest(BaseModel):
    """Request to process selected parcels"""
    parcels: List[ParcelResponse]


class ProcessParcelsResponse(BaseModel):
    """Response from parcel processing"""
    success: bool
    message: str
    job_id: Optional[str] = None


@router.post("/process", response_model=ProcessParcelsResponse)
async def process_parcels(request: ProcessParcelsRequest):
    """
    Process selected parcels for lead enrichment.
    
    This endpoint queues the parcels for LLM enrichment to find contact information.
    
    Args:
        parcels: List of parcels to process
    """
    try:
        logger.info(f"📋 Processing {len(request.parcels)} parcels for enrichment")
        
        if not request.parcels:
            raise HTTPException(status_code=400, detail="No parcels provided")
        
        # TODO: Queue parcels for LLM enrichment
        # For now, return a placeholder response
        
        return ProcessParcelsResponse(
            success=True,
            message=f"Queued {len(request.parcels)} parcels for enrichment",
            job_id="pending_implementation",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Process parcels error: {e}", exc_info=True)
        return ProcessParcelsResponse(
            success=False,
            message=str(e),
        )
