from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from decimal import Decimal


class Coordinates(BaseModel):
    lat: float
    lng: float


class GeoJSONPolygon(BaseModel):
    type: str = "Polygon"
    coordinates: List[List[List[float]]]


class GeoJSONPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float]


# ============ Parking Lot Schemas ============

class ParkingLotBase(BaseModel):
    area_m2: Optional[float] = None
    area_sqft: Optional[float] = None
    operator_name: Optional[str] = None
    address: Optional[str] = None
    surface_type: Optional[str] = None


class ParkingLotCreate(ParkingLotBase):
    geometry: Optional[GeoJSONPolygon] = None
    centroid: Coordinates
    inrix_id: Optional[str] = None
    here_id: Optional[str] = None
    osm_id: Optional[str] = None
    data_sources: List[str] = []
    raw_metadata: Optional[Dict[str, Any]] = None


class ParkingLotCondition(BaseModel):
    condition_score: Optional[float] = None
    crack_density: Optional[float] = None
    pothole_score: Optional[float] = None
    line_fading_score: Optional[float] = None
    degradation_areas: Optional[List[Dict[str, Any]]] = None


# ============ Business Summary (for embedding) ============

class BusinessSummary(BaseModel):
    id: UUID
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None

    class Config:
        from_attributes = True


class ParkingLotResponse(ParkingLotBase):
    id: UUID
    centroid: Coordinates
    geometry: Optional[GeoJSONPolygon] = None
    
    # Condition
    condition_score: Optional[float] = None
    crack_density: Optional[float] = None
    pothole_score: Optional[float] = None
    line_fading_score: Optional[float] = None
    
    # Imagery
    satellite_image_url: Optional[str] = None
    
    # Status
    is_evaluated: bool
    data_sources: List[str]
    
    # Business-first discovery fields
    business_type_tier: Optional[str] = None  # "premium", "high", "standard"
    discovery_mode: Optional[str] = None  # "business_first", "parking_first"
    
    # Timestamps
    created_at: datetime
    evaluated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TileSummary(BaseModel):
    """Summary of a single analysis tile."""
    id: str
    tile_index: int
    center_lat: float
    center_lng: float
    zoom_level: int
    bounds: Dict[str, float]
    # Total asphalt from CV
    asphalt_area_m2: Optional[float] = 0
    # Private asphalt (after filtering public roads)
    private_asphalt_area_m2: Optional[float] = None
    private_asphalt_area_sqft: Optional[float] = None
    private_asphalt_geojson: Optional[Dict[str, Any]] = None
    # Public roads filtered out
    public_road_area_m2: Optional[float] = None
    asphalt_source: Optional[str] = None
    # Condition
    condition_score: Optional[float] = 100
    crack_count: Optional[int] = 0
    pothole_count: Optional[int] = 0
    status: str = "pending"
    has_image: bool = False


class SurfaceBreakdown(BaseModel):
    """Surface type breakdown (asphalt/concrete/buildings)."""
    area_m2: Optional[float] = None
    area_sqft: Optional[float] = None
    geojson: Optional[Dict[str, Any]] = None
    color: Optional[str] = None
    label: Optional[str] = None


class SurfacesData(BaseModel):
    """All surface type breakdowns."""
    asphalt: Optional[SurfaceBreakdown] = None
    concrete: Optional[SurfaceBreakdown] = None
    buildings: Optional[SurfaceBreakdown] = None


class PropertyAnalysisSummary(BaseModel):
    """Summary of property analysis for embedding in parking lot response."""
    id: str
    status: str
    analysis_type: Optional[str] = "single"  # "single" or "tiled"
    detection_method: Optional[str] = None  # "grounded_sam", "legacy_cv"
    
    # ============ SURFACE TYPE BREAKDOWN (NEW) ============
    surfaces: Optional[SurfacesData] = None
    surfaces_geojson: Optional[Dict[str, Any]] = None  # FeatureCollection for all surfaces
    
    # Total paved (asphalt + concrete)
    total_paved_area_m2: Optional[float] = None
    total_paved_area_sqft: Optional[float] = None
    
    # ============ LEGACY FIELDS (backwards compat) ============
    # Aggregated metrics
    total_asphalt_area_m2: Optional[float] = None
    total_asphalt_area_sqft: Optional[float] = None
    parking_area_sqft: Optional[float] = None
    road_area_sqft: Optional[float] = None
    
    # Private asphalt (after filtering public roads)
    private_asphalt_area_m2: Optional[float] = None
    private_asphalt_area_sqft: Optional[float] = None
    private_asphalt_geojson: Optional[Dict[str, Any]] = None
    public_road_area_m2: Optional[float] = None
    
    # Condition
    weighted_condition_score: Optional[float] = None
    worst_tile_score: Optional[float] = None
    best_tile_score: Optional[float] = None
    total_crack_count: int = 0
    total_pothole_count: int = 0
    total_detection_count: int = 0
    damage_density: Optional[float] = None
    
    # Tile grid info
    total_tiles: int = 0
    analyzed_tiles: int = 0
    tiles_with_asphalt: int = 0
    tiles_with_damage: int = 0
    tile_zoom_level: Optional[int] = None
    tile_grid_rows: Optional[int] = None
    tile_grid_cols: Optional[int] = None
    
    # Lead quality
    lead_quality: Optional[str] = None
    hotspot_count: int = 0
    
    # Legacy images (for single analysis)
    images: Dict[str, Optional[str]] = {}
    analyzed_at: Optional[str] = None
    
    # Property boundary info
    property_boundary: Optional[Dict[str, Any]] = None
    
    # Tiles data (for tiled analysis)
    tiles: List[TileSummary] = []


class ParkingLotDetailResponse(ParkingLotResponse):
    degradation_areas: Optional[List[Dict[str, Any]]] = None
    raw_metadata: Optional[Dict[str, Any]] = None
    evaluation_error: Optional[str] = None
    updated_at: Optional[datetime] = None
    business: Optional[BusinessSummary] = None
    match_score: Optional[float] = None
    distance_meters: Optional[float] = None
    property_analysis: Optional[PropertyAnalysisSummary] = None

    class Config:
        from_attributes = True


class ParkingLotMapResponse(BaseModel):
    """Optimized response for map display."""
    id: UUID
    centroid: Coordinates
    area_m2: Optional[float] = None
    condition_score: Optional[float] = None
    is_evaluated: bool
    has_business: bool
    business_name: Optional[str] = None
    business_type_tier: Optional[str] = None  # "premium", "high", "standard"
    business: Optional[BusinessSummary] = None

    class Config:
        from_attributes = True


class ParkingLotWithBusiness(ParkingLotResponse):
    """Parking lot with associated business info."""
    business: Optional[BusinessSummary] = None
    match_score: Optional[float] = None
    distance_meters: Optional[float] = None
    # Analysis data
    paved_area_sqft: Optional[float] = None
    crack_count: Optional[int] = None
    pothole_count: Optional[int] = None
    property_boundary_source: Optional[str] = None
    lead_quality: Optional[str] = None

    class Config:
        from_attributes = True


# ============ List/Filter Schemas ============

class ParkingLotListParams(BaseModel):
    min_area_m2: Optional[float] = None
    max_condition_score: Optional[float] = None  # Lower = worse = better lead
    min_match_score: Optional[float] = None
    has_business: Optional[bool] = None
    is_evaluated: Optional[bool] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ParkingLotListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: List[ParkingLotWithBusiness]


# Forward reference update
ParkingLotWithBusiness.model_rebuild()

