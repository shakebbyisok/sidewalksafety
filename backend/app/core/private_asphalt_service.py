"""
Private Asphalt Detection Service

SIMPLIFIED APPROACH:
1. We have the EXACT property boundary from Regrid
2. Run CV to detect paved surfaces (asphalt, concrete, buildings)
3. CLIP all detected surfaces to the Regrid boundary
4. Everything inside the boundary = private property

No OSM filtering needed - the Regrid boundary defines what's private.
"""

import logging
import math
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from shapely.geometry import Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
from io import BytesIO
from PIL import Image

from app.core.grounded_sam_service import (
    grounded_sam_service,
    SurfaceDetectionResult,
)

logger = logging.getLogger(__name__)


@dataclass
class PrivateAsphaltResult:
    """Result of paved surface detection clipped to property boundary."""
    
    # ============ PAVED SURFACES (clipped to property boundary) ============
    paved_polygon: Optional[Polygon] = None  # All paved surfaces merged
    paved_area_m2: float = 0
    paved_area_sqft: float = 0
    paved_geojson: Optional[Dict] = None  # GeoJSON for frontend display
    
    # ============ BUILDINGS (for reference) ============
    building_polygon: Optional[Polygon] = None
    building_area_m2: float = 0
    building_geojson: Optional[Dict] = None
    
    # ============ LEGACY FIELDS (backwards compat) ============
    private_asphalt_polygon: Optional[Polygon] = None
    private_asphalt_area_m2: float = 0
    private_asphalt_area_sqft: float = 0
    asphalt_polygon: Optional[Polygon] = None
    asphalt_area_m2: float = 0
    asphalt_area_sqft: float = 0
    asphalt_geojson: Optional[Dict] = None
    concrete_polygon: Optional[Polygon] = None
    concrete_area_m2: float = 0
    concrete_area_sqft: float = 0
    concrete_geojson: Optional[Dict] = None
    total_paved_polygon: Optional[Polygon] = None
    total_paved_area_m2: float = 0
    total_paved_area_sqft: float = 0
    total_asphalt_area_m2: float = 0
    public_road_area_m2: float = 0
    public_road_polygon: Optional[Polygon] = None
    building_polygons: List[Polygon] = field(default_factory=list)
    
    # ============ SURFACE BREAKDOWN FOR UI ============
    surfaces: List[Dict] = field(default_factory=list)
    
    # ============ METADATA ============
    detection_method: str = "roboflow"
    osm_road_filter_used: bool = False  # No longer used
    source: str = "cv_clipped_to_boundary"
    success: bool = False
    error_message: Optional[str] = None
    raw_detection: Optional[SurfaceDetectionResult] = None
    
    @property
    def has_paved_surfaces(self) -> bool:
        return self.paved_area_m2 > 0
    
    @property
    def has_private_asphalt(self) -> bool:
        return self.paved_area_m2 > 0


