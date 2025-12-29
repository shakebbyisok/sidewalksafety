"""
SmartAnalysisPipeline - Two-Phase Property Analysis

This is the CORRECT approach to analyzing property asphalt:

Phase 1: AREA DETECTION (coarse)
├── Fetch ONE wide satellite image of entire property
├── Run CV segmentation to find ALL asphalt surfaces
├── Filter out public roads (using OSM)
├── Output: Private asphalt polygons with geo-coordinates

Phase 2: DAMAGE DETECTION (fine)
├── Tile ONLY the detected asphalt areas (not buildings/pools)
├── Fetch high-res tiles for each asphalt region
├── Run crack/pothole detection
├── Output: Damage detections with locations

This ensures:
✅ We only analyze actual asphalt (not buildings)
✅ Fewer tiles = lower API cost
✅ More accurate results
✅ GeoJSON polygons for map display
"""

import logging
import uuid
import math
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from shapely.geometry import Polygon, MultiPolygon, Point, box, mapping
from shapely.ops import unary_union
from io import BytesIO
from PIL import Image

from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape

from app.core.config import settings
from app.core.private_asphalt_service import private_asphalt_service, PrivateAsphaltResult
from app.core.condition_evaluation_service import condition_evaluation_service
from app.core.regrid_service import PropertyParcel

from app.models.property_analysis import PropertyAnalysis
from app.models.analysis_tile import AnalysisTile

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SurfaceRegion:
    """A detected surface region within the property."""
    surface_type: str  # "asphalt", "concrete", "building"
    polygon: Polygon
    area_m2: float
    area_sqft: float
    centroid_lat: float
    centroid_lng: float
    bounds: Dict[str, float]  # min_lat, max_lat, min_lng, max_lng
    color: str  # For UI display
    geojson: Dict  # For frontend display


# Legacy alias for backwards compatibility
AsphaltRegion = SurfaceRegion


@dataclass
class DamageDetection:
    """A detected damage (crack/pothole) with location."""
    detection_type: str  # "crack", "pothole"
    confidence: float
    severity: str  # "minor", "moderate", "severe"
    location_lat: float
    location_lng: float
    pixel_bbox: Dict  # Original bbox in pixels
    area_pixels: int
    geojson: Dict  # Point or polygon for display


@dataclass
class SmartAnalysisResult:
    """Complete result from smart analysis pipeline."""
    # Property info
    property_id: Optional[str] = None
    business_name: Optional[str] = None
    address: Optional[str] = None
    
    # Property boundary (from Regrid)
    property_boundary_polygon: Optional[Polygon] = None
    property_boundary_geojson: Optional[Dict] = None
    property_area_m2: float = 0
    
    # ============ SURFACE DETECTION (Grounded SAM) ============
    # All detected surfaces
    surfaces: List[SurfaceRegion] = field(default_factory=list)
    surfaces_geojson: Optional[Dict] = None  # FeatureCollection for all surfaces
    
    # Asphalt (dark pavement)
    asphalt_polygon: Optional[Polygon] = None
    asphalt_area_m2: float = 0
    asphalt_area_sqft: float = 0
    asphalt_geojson: Optional[Dict] = None
    
    # Concrete (light pavement)
    concrete_polygon: Optional[Polygon] = None
    concrete_area_m2: float = 0
    concrete_area_sqft: float = 0
    concrete_geojson: Optional[Dict] = None
    
    # Total paved area (asphalt + concrete)
    total_paved_area_m2: float = 0
    total_paved_area_sqft: float = 0
    
    # Buildings detected
    building_polygon: Optional[Polygon] = None
    building_area_m2: float = 0
    building_geojson: Optional[Dict] = None
    
    # Legacy fields for backwards compatibility
    asphalt_regions: List[SurfaceRegion] = field(default_factory=list)
    total_asphalt_area_m2: float = 0  # Maps to total_paved_area_m2
    total_asphalt_area_sqft: float = 0  # Maps to total_paved_area_sqft
    
    # Public roads filtered out
    public_road_area_m2: float = 0
    
    # Phase 2: Damage detections
    damage_detections: List[DamageDetection] = field(default_factory=list)
    total_crack_count: int = 0
    total_pothole_count: int = 0
    condition_score: float = 100
    damage_geojson: Optional[Dict] = None  # GeoJSON FeatureCollection of damage
    
    # Analysis metadata
    wide_image_bounds: Optional[Dict] = None
    tiles_analyzed: int = 0
    detection_method: str = "grounded_sam"
    status: str = "pending"
    error_message: Optional[str] = None
    analyzed_at: Optional[datetime] = None


