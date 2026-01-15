from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import and_, func, text
from typing import List, Optional
from uuid import UUID
from geoalchemy2.shape import to_shape
from geoalchemy2.functions import ST_X, ST_Y, ST_MakeEnvelope, ST_Intersects

from app.db.base import get_db
from app.models.parking_lot import ParkingLot
from app.models.association import ParkingLotBusinessAssociation
from app.models.business import Business
from app.models.user import User
from app.models.property_analysis import PropertyAnalysis
from app.models.asphalt_area import AsphaltArea
from app.models.analysis_tile import AnalysisTile
from app.schemas.parking_lot import (
    ParkingLotResponse,
    ParkingLotDetailResponse,
    ParkingLotMapResponse,
    ParkingLotWithBusiness,
    ParkingLotListResponse,
    Coordinates,
    BusinessSummary,
)
from app.core.dependencies import get_current_user

router = APIRouter()


def _extract_asphalt_geojson(property_analysis):
    """
    Extract asphalt features from surfaces_geojson FeatureCollection.
    
    Returns a merged GeoJSON Feature if asphalt features exist, None otherwise.
    """
    surfaces_geojson = getattr(property_analysis, 'surfaces_geojson', None)
    if not surfaces_geojson or not surfaces_geojson.get('features'):
        return None
    
    # Filter for asphalt features
    asphalt_features = [
        f for f in surfaces_geojson['features']
        if f.get('properties', {}).get('surface_type') in ('asphalt', 'road', 'paved', 'driveway', 'parking lot')
    ]
    
    if not asphalt_features:
        return None
    
    # If single feature, return it directly
    if len(asphalt_features) == 1:
        return asphalt_features[0]
    
    # If multiple features, return as FeatureCollection
    return {
        "type": "FeatureCollection",
        "features": asphalt_features
    }


def parking_lot_to_response(lot: ParkingLot, include_business: bool = False) -> dict:
    """Convert ParkingLot model to response dict."""
    centroid = to_shape(lot.centroid)
    
    response = {
        "id": lot.id,
        "centroid": Coordinates(lat=centroid.y, lng=centroid.x),
        # Add flat lat/lng for easier frontend use
        "latitude": centroid.y,
        "longitude": centroid.x,
        "area_m2": float(lot.area_m2) if lot.area_m2 else None,
        "area_sqft": float(lot.area_sqft) if lot.area_sqft else None,
        "operator_name": lot.operator_name,
        "address": lot.address,
        "surface_type": lot.surface_type,
        "condition_score": float(lot.condition_score) if lot.condition_score else None,
        "crack_density": float(lot.crack_density) if lot.crack_density else None,
        "pothole_score": float(lot.pothole_score) if lot.pothole_score else None,
        "line_fading_score": float(lot.line_fading_score) if lot.line_fading_score else None,
        "satellite_image_url": lot.satellite_image_url,
        "is_evaluated": lot.is_evaluated,
        "data_sources": lot.data_sources or [],
        "created_at": lot.created_at,
        "evaluated_at": lot.evaluated_at,
        # Business-first discovery fields
        "business_type_tier": lot.business_type_tier,
        "discovery_mode": lot.discovery_mode,
        "evaluation_status": lot.evaluation_status,
    }
    
    # Add geometry if available
    if lot.geometry:
        geom = to_shape(lot.geometry)
        response["geometry"] = {
            "type": "Polygon",
            "coordinates": [list(geom.exterior.coords)]
        }
    
    # Add Regrid property data
    if lot.regrid_parcel_id:
        regrid_polygon_geojson = None
        if lot.regrid_polygon:
            try:
                regrid_geom = to_shape(lot.regrid_polygon)
                if hasattr(regrid_geom, 'exterior'):
                    regrid_polygon_geojson = {
                        "type": "Polygon",
                        "coordinates": [list(regrid_geom.exterior.coords)]
                    }
            except Exception:
                pass
        
        response["regrid"] = {
            "parcel_id": lot.regrid_parcel_id,
            "apn": lot.regrid_apn,
            "owner": lot.regrid_owner,
            "owner_address": lot.regrid_owner_address,
            "land_use": lot.regrid_land_use,
            "zoning": lot.regrid_zoning,
            "year_built": lot.regrid_year_built,
            "area_acres": float(lot.regrid_area_acres) if lot.regrid_area_acres else None,
            "polygon": regrid_polygon_geojson,
            "fetched_at": lot.regrid_fetched_at,
        }
    
    return response


