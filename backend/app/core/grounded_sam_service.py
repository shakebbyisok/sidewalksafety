"""
GroundedSAMService - Surface Detection Service

Primary: Replicate's hosted Grounded SAM API (high accuracy, paid)
Fallback: Roboflow's satellite-building-segmentation model (free)

Detects:
- Asphalt (dark pavement - parking lots, driveways)
- Concrete (light pavement - sidewalks, some parking areas)  
- Buildings (to exclude from analysis)

When Replicate credits are unavailable, automatically falls back to
the free Roboflow model which detects "road" (paved surfaces) and "building".
"""

import logging
import httpx
import base64
import time
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from shapely.geometry import Polygon, MultiPolygon, mapping
from shapely.ops import unary_union
from io import BytesIO
from PIL import Image
import math

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DetectedSurface:
    """A detected surface with its polygon and metadata."""
    surface_type: str  # "asphalt", "concrete", "building"
    polygon: Polygon
    confidence: float
    area_m2: float
    area_sqft: float
    color: str  # For UI display
    geojson: Dict


@dataclass 
class SurfaceDetectionResult:
    """Complete result from surface detection."""
    # Detected surfaces by type
    asphalt_surfaces: List[DetectedSurface] = field(default_factory=list)
    concrete_surfaces: List[DetectedSurface] = field(default_factory=list)
    building_surfaces: List[DetectedSurface] = field(default_factory=list)
    
    # Merged polygons for easy access
    asphalt_polygon: Optional[Polygon] = None
    concrete_polygon: Optional[Polygon] = None
    building_polygon: Optional[Polygon] = None
    
    # Total areas
    total_asphalt_area_m2: float = 0
    total_asphalt_area_sqft: float = 0
    total_concrete_area_m2: float = 0
    total_concrete_area_sqft: float = 0
    total_paved_area_m2: float = 0  # asphalt + concrete
    total_paved_area_sqft: float = 0
    
    # Metadata
    detection_method: str = "grounded_sam_replicate"
    image_width: int = 0
    image_height: int = 0
    success: bool = False
    error_message: Optional[str] = None