class SmartAnalysisPipeline:
    """
    Two-phase analysis pipeline for accurate property asphalt analysis.
    
    Phase 1: Detect where the asphalt is (wide view)
    Phase 2: Analyze damage in those areas only (zoomed tiles)
    """
    
    # Image sizes
    WIDE_IMAGE_SIZE = 640  # Max for Google Static Maps
    WIDE_IMAGE_SCALE = 2   # 2x for higher resolution (1280x1280 actual)
    
    # Tile sizes for damage detection
    DAMAGE_TILE_SIZE = 640
    DAMAGE_TILE_SCALE = 2
    DAMAGE_ZOOM = 20  # High zoom for crack detection
    
    # Minimum asphalt area to analyze (m²)
    MIN_ASPHALT_AREA = 50
    
    async def analyze_property(
        self,
        db: Session,
        property_boundary: Polygon,
        regrid_parcel: Optional[PropertyParcel],
        lat: float,
        lng: float,
        user_id: uuid.UUID,
        business_id: Optional[uuid.UUID] = None,
        parking_lot_id: Optional[uuid.UUID] = None,
        business_name: Optional[str] = None,
        address: Optional[str] = None,
    ) -> SmartAnalysisResult:
        """
        Run the complete two-phase analysis on a property.
        
        Args:
            db: Database session
            property_boundary: Exact property boundary from Regrid
            regrid_parcel: Full Regrid parcel data
            lat, lng: Property center coordinates
            user_id: User running the analysis
            business_id: Optional linked business
            parking_lot_id: Optional linked parking lot
            business_name: For logging
            address: Property address
            
        Returns:
            SmartAnalysisResult with all analysis data and GeoJSON for display
        """
        result = SmartAnalysisResult(
            business_name=business_name,
            address=address,
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"🎯 SMART ANALYSIS PIPELINE: {business_name or 'Unknown'}")
        logger.info("=" * 60)
        logger.info(f"   📍 Location: ({lat:.6f}, {lng:.6f})")
        logger.info(f"   📋 Address: {address}")
        
        try:
            # Store property boundary
            if property_boundary:
                result.property_boundary_polygon = property_boundary
                result.property_boundary_geojson = self._polygon_to_geojson(
                    property_boundary, 
                    {"type": "property_boundary", "source": "regrid"}
                )
                result.property_area_m2 = self._calculate_area_m2(property_boundary)
                logger.info(f"   📐 Property area: {result.property_area_m2:,.0f} m²")
            
            # ============ PHASE 1: AREA DETECTION ============
            logger.info("")
            logger.info("   🔍 PHASE 1: Detecting asphalt areas...")
            
            phase1_result = await self._phase1_detect_asphalt(
                property_boundary=property_boundary,
                lat=lat,
                lng=lng,
            )
            
            if not phase1_result["success"]:
                result.status = "failed"
                result.error_message = phase1_result.get("error", "Phase 1 failed")
                return result
            
            # Store surface data
            result.surfaces = phase1_result.get("surfaces", [])
            result.surfaces_geojson = phase1_result.get("surfaces_geojson")
            
            # Asphalt
            result.asphalt_polygon = phase1_result.get("asphalt_polygon")
            result.asphalt_area_m2 = phase1_result.get("asphalt_m2", 0)
            result.asphalt_area_sqft = result.asphalt_area_m2 * 10.764
            result.asphalt_geojson = phase1_result.get("asphalt_geojson")
            
            # Concrete
            result.concrete_polygon = phase1_result.get("concrete_polygon")
            result.concrete_area_m2 = phase1_result.get("concrete_m2", 0)
            result.concrete_area_sqft = result.concrete_area_m2 * 10.764
            result.concrete_geojson = phase1_result.get("concrete_geojson")
            
            # Totals
            result.total_paved_area_m2 = phase1_result.get("total_paved_m2", 0)
            result.total_paved_area_sqft = result.total_paved_area_m2 * 10.764
            
            # Buildings
            result.building_polygon = phase1_result.get("building_polygon")
            result.building_area_m2 = phase1_result.get("building_m2", 0)
            result.building_geojson = phase1_result.get("building_geojson")
            
            # Legacy fields
            result.asphalt_regions = phase1_result.get("surfaces", [])
            result.total_asphalt_area_m2 = result.total_paved_area_m2
            result.total_asphalt_area_sqft = result.total_paved_area_sqft
            
            result.public_road_area_m2 = phase1_result.get("public_road_m2", 0)
            result.wide_image_bounds = phase1_result.get("image_bounds")
            
            logger.info(f"   ✅ Detected surfaces:")
            logger.info(f"      Asphalt: {result.asphalt_area_sqft:,.0f} sqft")
            logger.info(f"      Concrete: {result.concrete_area_sqft:,.0f} sqft")
            logger.info(f"      Total paved: {result.total_paved_area_sqft:,.0f} sqft")
            logger.info(f"      Roads filtered: {result.public_road_area_m2:,.0f} m²")
            
            if result.total_paved_area_m2 < self.MIN_ASPHALT_AREA:
                logger.info(f"   ⚠️ Insufficient paved area for damage detection ({result.total_paved_area_m2:.0f}m²)")
                result.status = "completed"
                result.condition_score = 100  # No damage if no asphalt
                result.analyzed_at = datetime.utcnow()
                
                # Still save results so property boundary is visible
                await self._save_results(
                    db=db,
                    result=result,
                    regrid_parcel=regrid_parcel,
                    user_id=user_id,
                    business_id=business_id,
                    parking_lot_id=parking_lot_id,
                    lat=lat,
                    lng=lng,
                )
                
                logger.info("")
                logger.info("=" * 60)
                logger.info(f"⚠️ SMART ANALYSIS COMPLETE (No private asphalt): {business_name or 'Unknown'}")
                logger.info(f"   Property boundary saved for visualization")
                logger.info("=" * 60)
                
                return result
            
            # ============ PHASE 2: DAMAGE DETECTION ============
            logger.info("")
            logger.info("   🔬 PHASE 2: Detecting damage in asphalt areas...")
            
            phase2_result = await self._phase2_detect_damage(
                asphalt_regions=result.asphalt_regions,
                property_boundary=property_boundary,
            )
            
            result.damage_detections = phase2_result["detections"]
            result.total_crack_count = phase2_result["crack_count"]
            result.total_pothole_count = phase2_result["pothole_count"]
            result.condition_score = phase2_result["condition_score"]
            result.damage_geojson = phase2_result["damage_geojson"]
            result.tiles_analyzed = phase2_result["tiles_analyzed"]
            
            logger.info(f"   ✅ Analyzed {result.tiles_analyzed} tiles")
            logger.info(f"      Cracks: {result.total_crack_count}")
            logger.info(f"      Potholes: {result.total_pothole_count}")
            logger.info(f"      Condition: {result.condition_score:.0f}/100")
            
            # ============ SAVE TO DATABASE ============
            logger.info("")
            logger.info("   💾 Saving results...")
            
            await self._save_results(
                db=db,
                result=result,
                regrid_parcel=regrid_parcel,
                user_id=user_id,
                business_id=business_id,
                parking_lot_id=parking_lot_id,
                lat=lat,
                lng=lng,
            )
            
            result.status = "completed"
            result.analyzed_at = datetime.utcnow()
            
            logger.info("")
            logger.info("=" * 60)
            logger.info(f"✅ SMART ANALYSIS COMPLETE: {business_name or 'Unknown'}")
            logger.info(f"   Asphalt: {result.total_asphalt_area_sqft:,.0f} sqft")
            logger.info(f"   Condition: {result.condition_score:.0f}/100")
            logger.info(f"   Damage: {result.total_crack_count} cracks, {result.total_pothole_count} potholes")
            logger.info("=" * 60)
            
            return result
            
        except Exception as e:
            logger.error(f"   ❌ Smart analysis failed: {e}")
            import traceback
            traceback.print_exc()
            result.status = "failed"
            result.error_message = str(e)
            return result
    
    async def _phase1_detect_asphalt(
        self,
        property_boundary: Polygon,
        lat: float,
        lng: float,
    ) -> Dict[str, Any]:
        """
        Phase 1: Detect asphalt areas in the property.
        
        Fetches satellite image(s) and runs asphalt segmentation.
        For large properties, tiles the area to maintain CV accuracy.
        """
        try:
            # Calculate bounds for the wide image
            if property_boundary:
                bounds = property_boundary.bounds  # (minx, miny, maxx, maxy)
                image_bounds = {
                    "min_lng": bounds[0],
                    "min_lat": bounds[1],
                    "max_lng": bounds[2],
                    "max_lat": bounds[3],
                }
                center_lat = (bounds[1] + bounds[3]) / 2
                center_lng = (bounds[0] + bounds[2]) / 2
            else:
                # Estimate bounds from point
                radius = 0.001  # ~100m
                image_bounds = {
                    "min_lng": lng - radius,
                    "min_lat": lat - radius,
                    "max_lng": lng + radius,
                    "max_lat": lat + radius,
                }
                center_lat = lat
                center_lng = lng
            
            # Calculate property dimensions
            lat_span = image_bounds["max_lat"] - image_bounds["min_lat"]
            lng_span = image_bounds["max_lng"] - image_bounds["min_lng"]
            property_width_m = lng_span * 111000 * math.cos(math.radians(center_lat))
            property_height_m = lat_span * 111000
            
            logger.info(f"      📐 Property size: {property_height_m:.0f}m x {property_width_m:.0f}m")
            
            # At zoom 19, one image covers ~160m x 160m (at this latitude)
            # At zoom 20, one image covers ~80m x 80m
            # Use zoom 19 for Phase 1 to balance coverage and accuracy
            zoom = 19
            tile_coverage_m = 160  # Approximate coverage at zoom 19
            
            # Check if property needs multiple tiles
            needs_tiling = property_width_m > tile_coverage_m * 0.9 or property_height_m > tile_coverage_m * 0.9
            
            # Single image for now - can add tiling later for very large properties
            logger.info(f"      📸 Fetching satellite image at zoom {zoom}...")
            
            image_bytes = await self._fetch_satellite_image(
                center_lat, center_lng, zoom,
                self.WIDE_IMAGE_SIZE, self.WIDE_IMAGE_SCALE
            )
            
            if not image_bytes:
                return {"success": False, "error": "Failed to fetch satellite image"}
            
            actual_bounds = self._calculate_image_bounds(
                center_lat, center_lng, zoom,
                self.WIDE_IMAGE_SIZE * self.WIDE_IMAGE_SCALE
            )
            
            logger.info(f"      🎯 Running Grounded SAM surface detection...")
            
            detection_result = await private_asphalt_service.detect_private_asphalt(
                image_bytes=image_bytes,
                image_bounds=actual_bounds,
                property_boundary=property_boundary,
                skip_osm_filter=False,
            )
            
            if not detection_result.success:
                logger.warning(f"      ⚠️ Surface detection failed: {detection_result.error_message}")
                return {"success": False, "error": detection_result.error_message or "Detection failed"}
            
            # Build surface regions for each detected type
            surfaces = []
            
            # Asphalt regions
            if detection_result.asphalt_polygon and not detection_result.asphalt_polygon.is_empty:
                centroid = detection_result.asphalt_polygon.centroid
                bounds = detection_result.asphalt_polygon.bounds
                surfaces.append(SurfaceRegion(
                    surface_type="asphalt",
                    polygon=detection_result.asphalt_polygon,
                    area_m2=detection_result.asphalt_area_m2,
                    area_sqft=detection_result.asphalt_area_sqft,
                    centroid_lat=centroid.y,
                    centroid_lng=centroid.x,
                    bounds={"min_lat": bounds[1], "max_lat": bounds[3], "min_lng": bounds[0], "max_lng": bounds[2]},
                    color="#374151",
                    geojson=detection_result.asphalt_geojson or {}
                ))
            
            # Concrete regions
            if detection_result.concrete_polygon and not detection_result.concrete_polygon.is_empty:
                centroid = detection_result.concrete_polygon.centroid
                bounds = detection_result.concrete_polygon.bounds
                surfaces.append(SurfaceRegion(
                    surface_type="concrete",
                    polygon=detection_result.concrete_polygon,
                    area_m2=detection_result.concrete_area_m2,
                    area_sqft=detection_result.concrete_area_sqft,
                    centroid_lat=centroid.y,
                    centroid_lng=centroid.x,
                    bounds={"min_lat": bounds[1], "max_lat": bounds[3], "min_lng": bounds[0], "max_lng": bounds[2]},
                    color="#9CA3AF",
                    geojson=detection_result.concrete_geojson or {}
                ))
            
            # Build surfaces GeoJSON
            surfaces_geojson = None
            if detection_result.surfaces:
                features = [s.get("geojson") for s in detection_result.surfaces if s.get("geojson")]
                surfaces_geojson = {
                    "type": "FeatureCollection",
                    "features": features,
                }
            
            return {
                "success": True,
                "surfaces": surfaces,
                "surfaces_geojson": surfaces_geojson,
                "asphalt_polygon": detection_result.asphalt_polygon,
                "asphalt_m2": detection_result.asphalt_area_m2,
                "asphalt_geojson": detection_result.asphalt_geojson,
                "concrete_polygon": detection_result.concrete_polygon,
                "concrete_m2": detection_result.concrete_area_m2,
                "concrete_geojson": detection_result.concrete_geojson,
                "total_paved_m2": detection_result.total_paved_area_m2,
                "building_polygon": detection_result.building_polygon,
                "building_m2": detection_result.building_area_m2,
                "building_geojson": detection_result.building_geojson,
                "public_road_m2": detection_result.public_road_area_m2,
                "image_bounds": image_bounds,
            }
            
        except Exception as e:
            logger.error(f"      ❌ Phase 1 failed: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}
    
    async def _phase2_detect_damage(
        self,
        asphalt_regions: List[SurfaceRegion],
        property_boundary: Polygon,
    ) -> Dict[str, Any]:
        """
        Phase 2: Detect damage in the asphalt regions.
        
        Creates high-resolution tiles for each asphalt region and runs crack detection.
        """
        all_detections = []
        total_cracks = 0
        total_potholes = 0
        tiles_analyzed = 0
        all_scores = []
        
        try:
            for idx, region in enumerate(asphalt_regions):
                logger.info(f"      [{idx+1}/{len(asphalt_regions)}] Analyzing region ({region.area_sqft:.0f} sqft)...")
                
                # Calculate how many tiles we need for this region
                tiles_for_region = self._calculate_tiles_for_region(region)
                
                for tile_info in tiles_for_region:
                    # Fetch high-res tile
                    tile_bytes = await self._fetch_satellite_image(
                        tile_info["center_lat"],
                        tile_info["center_lng"],
                        self.DAMAGE_ZOOM,
                        self.DAMAGE_TILE_SIZE,
                        self.DAMAGE_TILE_SCALE,
                    )
                    
                    if not tile_bytes:
                        continue
                    
                    tiles_analyzed += 1
                    
                    # Run damage detection
                    try:
                        condition_result = await condition_evaluation_service.evaluate_condition(
                            image_bytes=tile_bytes,
                            parking_lot_id=f"region_{idx}_tile_{tiles_analyzed}"
                        )
                        
                        if condition_result:
                            score = condition_result.get("condition_score", 100)
                            all_scores.append(score)
                            
                            crack_count = condition_result.get("detection_count", 0)
                            total_cracks += crack_count
                            
                            degradation_areas = condition_result.get("degradation_areas", [])
                            potholes = len([d for d in degradation_areas if "pothole" in d.get("class", "").lower()])
                            total_potholes += potholes
                            
                            # Convert detections to geo-coordinates
                            for det in degradation_areas:
                                detection = self._convert_detection_to_geo(
                                    det, tile_info["bounds"],
                                    self.DAMAGE_TILE_SIZE * self.DAMAGE_TILE_SCALE
                                )
                                if detection:
                                    all_detections.append(detection)
                                    
                    except Exception as e:
                        logger.warning(f"         ⚠️ Damage detection failed: {e}")
            
            # Calculate overall condition score
            condition_score = 100
            if all_scores:
                condition_score = sum(all_scores) / len(all_scores)
            
            # Create damage GeoJSON
            damage_geojson = None
            if all_detections:
                damage_geojson = {
                    "type": "FeatureCollection",
                    "features": [d.geojson for d in all_detections],
                }
            
            return {
                "detections": all_detections,
                "crack_count": total_cracks,
                "pothole_count": total_potholes,
                "condition_score": condition_score,
                "damage_geojson": damage_geojson,
                "tiles_analyzed": tiles_analyzed,
            }
            
        except Exception as e:
            logger.error(f"      ❌ Phase 2 failed: {e}")
            return {
                "detections": [],
                "crack_count": 0,
                "pothole_count": 0,
                "condition_score": 100,
                "damage_geojson": None,
                "tiles_analyzed": tiles_analyzed,
            }
    
    def _calculate_tiles_for_region(self, region: SurfaceRegion) -> List[Dict]:
        """Calculate tile grid to cover an asphalt region."""
        tiles = []
        
        # At zoom 20, each tile covers approximately 80m x 80m
        tile_size_m = 80
        
        bounds = region.bounds
        lat_span = bounds["max_lat"] - bounds["min_lat"]
        lng_span = bounds["max_lng"] - bounds["min_lng"]
        
        # Convert to meters
        lat_span_m = lat_span * 111000
        lng_span_m = lng_span * 111000 * math.cos(math.radians(region.centroid_lat))
        
        # Calculate grid size
        cols = max(1, int(math.ceil(lng_span_m / tile_size_m)))
        rows = max(1, int(math.ceil(lat_span_m / tile_size_m)))
        
        # Limit tiles per region
        max_tiles = 9  # 3x3 max
        if rows * cols > max_tiles:
            scale = math.sqrt(max_tiles / (rows * cols))
            rows = max(1, int(rows * scale))
            cols = max(1, int(cols * scale))
        
        lat_step = lat_span / rows if rows > 1 else lat_span
        lng_step = lng_span / cols if cols > 1 else lng_span
        
        for row in range(rows):
            for col in range(cols):
                tile_center_lat = bounds["min_lat"] + (row + 0.5) * lat_step
                tile_center_lng = bounds["min_lng"] + (col + 0.5) * lng_step
                
                tile_bounds = self._calculate_image_bounds(
                    tile_center_lat, tile_center_lng,
                    self.DAMAGE_ZOOM,
                    self.DAMAGE_TILE_SIZE * self.DAMAGE_TILE_SCALE
                )
                
                tiles.append({
                    "center_lat": tile_center_lat,
                    "center_lng": tile_center_lng,
                    "row": row,
                    "col": col,
                    "bounds": tile_bounds,
                })
        
        return tiles
    
    def _convert_detection_to_geo(
        self,
        detection: Dict,
        tile_bounds: Dict,
        image_size: int
    ) -> Optional[DamageDetection]:
        """Convert a pixel-based detection to geo-coordinates."""
        try:
            # Get detection center
            x = detection.get("x", 0)
            y = detection.get("y", 0)
            width = detection.get("width", 0)
            height = detection.get("height", 0)
            
            # Convert pixel to normalized coordinates
            norm_x = x / image_size
            norm_y = y / image_size
            
            # Convert to geo coordinates
            lat_range = tile_bounds["max_lat"] - tile_bounds["min_lat"]
            lng_range = tile_bounds["max_lng"] - tile_bounds["min_lng"]
            
            lng = tile_bounds["min_lng"] + norm_x * lng_range
            lat = tile_bounds["max_lat"] - norm_y * lat_range
            
            detection_type = detection.get("class", "crack").lower()
            if "pothole" in detection_type:
                detection_type = "pothole"
            else:
                detection_type = "crack"
            
            confidence = detection.get("confidence", 0)
            
            # Determine severity based on size
            area = width * height
            if area > 10000:
                severity = "severe"
            elif area > 5000:
                severity = "moderate"
            else:
                severity = "minor"
            
            return DamageDetection(
                detection_type=detection_type,
                confidence=confidence,
                severity=severity,
                location_lat=lat,
                location_lng=lng,
                pixel_bbox={"x": x, "y": y, "width": width, "height": height},
                area_pixels=int(area),
                geojson={
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lng, lat],
                    },
                    "properties": {
                        "type": detection_type,
                        "severity": severity,
                        "confidence": confidence,
                    },
                },
            )
            
        except Exception as e:
            logger.debug(f"Failed to convert detection: {e}")
            return None
    
    async def _fetch_satellite_image(
        self,
        lat: float,
        lng: float,
        zoom: int,
        size: int,
        scale: int,
    ) -> Optional[bytes]:
        """Fetch satellite image from Google Static Maps API."""
        if not settings.GOOGLE_MAPS_KEY:
            logger.warning("Google Maps API key not configured")
            return None
        
        url = "https://maps.googleapis.com/maps/api/staticmap"
        params = {
            "center": f"{lat},{lng}",
            "zoom": zoom,
            "size": f"{size}x{size}",
            "scale": scale,
            "maptype": "satellite",
            "key": settings.GOOGLE_MAPS_KEY,
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.warning(f"Failed to fetch satellite image: {e}")
            return None
    
    def _calculate_image_bounds(
        self,
        center_lat: float,
        center_lng: float,
        zoom: int,
        image_size_pixels: int,
    ) -> Dict[str, float]:
        """Calculate geographic bounds of an image."""
        # Meters per pixel at this zoom level
        meters_per_pixel = 156543.03 * math.cos(math.radians(center_lat)) / (2 ** zoom)
        
        # Image dimensions in meters
        half_width_m = (image_size_pixels / 2) * meters_per_pixel
        half_height_m = (image_size_pixels / 2) * meters_per_pixel
        
        # Convert to degrees
        lat_offset = half_height_m / 111000
        lng_offset = half_width_m / (111000 * math.cos(math.radians(center_lat)))
        
        return {
            "min_lat": center_lat - lat_offset,
            "max_lat": center_lat + lat_offset,
            "min_lng": center_lng - lng_offset,
            "max_lng": center_lng + lng_offset,
        }
    
    def _calculate_area_m2(self, polygon: Polygon) -> float:
        """Calculate approximate area in square meters."""
        if polygon is None or polygon.is_empty:
            return 0
        
        centroid = polygon.centroid
        center_lat = centroid.y
        
        # Approximate conversion from degrees² to m²
        m_per_deg_lat = 111000
        m_per_deg_lng = 111000 * math.cos(math.radians(center_lat))
        scale = m_per_deg_lat * m_per_deg_lng
        
        return polygon.area * scale
    
    def _polygon_to_geojson(self, polygon: Polygon, properties: Dict) -> Dict:
        """Convert Shapely polygon to GeoJSON Feature."""
        return {
            "type": "Feature",
            "geometry": mapping(polygon),
            "properties": properties,
        }
    
    async def _save_results(
        self,
        db: Session,
        result: SmartAnalysisResult,
        regrid_parcel: Optional[PropertyParcel],
        user_id: uuid.UUID,
        business_id: Optional[uuid.UUID],
        parking_lot_id: Optional[uuid.UUID],
        lat: float,
        lng: float,
    ) -> None:
        """Save analysis results to database."""
        import json
        
        analysis_id = uuid.uuid4()
        
        # Check if analysis already exists for this parking lot
        existing = db.query(PropertyAnalysis).filter(
            PropertyAnalysis.parking_lot_id == parking_lot_id
        ).first()
        
        if existing:
            # Update existing analysis
            existing.analysis_type = "smart"
            existing.status = "completed"
            existing.analyzed_at = datetime.utcnow()
            
            # Property boundary
            if result.property_boundary_polygon:
                existing.property_boundary_polygon = from_shape(result.property_boundary_polygon, srid=4326)
            existing.property_boundary_source = "regrid" if regrid_parcel else "estimated"
            if regrid_parcel:
                existing.property_parcel_id = regrid_parcel.parcel_id
                existing.property_owner = regrid_parcel.owner
                existing.property_apn = regrid_parcel.apn
                existing.property_land_use = regrid_parcel.land_use
                existing.property_zoning = regrid_parcel.zoning
            
            # DEBUG: Log what we're updating
            logger.info(f"   📝 UPDATING VALUES:")
            logger.info(f"      result.total_paved_area_m2 = {result.total_paved_area_m2}")
            logger.info(f"      result.total_paved_area_sqft = {result.total_paved_area_sqft}")
            logger.info(f"      result.asphalt_area_m2 = {result.asphalt_area_m2}")
            logger.info(f"      result.asphalt_area_sqft = {result.asphalt_area_sqft}")
            
            # Surface metrics - save to all relevant columns
            existing.total_asphalt_area_m2 = result.total_paved_area_m2
            existing.total_asphalt_area_sqft = result.total_paved_area_sqft
            existing.total_paved_area_m2 = result.total_paved_area_m2  # Also save here
            existing.total_paved_area_sqft = result.total_paved_area_sqft  # Also save here
            existing.private_asphalt_area_m2 = result.asphalt_area_m2
            existing.private_asphalt_area_sqft = result.asphalt_area_sqft
            existing.private_asphalt_geojson = result.surfaces_geojson  # All surfaces
            existing.surfaces_geojson = result.surfaces_geojson  # Also save here
            existing.public_road_area_m2 = result.public_road_area_m2
            
            # Store concrete data if column exists
            if hasattr(existing, 'concrete_area_m2'):
                existing.concrete_area_m2 = result.concrete_area_m2
                existing.concrete_area_sqft = result.concrete_area_sqft
            
            # Condition metrics  
            existing.weighted_condition_score = result.condition_score
            existing.total_crack_count = result.total_crack_count
            existing.total_pothole_count = result.total_pothole_count
            existing.total_detection_count = result.total_crack_count + result.total_pothole_count
            
            # Tile info
            existing.total_tiles = result.tiles_analyzed
            existing.analyzed_tiles = result.tiles_analyzed
            existing.tiles_with_asphalt = len(result.surfaces)
            existing.tiles_with_damage = len([d for d in result.damage_detections])
            
            # Lead quality
            existing.lead_quality = self._calculate_lead_quality(result)
            existing.hotspot_count = len([d for d in result.damage_detections if d.severity in ("severe", "moderate")])
            
            db.commit()
            result.property_id = str(existing.id)
            logger.info(f"   ✅ Updated existing PropertyAnalysis: {existing.id}")
            return
        
        # DEBUG: Log what we're about to save
        logger.info(f"   📝 SAVING VALUES:")
        logger.info(f"      result.total_paved_area_m2 = {result.total_paved_area_m2}")
        logger.info(f"      result.total_paved_area_sqft = {result.total_paved_area_sqft}")
        logger.info(f"      result.asphalt_area_m2 = {result.asphalt_area_m2}")
        logger.info(f"      result.asphalt_area_sqft = {result.asphalt_area_sqft}")
        logger.info(f"      result.surfaces_geojson = {type(result.surfaces_geojson)} with {len(result.surfaces_geojson.get('features', [])) if result.surfaces_geojson else 0} features")
        
        # Create new PropertyAnalysis record
        property_analysis = PropertyAnalysis(
            id=analysis_id,
            parking_lot_id=parking_lot_id,
            user_id=user_id,
            business_id=business_id,
            business_location=from_shape(Point(lng, lat), srid=4326),
            
            # Property boundary
            property_boundary_polygon=from_shape(result.property_boundary_polygon, srid=4326) if result.property_boundary_polygon else None,
            property_boundary_source="regrid" if regrid_parcel else "estimated",
            property_parcel_id=regrid_parcel.parcel_id if regrid_parcel else None,
            property_owner=regrid_parcel.owner if regrid_parcel else None,
            property_apn=regrid_parcel.apn if regrid_parcel else None,
            property_land_use=regrid_parcel.land_use if regrid_parcel else None,
            property_zoning=regrid_parcel.zoning if regrid_parcel else None,
            
            # Analysis type
            analysis_type="smart",
            
            # Surface metrics - ALSO save to total_paved columns
            total_asphalt_area_m2=result.total_paved_area_m2,
            total_asphalt_area_sqft=result.total_paved_area_sqft,
            total_paved_area_m2=result.total_paved_area_m2,  # NEW: Save to correct column
            total_paved_area_sqft=result.total_paved_area_sqft,  # NEW: Save to correct column
            private_asphalt_area_m2=result.asphalt_area_m2,
            private_asphalt_area_sqft=result.asphalt_area_sqft,
            private_asphalt_geojson=result.surfaces_geojson,  # All surfaces GeoJSON
            surfaces_geojson=result.surfaces_geojson,  # NEW: Also save to dedicated column
            public_road_area_m2=result.public_road_area_m2,
            
            # Condition metrics
            weighted_condition_score=result.condition_score,
            total_crack_count=result.total_crack_count,
            total_pothole_count=result.total_pothole_count,
            total_detection_count=result.total_crack_count + result.total_pothole_count,
            
            # Tile info
            total_tiles=result.tiles_analyzed,
            analyzed_tiles=result.tiles_analyzed,
            tiles_with_asphalt=len(result.surfaces),
            tiles_with_damage=len([d for d in result.damage_detections]),
            
            # Lead quality
            lead_quality=self._calculate_lead_quality(result),
            hotspot_count=len([d for d in result.damage_detections if d.severity in ("severe", "moderate")]),
            
            # Status
            status="completed",
            analyzed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        
        db.add(property_analysis)
        db.commit()
        db.refresh(property_analysis)
        
        result.property_id = str(analysis_id)
        logger.info(f"   ✅ Created new PropertyAnalysis: {analysis_id}")
        
        # Update parking lot with analysis results
        if parking_lot_id:
            from app.models.parking_lot import ParkingLot
            parking_lot = db.query(ParkingLot).filter(ParkingLot.id == parking_lot_id).first()
            if parking_lot:
                parking_lot.is_evaluated = True
                parking_lot.condition_score = result.condition_score
                parking_lot.evaluated_at = datetime.utcnow()
                db.commit()
                logger.info(f"   ✅ Updated ParkingLot: score={result.condition_score:.0f}")
    
    def _calculate_lead_quality(self, result: SmartAnalysisResult) -> str:
        """Calculate lead quality based on area and condition."""
        area = result.total_asphalt_area_sqft
        score = result.condition_score
        
        if area >= 50000 and score <= 40:
            return "premium"
        elif area >= 25000 and score <= 50:
            return "high"
        elif area >= 10000 and score <= 60:
            return "standard"
        else:
            return "low"


# Singleton instance
smart_analysis_pipeline = SmartAnalysisPipeline()