def get_primary_business_from_associations(associations) -> tuple:
    """
    Extract primary business from eagerly-loaded associations.
    Returns (business, association) or (None, None).
    """
    for assoc in associations:
        if assoc.is_primary:
            return assoc.business, assoc
    return None, None


@router.get("", response_model=ParkingLotListResponse)
def list_parking_lots(
    min_area_m2: Optional[float] = Query(None, description="Minimum lot area in m²"),
    max_condition_score: Optional[float] = Query(None, description="Maximum condition score (lower = worse)"),
    min_match_score: Optional[float] = Query(None, description="Minimum business match score"),
    has_business: Optional[bool] = Query(None, description="Filter by business association"),
    is_evaluated: Optional[bool] = Query(None, description="Filter by evaluation status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List parking lots with filters.
    
    Returns parking lots owned by the current user with optional filtering.
    Uses eager loading to avoid N+1 queries.
    """
    # Base query with eager loading of associations and businesses
    query = (
        db.query(ParkingLot)
        .filter(ParkingLot.user_id == current_user.id)
        .options(
            selectinload(ParkingLot.business_associations)
            .joinedload(ParkingLotBusinessAssociation.business)
        )
    )
    
    # Apply filters
    if min_area_m2 is not None:
        query = query.filter(ParkingLot.area_m2 >= min_area_m2)
    
    if max_condition_score is not None:
        query = query.filter(ParkingLot.condition_score <= max_condition_score)
    
    if is_evaluated is not None:
        query = query.filter(ParkingLot.is_evaluated == is_evaluated)
    
    if has_business is not None:
        if has_business:
            # Use exists subquery for filtering
            subquery = (
                db.query(ParkingLotBusinessAssociation.parking_lot_id)
                .filter(ParkingLotBusinessAssociation.is_primary == True)
                .subquery()
            )
            query = query.filter(ParkingLot.id.in_(db.query(subquery)))
        else:
            subquery = (
                db.query(ParkingLotBusinessAssociation.parking_lot_id)
                .filter(ParkingLotBusinessAssociation.is_primary == True)
                .subquery()
            )
            query = query.filter(~ParkingLot.id.in_(db.query(subquery)))
    
    # Get total count (before pagination)
    total = query.count()
    
    # Apply pagination and ordering
    lots = (
        query
        .order_by(ParkingLot.condition_score.asc().nullslast())
        .offset(offset)
        .limit(limit)
        .all()
    )
    
    # Fetch latest analysis for each lot in one query
    lot_ids = [lot.id for lot in lots]
    analyses_query = (
        db.query(PropertyAnalysis)
        .filter(PropertyAnalysis.parking_lot_id.in_(lot_ids))
        .order_by(PropertyAnalysis.created_at.desc())
        .all()
    )
    # Build lookup - latest analysis per lot
    analysis_by_lot = {}
    for analysis in analyses_query:
        if analysis.parking_lot_id not in analysis_by_lot:
            analysis_by_lot[analysis.parking_lot_id] = analysis
    
    # Build response - no additional queries needed due to eager loading
    results = []
    for lot in lots:
        lot_dict = parking_lot_to_response(lot)
        
        # Get primary business from already-loaded associations
        business, assoc = get_primary_business_from_associations(lot.business_associations)
        
        if business and assoc:
            lot_dict["business"] = BusinessSummary(
                id=business.id,
                name=business.name,
                phone=business.phone,
                email=business.email,
                website=business.website,
                address=business.address,
                category=business.category,
            )
            lot_dict["match_score"] = float(assoc.match_score)
            lot_dict["distance_meters"] = float(assoc.distance_meters)
        
        # Add analysis data
        analysis = analysis_by_lot.get(lot.id)
        if analysis:
            lot_dict["paved_area_sqft"] = float(analysis.private_asphalt_area_sqft or 0)
            lot_dict["crack_count"] = int(analysis.total_crack_count or 0)
            lot_dict["pothole_count"] = int(analysis.total_pothole_count or 0)
            lot_dict["property_boundary_source"] = analysis.property_boundary_source
            lot_dict["lead_quality"] = analysis.lead_quality
        
        results.append(ParkingLotWithBusiness(**lot_dict))
    
    return ParkingLotListResponse(
        total=total,
        limit=limit,
        offset=offset,
        results=results,
    )


@router.get("/map")
def get_parking_lots_for_map(
    min_lat: Optional[float] = Query(None),
    max_lat: Optional[float] = Query(None),
    min_lng: Optional[float] = Query(None),
    max_lng: Optional[float] = Query(None),
    max_condition_score: Optional[float] = Query(None),
    has_business: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get parking lots optimized for map display.
    
    Uses PostGIS spatial filtering and eager loading for optimal performance.
    Returns GeoJSON FeatureCollection.
    """
    # Base query with eager loading - single query for all data
    query = (
        db.query(ParkingLot)
        .filter(ParkingLot.user_id == current_user.id)
        .options(
            selectinload(ParkingLot.business_associations)
            .joinedload(ParkingLotBusinessAssociation.business)
        )
    )
    
    # Apply PostGIS bounding box filter if all bounds provided
    if all(v is not None for v in [min_lat, max_lat, min_lng, max_lng]):
        # Use PostGIS ST_MakeEnvelope for efficient spatial filtering
        # ST_MakeEnvelope(xmin, ymin, xmax, ymax, srid)
        envelope = func.ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)
        query = query.filter(
            func.ST_Intersects(
                func.ST_SetSRID(ParkingLot.centroid, 4326),
                envelope
            )
        )
    
    if max_condition_score is not None:
        query = query.filter(ParkingLot.condition_score <= max_condition_score)
    
    if has_business is not None:
        if has_business:
            subquery = (
                db.query(ParkingLotBusinessAssociation.parking_lot_id)
                .filter(ParkingLotBusinessAssociation.is_primary == True)
                .subquery()
            )
            query = query.filter(ParkingLot.id.in_(db.query(subquery)))
        else:
            subquery = (
                db.query(ParkingLotBusinessAssociation.parking_lot_id)
                .filter(ParkingLotBusinessAssociation.is_primary == True)
                .subquery()
            )
            query = query.filter(~ParkingLot.id.in_(db.query(subquery)))
    
    # Limit results for map display
    lots = query.limit(500).all()
    
    # Build features - no additional queries due to eager loading
    features = []
    
    # Fetch latest analysis for each lot in one query
    lot_ids = [lot.id for lot in lots]
    analyses_query = (
        db.query(PropertyAnalysis)
        .filter(PropertyAnalysis.parking_lot_id.in_(lot_ids))
        .order_by(PropertyAnalysis.created_at.desc())
        .all()
    )
    # Build lookup - latest analysis per lot
    analysis_by_lot = {}
    for analysis in analyses_query:
        if analysis.parking_lot_id not in analysis_by_lot:
            analysis_by_lot[analysis.parking_lot_id] = analysis
    
    for lot in lots:
        centroid = to_shape(lot.centroid)
        
        # Get business from already-loaded associations
        business, _ = get_primary_business_from_associations(lot.business_associations)
        business_name = business.name if business else None
        has_biz = business is not None
        
        # Get analysis data
        analysis = analysis_by_lot.get(lot.id)
        
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [centroid.x, centroid.y]
            },
            "properties": {
                "id": str(lot.id),
                "area_m2": float(lot.area_m2) if lot.area_m2 else None,
                "condition_score": float(lot.condition_score) if lot.condition_score else None,
                "business_name": business_name,
                "address": lot.address,
                "satellite_image_url": lot.satellite_image_url,
                "operator_name": lot.operator_name,
                "has_business": has_biz,
                "is_evaluated": lot.is_evaluated,
                "business_type_tier": lot.business_type_tier,
                "discovery_mode": lot.discovery_mode,
                # Analysis data
                "paved_area_sqft": float(analysis.private_asphalt_area_sqft or 0) if analysis else None,
                "crack_count": int(analysis.total_crack_count or 0) if analysis else None,
                "pothole_count": int(analysis.total_pothole_count or 0) if analysis else None,
                "property_boundary_source": analysis.property_boundary_source if analysis else None,
                "lead_quality": analysis.lead_quality if analysis else None,
            }
        })
    
    return {
        "type": "FeatureCollection",
        "features": features,
    }