class GroundedSAMService:
    """
    Surface detection using Replicate's hosted Grounded SAM API.
    
    Uses the combined Grounding DINO + SAM model:
    - Grounding DINO: Text-prompted object detection
    - SAM: Pixel-perfect segmentation masks
    
    This provides high-accuracy zero-shot segmentation for any surface type.
    """
    
    # Replicate API endpoints
    REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"
    
    # Grounded SAM model on Replicate
    # https://replicate.com/schananas/grounded_sam
    GROUNDED_SAM_MODEL = "schananas/grounded_sam:ee871c19efb1941f55f66a3d7d960428c8a5afcb77449547fe8e5a3ab9ebc21c"
    
    # Detection prompts for each surface type
    SURFACE_PROMPTS = {
        "asphalt": "dark asphalt parking lot . asphalt driveway . black pavement . dark paved surface",
        "concrete": "light gray concrete . white concrete parking lot . cement surface . light pavement",
        "building": "building rooftop . building roof . structure roof",
    }
    
    # Colors for UI display
    SURFACE_COLORS = {
        "asphalt": "#374151",  # Dark gray
        "concrete": "#9CA3AF",  # Light gray
        "building": "#DC2626",  # Red
    }
    
    # Confidence thresholds
    MIN_CONFIDENCE = 0.25
    MIN_AREA_M2 = 20
    
    def __init__(self):
        self.api_token = settings.REPLICATE_API_TOKEN
        self.is_configured = bool(self.api_token)
        self._replicate_failed = False  # Track if Replicate is failing (billing issues)
        
        if self.is_configured:
            logger.info("✅ GroundedSAM service configured with Replicate API")
        else:
            logger.info("ℹ️ Replicate not configured - will use Roboflow fallback")
    
    async def detect_surfaces(
        self,
        image_bytes: bytes,
        image_bounds: Dict[str, float],
        property_boundary: Optional[Polygon] = None,
        detect_asphalt: bool = True,
        detect_concrete: bool = True,
        detect_buildings: bool = True,
    ) -> SurfaceDetectionResult:
        """
        Detect surfaces in a satellite image.
        
        SIMPLIFIED: Uses Roboflow's free satellite-building-segmentation model.
        The "road" class includes all paved surfaces (parking lots, driveways).
        
        Args:
            image_bytes: Satellite image as bytes
            image_bounds: Geographic bounds {min_lat, max_lat, min_lng, max_lng}
            property_boundary: Optional property boundary to clip results
            detect_asphalt: Whether to detect asphalt surfaces
            detect_concrete: Whether to detect concrete surfaces
            detect_buildings: Whether to detect buildings
            
        Returns:
            SurfaceDetectionResult with all detected surfaces
        """
        # SIMPLIFIED: Always use Roboflow since it's free and works
        # Skip Replicate (paid API with billing issues)
        logger.info("   🔄 Using Roboflow satellite-building-segmentation model...")
        return await self._detect_with_roboflow_fallback(
            image_bytes, image_bounds, property_boundary
        )
        
        # DISABLED: Replicate Grounded SAM (uncomment if billing is resolved)
        # Try Replicate first if configured and not known to be failing
        if False and self.is_configured and not self._replicate_failed:
            result = await self._detect_with_replicate(
                image_bytes, image_bounds, property_boundary,
                detect_asphalt, detect_concrete, detect_buildings
            )
            
            if result.success:
                return result
            
            # Check if billing/payment issue
            if result.error_message and ("402" in result.error_message or "Payment" in result.error_message or "credit" in result.error_message.lower()):
                logger.warning("   ⚠️ Replicate billing issue detected - switching to Roboflow fallback")
                self._replicate_failed = True
        
        # Fallback to Roboflow
        logger.info("   🔄 Using Roboflow segmentation model (free fallback)...")
        return await self._detect_with_roboflow_fallback(
            image_bytes, image_bounds, property_boundary
        )
    
    async def _detect_with_replicate(
        self,
        image_bytes: bytes,
        image_bounds: Dict[str, float],
        property_boundary: Optional[Polygon] = None,
        detect_asphalt: bool = True,
        detect_concrete: bool = True,
        detect_buildings: bool = True,
    ) -> SurfaceDetectionResult:
        """Detect surfaces using Replicate's Grounded SAM."""
        result = SurfaceDetectionResult()
        billing_error = False
        
        try:
            # Get image dimensions
            img = Image.open(BytesIO(image_bytes))
            result.image_width, result.image_height = img.size
            
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
                buffer = BytesIO()
                img.save(buffer, format='JPEG', quality=95)
                image_bytes = buffer.getvalue()
            
            # Encode image to base64 data URI
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            image_data_uri = f"data:image/jpeg;base64,{image_base64}"
            
            # Build combined prompt for all surfaces we want to detect
            prompts_to_run = []
            if detect_asphalt:
                prompts_to_run.append(("asphalt", self.SURFACE_PROMPTS["asphalt"]))
            if detect_concrete:
                prompts_to_run.append(("concrete", self.SURFACE_PROMPTS["concrete"]))
            if detect_buildings:
                prompts_to_run.append(("building", self.SURFACE_PROMPTS["building"]))
            
            logger.info(f"🎯 Running Grounded SAM via Replicate for {len(prompts_to_run)} surface types...")
            
            # Run detection for each surface type
            for surface_type, prompt in prompts_to_run:
                logger.info(f"   🔍 Detecting {surface_type}...")
                
                surfaces, error = await self._run_grounded_sam(
                    image_data_uri=image_data_uri,
                    prompt=prompt,
                    surface_type=surface_type,
                    image_bounds=image_bounds,
                    image_width=result.image_width,
                    image_height=result.image_height,
                    property_boundary=property_boundary,
                )
                
                # Check if we got a billing error
                if error and ("402" in error or "Payment" in error or "credit" in error.lower()):
                    billing_error = True
                    result.error_message = error
                    break  # Stop trying, switch to fallback
                
                if surface_type == "asphalt":
                    result.asphalt_surfaces = surfaces
                elif surface_type == "concrete":
                    result.concrete_surfaces = surfaces
                elif surface_type == "building":
                    result.building_surfaces = surfaces
                
                logger.info(f"      ✅ Found {len(surfaces)} {surface_type} regions")
            
            # If billing error, return failed result to trigger fallback
            if billing_error:
                result.success = False
                return result
            
            # Aggregate results
            result = self._aggregate_results(result, image_bounds)
            result.success = True
            
            logger.info(f"   📊 Total asphalt: {result.total_asphalt_area_sqft:,.0f} sqft")
            logger.info(f"   📊 Total concrete: {result.total_concrete_area_sqft:,.0f} sqft")
            logger.info(f"   📊 Total paved: {result.total_paved_area_sqft:,.0f} sqft")
            
            return result
            
        except Exception as e:
            logger.error(f"   ❌ Surface detection failed: {e}")
            import traceback
            traceback.print_exc()
            result.error_message = str(e)
            return result
    
    async def _run_grounded_sam(
        self,
        image_data_uri: str,
        prompt: str,
        surface_type: str,
        image_bounds: Dict[str, float],
        image_width: int,
        image_height: int,
        property_boundary: Optional[Polygon] = None,
    ) -> tuple[List[DetectedSurface], Optional[str]]:
        """
        Run Grounded SAM via Replicate API.
        
        Returns tuple of (list of detected surfaces, error message if any).
        """
        detected_surfaces = []
        
        try:
            headers = {
                "Authorization": f"Token {self.api_token}",
                "Content-Type": "application/json",
            }
            
            # Prepare request payload
            payload = {
                "version": self.GROUNDED_SAM_MODEL.split(":")[1],
                "input": {
                    "image": image_data_uri,
                    "text_prompt": prompt,
                    "box_threshold": 0.25,
                    "text_threshold": 0.25,
                }
            }
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Start the prediction
                logger.debug(f"      🚀 Starting Replicate prediction...")
                response = await client.post(
                    self.REPLICATE_API_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                prediction = response.json()
                
                prediction_id = prediction.get("id")
                status = prediction.get("status")
                
                logger.debug(f"      📋 Prediction ID: {prediction_id}, Status: {status}")
                
                # Poll for completion (Replicate is async)
                max_attempts = 60  # 60 seconds max
                attempt = 0
                
                while status not in ["succeeded", "failed", "canceled"]:
                    await asyncio.sleep(1)
                    attempt += 1
                    
                    if attempt >= max_attempts:
                        logger.warning(f"      ⚠️ Prediction timed out after {max_attempts}s")
                        return [], "Prediction timed out"
                    
                    # Get prediction status
                    status_response = await client.get(
                        f"{self.REPLICATE_API_URL}/{prediction_id}",
                        headers=headers,
                    )
                    status_response.raise_for_status()
                    prediction = status_response.json()
                    status = prediction.get("status")
                    
                    if attempt % 5 == 0:
                        logger.debug(f"      ⏳ Waiting... ({attempt}s, status: {status})")
                
                if status == "failed":
                    error = prediction.get("error", "Unknown error")
                    logger.warning(f"      ❌ Prediction failed: {error}")
                    return [], error
                
                if status == "canceled":
                    logger.warning(f"      ⚠️ Prediction was canceled")
                    return [], "Prediction canceled"
                
                # Get output
                output = prediction.get("output", {})
                
                if not output:
                    logger.info(f"      ℹ️ No {surface_type} detected")
                    return [], None  # No error, just no detections
                
                # Parse the output - Grounded SAM returns detection masks
                # Output format varies by model version
                detections = self._parse_grounded_sam_output(
                    output=output,
                    surface_type=surface_type,
                    image_bounds=image_bounds,
                    image_width=image_width,
                    image_height=image_height,
                    property_boundary=property_boundary,
                )
                
                return detections, None  # Success
                
        except httpx.HTTPStatusError as e:
            error_msg = f"402 Payment Required - {e.response.text[:200]}" if e.response.status_code == 402 else f"{e.response.status_code} - {e.response.text[:200]}"
            logger.error(f"      ❌ Replicate API error: {error_msg}")
            return [], error_msg
        except Exception as e:
            logger.error(f"      ❌ Grounded SAM error: {e}")
            import traceback
            traceback.print_exc()
            return [], str(e)
    
    def _parse_grounded_sam_output(
        self,
        output: Any,
        surface_type: str,
        image_bounds: Dict[str, float],
        image_width: int,
        image_height: int,
        property_boundary: Optional[Polygon] = None,
    ) -> List[DetectedSurface]:
        """
        Parse Grounded SAM output into DetectedSurface objects.
        
        The output format depends on the model version, but typically includes:
        - Bounding boxes with labels and confidence
        - Segmentation masks (as RLE or polygon points)
        """
        detected_surfaces = []
        
        try:
            # Handle different output formats
            if isinstance(output, str):
                # Output is a URL to the result image - we need to extract masks differently
                # For now, create a detection from the fact that something was found
                logger.debug(f"      Output is image URL: {output[:50]}...")
                # We'll need to parse the actual detection data
                return []
            
            if isinstance(output, dict):
                # Standard detection output format
                detections = output.get("detections", output.get("predictions", []))
                
                if not detections:
                    # Try to get boxes directly
                    boxes = output.get("boxes", [])
                    labels = output.get("labels", [])
                    scores = output.get("scores", [])
                    masks = output.get("masks", [])
                    
                    for i, box in enumerate(boxes):
                        confidence = scores[i] if i < len(scores) else 0.5
                        
                        if confidence < self.MIN_CONFIDENCE:
                            continue
                        
                        # Box format: [x1, y1, x2, y2]
                        polygon = self._box_to_geo_polygon(
                            box, image_bounds, image_width, image_height
                        )
                        
                        if polygon is None or polygon.is_empty:
                            continue
                        
                        # Clip to property boundary
                        if property_boundary and not property_boundary.is_empty:
                            try:
                                polygon = polygon.intersection(property_boundary)
                                if polygon.is_empty:
                                    continue
                            except Exception:
                                pass
                        
                        area_m2 = self._calculate_area_m2(polygon, image_bounds)
                        
                        if area_m2 < self.MIN_AREA_M2:
                            continue
                        
                        area_sqft = area_m2 * 10.764
                        
                        surface = DetectedSurface(
                            surface_type=surface_type,
                            polygon=polygon,
                            confidence=confidence,
                            area_m2=area_m2,
                            area_sqft=area_sqft,
                            color=self.SURFACE_COLORS.get(surface_type, "#888888"),
                            geojson={
                                "type": "Feature",
                                "geometry": mapping(polygon),
                                "properties": {
                                    "surface_type": surface_type,
                                    "confidence": confidence,
                                    "area_sqft": area_sqft,
                                    "color": self.SURFACE_COLORS.get(surface_type, "#888888"),
                                }
                            }
                        )
                        detected_surfaces.append(surface)
                
                # Process standard detections list
                for det in detections:
                    confidence = det.get("confidence", det.get("score", 0.5))
                    
                    if confidence < self.MIN_CONFIDENCE:
                        continue
                    
                    # Get polygon from detection
                    polygon = None
                    
                    # Try mask/segmentation first
                    if "mask" in det or "segmentation" in det:
                        mask_data = det.get("mask") or det.get("segmentation")
                        polygon = self._mask_to_geo_polygon(
                            mask_data, image_bounds, image_width, image_height
                        )
                    
                    # Fall back to bounding box
                    if polygon is None or polygon.is_empty:
                        box = det.get("box") or det.get("bbox") or det.get("bounding_box")
                        if box:
                            polygon = self._box_to_geo_polygon(
                                box, image_bounds, image_width, image_height
                            )
                    
                    if polygon is None or polygon.is_empty:
                        continue
                    
                    # Clip to property boundary
                    if property_boundary and not property_boundary.is_empty:
                        try:
                            polygon = polygon.intersection(property_boundary)
                            if polygon.is_empty:
                                continue
                        except Exception:
                            pass
                    
                    area_m2 = self._calculate_area_m2(polygon, image_bounds)
                    
                    if area_m2 < self.MIN_AREA_M2:
                        continue
                    
                    area_sqft = area_m2 * 10.764
                    
                    surface = DetectedSurface(
                        surface_type=surface_type,
                        polygon=polygon,
                        confidence=confidence,
                        area_m2=area_m2,
                        area_sqft=area_sqft,
                        color=self.SURFACE_COLORS.get(surface_type, "#888888"),
                        geojson={
                            "type": "Feature",
                            "geometry": mapping(polygon),
                            "properties": {
                                "surface_type": surface_type,
                                "confidence": confidence,
                                "area_sqft": area_sqft,
                                "color": self.SURFACE_COLORS.get(surface_type, "#888888"),
                            }
                        }
                    )
                    detected_surfaces.append(surface)
            
            elif isinstance(output, list):
                # List of detections
                for det in output:
                    if isinstance(det, dict):
                        surfaces = self._parse_grounded_sam_output(
                            {"detections": [det]},
                            surface_type, image_bounds, image_width, image_height, property_boundary
                        )
                        detected_surfaces.extend(surfaces)
            
            return detected_surfaces
            
        except Exception as e:
            logger.warning(f"      ⚠️ Failed to parse output: {e}")
            return []
    
    def _box_to_geo_polygon(
        self,
        box: List[float],
        image_bounds: Dict[str, float],
        image_width: int,
        image_height: int,
    ) -> Optional[Polygon]:
        """Convert bounding box [x1, y1, x2, y2] to geographic polygon."""
        try:
            if len(box) < 4:
                return None
            
            x1, y1, x2, y2 = box[:4]
            
            lat_range = image_bounds["max_lat"] - image_bounds["min_lat"]
            lng_range = image_bounds["max_lng"] - image_bounds["min_lng"]
            
            def pixel_to_geo(px, py):
                lng = image_bounds["min_lng"] + (px / image_width) * lng_range
                lat = image_bounds["max_lat"] - (py / image_height) * lat_range
                return (lng, lat)
            
            corners = [
                pixel_to_geo(x1, y1),
                pixel_to_geo(x2, y1),
                pixel_to_geo(x2, y2),
                pixel_to_geo(x1, y2),
                pixel_to_geo(x1, y1),
            ]
            
            polygon = Polygon(corners)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            
            return polygon
            
        except Exception:
            return None
    
    def _mask_to_geo_polygon(
        self,
        mask_data: Any,
        image_bounds: Dict[str, float],
        image_width: int,
        image_height: int,
    ) -> Optional[Polygon]:
        """Convert mask data to geographic polygon."""
        try:
            lat_range = image_bounds["max_lat"] - image_bounds["min_lat"]
            lng_range = image_bounds["max_lng"] - image_bounds["min_lng"]
            
            def pixel_to_geo(px, py):
                lng = image_bounds["min_lng"] + (px / image_width) * lng_range
                lat = image_bounds["max_lat"] - (py / image_height) * lat_range
                return (lng, lat)
            
            # Handle different mask formats
            if isinstance(mask_data, list):
                # List of polygon points [[x1,y1], [x2,y2], ...]
                if len(mask_data) >= 3:
                    if isinstance(mask_data[0], list):
                        geo_points = [pixel_to_geo(p[0], p[1]) for p in mask_data]
                    else:
                        # Flat list [x1, y1, x2, y2, ...]
                        points = [(mask_data[i], mask_data[i+1]) for i in range(0, len(mask_data)-1, 2)]
                        geo_points = [pixel_to_geo(p[0], p[1]) for p in points]
                    
                    if len(geo_points) >= 3:
                        polygon = Polygon(geo_points)
                        if not polygon.is_valid:
                            polygon = polygon.buffer(0)
                        return polygon
            
            elif isinstance(mask_data, dict):
                # RLE or other encoded format
                # Would need to decode - for now skip
                pass
            
            return None
            
        except Exception:
            return None
    
    def _aggregate_results(
        self,
        result: SurfaceDetectionResult,
        image_bounds: Dict[str, float],
    ) -> SurfaceDetectionResult:
        """Aggregate and merge detection results."""
        
        # Merge asphalt polygons
        if result.asphalt_surfaces:
            polygons = [s.polygon for s in result.asphalt_surfaces if s.polygon and not s.polygon.is_empty]
            if polygons:
                result.asphalt_polygon = unary_union(polygons)
                result.total_asphalt_area_m2 = sum(s.area_m2 for s in result.asphalt_surfaces)
                result.total_asphalt_area_sqft = result.total_asphalt_area_m2 * 10.764
        
        # Merge concrete polygons
        if result.concrete_surfaces:
            polygons = [s.polygon for s in result.concrete_surfaces if s.polygon and not s.polygon.is_empty]
            if polygons:
                result.concrete_polygon = unary_union(polygons)
                result.total_concrete_area_m2 = sum(s.area_m2 for s in result.concrete_surfaces)
                result.total_concrete_area_sqft = result.total_concrete_area_m2 * 10.764
        
        # Merge building polygons
        if result.building_surfaces:
            polygons = [s.polygon for s in result.building_surfaces if s.polygon and not s.polygon.is_empty]
            if polygons:
                result.building_polygon = unary_union(polygons)
        
        # Calculate total paved area
        result.total_paved_area_m2 = result.total_asphalt_area_m2 + result.total_concrete_area_m2
        result.total_paved_area_sqft = result.total_paved_area_m2 * 10.764
        
        return result
    
    def _calculate_area_m2(
        self,
        polygon: Polygon,
        bounds: Dict[str, float],
    ) -> float:
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
    
    async def _detect_with_roboflow_fallback(
        self,
        image_bytes: bytes,
        image_bounds: Dict[str, float],
        property_boundary: Optional[Polygon] = None,
    ) -> SurfaceDetectionResult:
        """
        Fallback detection using Roboflow's free satellite-building-segmentation model.
        
        This model detects:
        - "building" class -> buildings
        - "road" class -> paved surfaces (we treat as asphalt since we can't differentiate)
        
        Less accurate than Grounded SAM but free!
        """
        result = SurfaceDetectionResult()
        result.detection_method = "roboflow_fallback"
        
        try:
            # Import the asphalt segmentation service
            from app.core.asphalt_segmentation_service import asphalt_segmentation_service
            
            logger.info("   🔄 Running Roboflow segmentation model...")
            
            # Run segmentation
            segmentation = await asphalt_segmentation_service.segment_property(
                image_bytes=image_bytes,
                image_bounds=image_bounds
            )
            
            # Get image dimensions
            img = Image.open(BytesIO(image_bytes))
            result.image_width, result.image_height = img.size
            
            # Process buildings
            for building in segmentation.buildings:
                if building.polygon and not building.polygon.is_empty:
                    # Clip to property boundary
                    poly = building.polygon
                    if property_boundary and not property_boundary.is_empty:
                        try:
                            poly = poly.intersection(property_boundary)
                            if poly.is_empty:
                                continue
                        except Exception:
                            pass
                    
                    area_m2 = self._calculate_area_m2(poly, image_bounds)
                    
                    if area_m2 < self.MIN_AREA_M2:
                        continue
                    
                    surface = DetectedSurface(
                        surface_type="building",
                        polygon=poly,
                        confidence=building.confidence,
                        area_m2=area_m2,
                        area_sqft=area_m2 * 10.764,
                        color=self.SURFACE_COLORS["building"],
                        geojson={
                            "type": "Feature",
                            "geometry": mapping(poly),
                            "properties": {
                                "surface_type": "building",
                                "confidence": building.confidence,
                                "area_sqft": area_m2 * 10.764,
                                "color": self.SURFACE_COLORS["building"],
                            }
                        }
                    )
                    result.building_surfaces.append(surface)
            
            # Process paved surfaces (roads) - includes parking lots, driveways, all paved areas
            # Roboflow detects "road" class which covers all paved surfaces
            logger.info(f"      Processing {len(segmentation.paved_surfaces)} paved surfaces from Roboflow...")
            
            for paved in segmentation.paved_surfaces:
                if paved.polygon and not paved.polygon.is_empty:
                    # Clip to property boundary
                    poly = paved.polygon
                    if property_boundary and not property_boundary.is_empty:
                        try:
                            poly = poly.intersection(property_boundary)
                            if poly.is_empty:
                                continue
                        except Exception:
                            pass
                    
                    area_m2 = self._calculate_area_m2(poly, image_bounds)
                    
                    if area_m2 < self.MIN_AREA_M2:
                        continue
                    
                    # Store as "asphalt" type (Roboflow's "road" class = paved surfaces)
                    # This includes parking lots, driveways, and any paved areas
                    surface = DetectedSurface(
                        surface_type="asphalt",  # Generic paved surface
                        polygon=poly,
                        confidence=paved.confidence,
                        area_m2=area_m2,
                        area_sqft=area_m2 * 10.764,
                        color=self.SURFACE_COLORS["asphalt"],
                        geojson={
                            "type": "Feature",
                            "geometry": mapping(poly),
                            "properties": {
                                "surface_type": "paved",  # UI will show "Paved Surface"
                                "confidence": paved.confidence,
                                "area_sqft": area_m2 * 10.764,
                                "color": self.SURFACE_COLORS["asphalt"],
                                "label": "Paved Surface",
                            }
                        }
                    )
                    result.asphalt_surfaces.append(surface)
                    logger.info(f"         ✅ Added paved surface: {area_m2:.0f}m² ({area_m2 * 10.764:.0f} sqft)")
            
            # Aggregate results
            result = self._aggregate_results(result, image_bounds)
            result.success = True
            
            logger.info(f"   📊 Roboflow fallback results:")
            logger.info(f"      Paved surfaces: {result.total_asphalt_area_sqft:,.0f} sqft")
            logger.info(f"      Buildings: {len(result.building_surfaces)}")
            
            return result
            
        except Exception as e:
            logger.error(f"   ❌ Roboflow fallback failed: {e}")
            import traceback
            traceback.print_exc()
            result.error_message = f"Roboflow fallback failed: {e}"
            return result


# Singleton instance
grounded_sam_service = GroundedSAMService()