class PrivateAsphaltService:
    """
    Detects paved surfaces from satellite imagery and clips to property boundary.
    
    SIMPLIFIED APPROACH:
    1. Run CV to detect paved surfaces (roads, parking lots)
    2. CLIP detected surfaces to the Regrid property boundary
    3. Return clipped polygons as GeoJSON for display
    
    No OSM filtering - the Regrid boundary defines what's private.
    """
    
    MIN_PAVED_AREA_M2 = 50
    
    SURFACE_COLORS = {
        "paved": "#10B981",     # Emerald green for paved surfaces
        "building": "#DC2626",  # Red for buildings
    }
    
    async def detect_private_asphalt(
        self,
        image_bytes: bytes,
        image_bounds: Dict[str, float],
        property_boundary: Optional[Polygon] = None,
        skip_osm_filter: bool = True,  # Always skip OSM now
    ) -> PrivateAsphaltResult:
        """
        Detect paved surfaces and clip to property boundary.
        
        Args:
            image_bytes: Satellite image bytes
            image_bounds: {min_lat, max_lat, min_lng, max_lng}
            property_boundary: Regrid property boundary to clip to (REQUIRED for accuracy)
            
        Returns:
            PrivateAsphaltResult with paved surface polygons clipped to boundary
        """
        result = PrivateAsphaltResult()
        
        try:
            # ============ STEP 1: Run CV Detection ============
            logger.info("   🎯 Running CV surface detection...")
            
            detection = await grounded_sam_service.detect_surfaces(
                image_bytes=image_bytes,
                image_bounds=image_bounds,
                property_boundary=property_boundary,
            )
            
            result.raw_detection = detection
            
            if not detection.success:
                logger.warning(f"   ⚠️ CV detection failed: {detection.error_message}")
                result.error_message = detection.error_message
                result.source = "detection_failed"
                return result
            
            # ============ STEP 2: Get detected paved surfaces ============
            # The grounded_sam_service already clips to property_boundary
            paved_polygon = detection.asphalt_polygon  # This is all paved surfaces
            
            if paved_polygon is None or paved_polygon.is_empty:
                logger.info("   ℹ️ No paved surfaces detected")
                result.source = "no_pavement"
                result.success = True
                return result
            
            # ============ STEP 3: Calculate areas and build GeoJSON ============
            paved_area_m2 = self._calculate_area_m2(paved_polygon, image_bounds)
            paved_area_sqft = paved_area_m2 * 10.764
            
            if paved_area_m2 < self.MIN_PAVED_AREA_M2:
                logger.info(f"   ℹ️ Paved area too small ({paved_area_m2:.0f}m²)")
                result.source = "no_pavement"
                result.success = True
                return result
            
            # Build GeoJSON for frontend display
            paved_geojson = self._polygon_to_geojson(
                paved_polygon,
                {
                    "type": "paved",
                    "color": self.SURFACE_COLORS["paved"],
                    "area_m2": paved_area_m2,
                    "area_sqft": paved_area_sqft,
                    "label": "Paved Surfaces",
                }
            )
            
            # ============ STEP 4: Populate result ============
            result.paved_polygon = paved_polygon
            result.paved_area_m2 = paved_area_m2
            result.paved_area_sqft = paved_area_sqft
            result.paved_geojson = paved_geojson
            
            # Legacy fields for backwards compatibility
            result.asphalt_polygon = paved_polygon
            result.asphalt_area_m2 = paved_area_m2
            result.asphalt_area_sqft = paved_area_sqft
            result.asphalt_geojson = paved_geojson
            result.private_asphalt_polygon = paved_polygon
            result.private_asphalt_area_m2 = paved_area_m2
            result.private_asphalt_area_sqft = paved_area_sqft
            result.total_paved_polygon = paved_polygon
            result.total_paved_area_m2 = paved_area_m2
            result.total_paved_area_sqft = paved_area_sqft
            result.total_asphalt_area_m2 = paved_area_m2
            
            # Handle buildings if detected
            if detection.building_polygon and not detection.building_polygon.is_empty:
                result.building_polygon = detection.building_polygon
                result.building_area_m2 = self._calculate_area_m2(detection.building_polygon, image_bounds)
                result.building_geojson = self._polygon_to_geojson(
                    detection.building_polygon,
                    {"type": "building", "color": self.SURFACE_COLORS["building"]}
                )
                result.building_polygons = [detection.building_polygon]
            
            # Build surfaces list for UI
            result.surfaces = [{
                "type": "paved",
                "label": "Paved Surfaces",
                "color": self.SURFACE_COLORS["paved"],
                "area_m2": paved_area_m2,
                "area_sqft": paved_area_sqft,
                "geojson": paved_geojson,
            }]
            
            if result.building_polygon:
                result.surfaces.append({
                    "type": "building",
                    "label": "Buildings",
                    "color": self.SURFACE_COLORS["building"],
                    "area_m2": result.building_area_m2,
                    "area_sqft": result.building_area_m2 * 10.764,
                    "geojson": result.building_geojson,
                })
            
            result.success = True
            result.source = "cv_clipped_to_boundary"
            result.detection_method = "roboflow"
            result.osm_road_filter_used = False
            
            logger.info(f"   ✅ Detected {paved_area_sqft:,.0f} sqft of paved surfaces")
            
            return result
            
        except Exception as e:
            logger.error(f"   ❌ Surface detection failed: {e}")
            import traceback
            traceback.print_exc()
            result.error_message = str(e)
            result.source = "error"
            return result
    
    def _polygon_to_geojson(
        self,
        polygon: Polygon,
        properties: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Convert polygon to GeoJSON Feature."""
        if polygon is None or polygon.is_empty:
            return None
        
        try:
            return {
                "type": "Feature",
                "geometry": mapping(polygon),
                "properties": properties or {}
            }
        except Exception as e:
            logger.warning(f"   ⚠️ Failed to convert polygon: {e}")
            return None
    
    def _calculate_area_m2(self, polygon, bounds: Dict[str, float]) -> float:
        """Calculate approximate area in square meters."""
        if polygon is None or polygon.is_empty:
            return 0
        
        center_lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
        m_per_deg_lat = 111000
        m_per_deg_lng = 111000 * math.cos(math.radians(center_lat))
        scale = m_per_deg_lat * m_per_deg_lng
        
        return polygon.area * scale
    
    def get_polygon_geojson(
        self,
        polygon: Polygon,
        properties: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Convert polygon to GeoJSON for frontend display."""
        return self._polygon_to_geojson(polygon, properties)


# Singleton instance
private_asphalt_service = PrivateAsphaltService()