@router.get("/{parking_lot_id}", response_model=ParkingLotDetailResponse)
def get_parking_lot(
    parking_lot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get single parking lot with full details."""
    lot = (
        db.query(ParkingLot)
        .filter(
            ParkingLot.id == parking_lot_id,
            ParkingLot.user_id == current_user.id
        )
        .options(
            selectinload(ParkingLot.business_associations)
            .joinedload(ParkingLotBusinessAssociation.business)
        )
        .first()
    )
    
    if not lot:
        raise HTTPException(status_code=404, detail="Parking lot not found")
    
    response = parking_lot_to_response(lot)
    response["degradation_areas"] = lot.degradation_areas
    response["raw_metadata"] = lot.raw_metadata
    response["evaluation_error"] = lot.evaluation_error
    response["updated_at"] = lot.updated_at
    
    # Get primary business from already-loaded associations
    business, assoc = get_primary_business_from_associations(lot.business_associations)
    
    if business and assoc:
        response["business"] = BusinessSummary(
            id=business.id,
            name=business.name,
            phone=business.phone,
            email=business.email,
            website=business.website,
            address=business.address,
            category=business.category,
        )
        response["match_score"] = float(assoc.match_score)
        response["distance_meters"] = float(assoc.distance_meters)
    
    # Get LATEST property analysis if exists (order by created_at DESC to get newest)
    property_analysis = db.query(PropertyAnalysis).filter(
        PropertyAnalysis.parking_lot_id == parking_lot_id
    ).order_by(PropertyAnalysis.created_at.desc()).first()
    
    if property_analysis:
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"📸 PropertyAnalysis found for {parking_lot_id}")
        logger.info(f"   analysis_type: {property_analysis.analysis_type}")
        logger.info(f"   total_tiles: {property_analysis.total_tiles}")
        logger.info(f"   🔥 DB VALUES:")
        logger.info(f"      total_asphalt_area_sqft: {property_analysis.total_asphalt_area_sqft}")
        logger.info(f"      total_paved_area_sqft: {property_analysis.total_paved_area_sqft}")
        logger.info(f"      private_asphalt_area_sqft: {property_analysis.private_asphalt_area_sqft}")
        logger.info(f"      private_asphalt_geojson: {type(property_analysis.private_asphalt_geojson)} - {bool(property_analysis.private_asphalt_geojson)}")
        logger.info(f"      surfaces_geojson: {type(property_analysis.surfaces_geojson)} - {bool(property_analysis.surfaces_geojson)}")
        logger.info(f"   condition_score: {property_analysis.weighted_condition_score}")
        
        # Build property boundary info if available
        property_boundary_info = None
        if property_analysis.property_boundary_source:
            property_boundary_info = {
                "source": property_analysis.property_boundary_source,
                "parcel_id": property_analysis.property_parcel_id,
                "owner": property_analysis.property_owner,
                "apn": property_analysis.property_apn,
                "land_use": property_analysis.property_land_use,
                "zoning": property_analysis.property_zoning,
            }
            # Add polygon as GeoJSON if available
            if property_analysis.property_boundary_polygon:
                boundary_shape = to_shape(property_analysis.property_boundary_polygon)
                if hasattr(boundary_shape, 'exterior'):
                    property_boundary_info["polygon"] = {
                        "type": "Polygon",
                        "coordinates": [list(boundary_shape.exterior.coords)]
                    }
        
        # Get tiles if this is a tiled analysis (WITHOUT images for performance)
        tiles_data = []
        if property_analysis.analysis_type == "tiled":
            logger.info(f"   🔍 Querying tiles for analysis: {property_analysis.id}")
            tiles = db.query(AnalysisTile).filter(
                AnalysisTile.property_analysis_id == property_analysis.id
            ).order_by(AnalysisTile.tile_index).all()
            logger.info(f"   📊 Found {len(tiles)} tiles in database")
            
            for tile in tiles:
                tiles_data.append({
                    "id": str(tile.id),
                    "tile_index": tile.tile_index,
                    "center_lat": tile.center_lat,
                    "center_lng": tile.center_lng,
                    "zoom_level": tile.zoom_level,
                    "bounds": {
                        "min_lat": tile.bounds_min_lat,
                        "max_lat": tile.bounds_max_lat,
                        "min_lng": tile.bounds_min_lng,
                        "max_lng": tile.bounds_max_lng,
                    },
                    # Total asphalt from CV (includes public roads)
                    "asphalt_area_m2": tile.asphalt_area_m2,
                    # Private asphalt (after filtering public roads)
                    "private_asphalt_area_m2": tile.private_asphalt_area_m2,
                    "private_asphalt_area_sqft": tile.private_asphalt_area_sqft,
                    "private_asphalt_geojson": tile.private_asphalt_geojson,  # For map overlay
                    # Public roads filtered out
                    "public_road_area_m2": tile.public_road_area_m2,
                    "asphalt_source": tile.asphalt_source,
                    # Condition
                    "condition_score": tile.condition_score,
                    "crack_count": tile.crack_count,
                    "pothole_count": tile.pothole_count,
                    "status": tile.status,
                    # Images NOT included here for performance - use /tiles/{id}/image endpoint
                    "has_image": tile.satellite_image_base64 is not None,
                })
        
        response["property_analysis"] = {
            "id": str(property_analysis.id),
            "status": property_analysis.status,
            "analysis_type": property_analysis.analysis_type or "single",
            "detection_method": getattr(property_analysis, 'detection_method', None) or "legacy_cv",
            
            # ============ SURFACE TYPE BREAKDOWN (NEW) ============
            # Note: We use surfaces_geojson as the primary source for polygon data
            # The individual geojson fields (asphalt_geojson, etc.) are for backwards compat
            "surfaces": {
                "asphalt": {
                    "area_m2": property_analysis.private_asphalt_area_m2 or getattr(property_analysis, 'total_paved_area_m2', None),
                    "area_sqft": property_analysis.private_asphalt_area_sqft or getattr(property_analysis, 'total_paved_area_sqft', None),
                    # Use surfaces_geojson features if private_asphalt_geojson is empty
                    "geojson": getattr(property_analysis, 'private_asphalt_geojson', None) or _extract_asphalt_geojson(property_analysis),
                    "color": "#374151",  # Dark gray
                    "label": "Asphalt",
                },
                "concrete": {
                    "area_m2": getattr(property_analysis, 'concrete_area_m2', None),
                    "area_sqft": getattr(property_analysis, 'concrete_area_sqft', None),
                    "geojson": getattr(property_analysis, 'concrete_geojson', None),
                    "color": "#9CA3AF",  # Light gray
                    "label": "Concrete",
                },
                "buildings": {
                    "area_m2": getattr(property_analysis, 'building_area_m2', None),
                    "geojson": getattr(property_analysis, 'building_geojson', None),
                    "color": "#DC2626",  # Red
                    "label": "Buildings",
                },
            },
            "surfaces_geojson": getattr(property_analysis, 'surfaces_geojson', None),  # FeatureCollection for all
            
            # Total paved area (asphalt + concrete)
            "total_paved_area_m2": getattr(property_analysis, 'total_paved_area_m2', None) or (
                (property_analysis.private_asphalt_area_m2 or 0) + (getattr(property_analysis, 'concrete_area_m2', None) or 0)
            ),
            "total_paved_area_sqft": getattr(property_analysis, 'total_paved_area_sqft', None) or (
                (property_analysis.private_asphalt_area_sqft or 0) + (getattr(property_analysis, 'concrete_area_sqft', None) or 0)
            ),
            
            # ============ LEGACY FIELDS (backwards compat) ============
            # Aggregated metrics (total from CV)
            "total_asphalt_area_m2": property_analysis.total_asphalt_area_m2,
            "total_asphalt_area_sqft": property_analysis.total_asphalt_area_sqft,
            "parking_area_sqft": property_analysis.parking_area_sqft,
            "road_area_sqft": property_analysis.road_area_sqft,
            # Private asphalt (after filtering public roads)
            "private_asphalt_area_m2": property_analysis.private_asphalt_area_m2,
            "private_asphalt_area_sqft": property_analysis.private_asphalt_area_sqft,
            "private_asphalt_geojson": property_analysis.private_asphalt_geojson,
            "public_road_area_m2": property_analysis.public_road_area_m2,
            # Condition
            "weighted_condition_score": property_analysis.weighted_condition_score,
            "worst_tile_score": property_analysis.worst_tile_score,
            "best_tile_score": property_analysis.best_tile_score,
            "total_crack_count": int(property_analysis.total_crack_count) if property_analysis.total_crack_count else 0,
            "total_pothole_count": int(property_analysis.total_pothole_count) if property_analysis.total_pothole_count else 0,
            "total_detection_count": int(property_analysis.total_detection_count) if property_analysis.total_detection_count else 0,
            "damage_density": property_analysis.damage_density,
            # Tile grid info
            "total_tiles": int(property_analysis.total_tiles) if property_analysis.total_tiles else 0,
            "analyzed_tiles": int(property_analysis.analyzed_tiles) if property_analysis.analyzed_tiles else 0,
            "tiles_with_asphalt": int(property_analysis.tiles_with_asphalt) if property_analysis.tiles_with_asphalt else 0,
            "tiles_with_damage": int(property_analysis.tiles_with_damage) if property_analysis.tiles_with_damage else 0,
            "tile_zoom_level": int(property_analysis.tile_zoom_level) if property_analysis.tile_zoom_level else None,
            "tile_grid_rows": int(property_analysis.tile_grid_rows) if property_analysis.tile_grid_rows else None,
            "tile_grid_cols": int(property_analysis.tile_grid_cols) if property_analysis.tile_grid_cols else None,
            # Lead quality
            "lead_quality": property_analysis.lead_quality,
            "hotspot_count": int(property_analysis.hotspot_count) if property_analysis.hotspot_count else 0,
            # Legacy images (for single analysis or backward compat)
            "images": {
                "wide_satellite": property_analysis.wide_image_base64,
                "segmentation": property_analysis.segmentation_image_base64,
                "property_boundary": property_analysis.property_boundary_image_base64,
                "condition_analysis": property_analysis.condition_analysis_image_base64,
            },
            "analyzed_at": property_analysis.analyzed_at.isoformat() if property_analysis.analyzed_at else None,
            "property_boundary": property_boundary_info,
            # Tiles data (for tiled analysis)
            "tiles": tiles_data,
        }
    else:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"📸 No PropertyAnalysis found for {parking_lot_id}")
        
        # Fallback: Create property_analysis-like structure from ParkingLot's Regrid data
        if lot.regrid_parcel_id:
            logger.info(f"   📦 Using Regrid data from ParkingLot model")
            
            # Build property boundary from Regrid polygon
            regrid_polygon_geojson = None
            if lot.regrid_polygon:
                try:
                    regrid_geom = to_shape(lot.regrid_polygon)
                    if hasattr(regrid_geom, 'exterior'):
                        regrid_polygon_geojson = {
                            "type": "Polygon",
                            "coordinates": [list(regrid_geom.exterior.coords)]
                        }
                except Exception as e:
                    logger.warning(f"   Failed to convert Regrid polygon: {e}")
            
            response["property_analysis"] = {
                "id": None,
                "status": lot.evaluation_status or "imagery_captured",
                "analysis_type": "regrid_only",
                "detection_method": None,
                # Property boundary from Regrid
                "property_boundary": {
                    "source": "regrid",
                    "parcel_id": lot.regrid_parcel_id,
                    "owner": lot.regrid_owner,
                    "apn": lot.regrid_apn,
                    "land_use": lot.regrid_land_use,
                    "zoning": lot.regrid_zoning,
                    "polygon": regrid_polygon_geojson,
                },
                # Area from Regrid
                "total_paved_area_sqft": float(lot.area_sqft) if lot.area_sqft else None,
                "private_asphalt_area_sqft": float(lot.area_sqft) if lot.area_sqft else None,
                # Satellite image
                "images": {
                    "wide_satellite": lot.satellite_image_base64,
                },
                "analyzed_at": lot.regrid_fetched_at.isoformat() if lot.regrid_fetched_at else None,
                # Empty analysis fields (not yet analyzed)
                "surfaces": None,
                "surfaces_geojson": None,
                "weighted_condition_score": None,
                "total_crack_count": 0,
                "total_pothole_count": 0,
                "tiles": [],
            }
    
    return ParkingLotDetailResponse(**response)


@router.get("/{parking_lot_id}/businesses")
def get_parking_lot_businesses(
    parking_lot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all businesses associated with a parking lot."""
    lot = db.query(ParkingLot).filter(
        ParkingLot.id == parking_lot_id,
        ParkingLot.user_id == current_user.id
    ).first()
    
    if not lot:
        raise HTTPException(status_code=404, detail="Parking lot not found")
    
    # Use eager loading for associations and businesses
    associations = (
        db.query(ParkingLotBusinessAssociation)
        .filter(ParkingLotBusinessAssociation.parking_lot_id == parking_lot_id)
        .options(joinedload(ParkingLotBusinessAssociation.business))
        .order_by(ParkingLotBusinessAssociation.match_score.desc())
        .all()
    )
    
    results = []
    for assoc in associations:
        business = assoc.business
        if business:
            biz_location = to_shape(business.geometry)
            results.append({
                "id": business.id,
                "name": business.name,
                "phone": business.phone,
                "email": business.email,
                "website": business.website,
                "address": business.address,
                "category": business.category,
                "match_score": float(assoc.match_score),
                "distance_meters": float(assoc.distance_meters),
                "is_primary": assoc.is_primary,
                "location": {"lat": biz_location.y, "lng": biz_location.x},
            })
    
    return results


@router.get("/tiles/{tile_id}/image")
def get_tile_image(
    tile_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the satellite image for a specific analysis tile.
    
    Returns the base64-encoded image for lazy loading on the frontend.
    """
    # Get the tile
    tile = db.query(AnalysisTile).filter(AnalysisTile.id == tile_id).first()
    
    if not tile:
        raise HTTPException(status_code=404, detail="Tile not found")
    
    # Verify user owns this tile's analysis
    analysis = db.query(PropertyAnalysis).filter(
        PropertyAnalysis.id == tile.property_analysis_id,
        PropertyAnalysis.user_id == current_user.id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="Tile not found")
    
    return {
        "id": str(tile.id),
        "tile_index": tile.tile_index,
        "image_base64": tile.satellite_image_base64,
        "segmentation_image_base64": tile.segmentation_image_base64,
        "condition_image_base64": tile.condition_image_base64,
    }
