"""
GroundedSAMService - Surface Detection Service

Primary: Replicate's hosted Grounded SAM API (high accuracy, paid)
Fallback: Roboflow's satellite-building-segmentation model (free)

Detects:
- Asphalt (dark pavement - parking lots, driveways)
- Concrete (light pavement - sidewalks, some parking areas)  
- Buildings (to exclude from analysis)

IMPORTANT: Before running CV, we MASK the satellite image to the property
boundary polygon. This ensures CV only detects surfaces WITHIN the property,
not from neighboring properties or public roads outside the boundary.

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
from app.core.polygon_masking_service import polygon_masking_service, MaskedImageResult

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
    
    # Merged GeoJSON for each type (for API/frontend)
    asphalt_geojson: Optional[Dict] = None
    concrete_geojson: Optional[Dict] = None
    building_geojson: Optional[Dict] = None
    
    # Combined surfaces list (for backward compat)
    surfaces: List[Dict] = field(default_factory=list)
    
    # Total areas
    total_asphalt_area_m2: float = 0
    total_asphalt_area_sqft: float = 0
    total_concrete_area_m2: float = 0
    total_concrete_area_sqft: float = 0
    total_paved_area_m2: float = 0  # asphalt + concrete
    total_paved_area_sqft: float = 0
    building_area_m2: float = 0
    public_road_area_m2: float = 0
    
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
    # Using period (.) as separator - Grounding DINO convention for multiple classes
    SURFACE_PROMPTS = {
        # Combined paved surfaces prompt - single API call for all pavement
        "paved": (
            "parking lot . "
            "asphalt pavement . "
            "paved driveway . "
            "concrete pavement . "
            "paved road . "
            "blacktop . "
            "tarmac surface"
        ),
        # Separate prompts if needed for differentiation
        "asphalt": "dark asphalt parking lot . black pavement . dark paved driveway . blacktop",
        "concrete": "light gray concrete . white concrete sidewalk . cement pavement . light paved surface",
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
        
        APPROACH:
        1. MASK the image to property boundary (if provided)
        2. Run CV on the masked image - model only sees property area
        3. Map detections back to geo-coordinates
        
        This ensures we don't detect neighbor's parking lots or public roads.
        
        Args:
            image_bytes: Satellite image as bytes
            image_bounds: Geographic bounds {min_lat, max_lat, min_lng, max_lng}
            property_boundary: Property boundary to mask to (REQUIRED for accuracy)
            detect_asphalt: Whether to detect asphalt surfaces
            detect_concrete: Whether to detect concrete surfaces
            detect_buildings: Whether to detect buildings
            
        Returns:
            SurfaceDetectionResult with all detected surfaces
        """
        # ============ STEP 1: Apply polygon mask if boundary provided ============
        masked_result: Optional[MaskedImageResult] = None
        effective_image_bytes = image_bytes
        effective_bounds = image_bounds
        
        if property_boundary is not None and not property_boundary.is_empty:
            logger.info("   🎭 Applying polygon mask to focus on property...")
            
            masked_result = polygon_masking_service.mask_to_polygon(
                image_bytes=image_bytes,
                polygon=property_boundary,
                image_bounds=image_bounds,
            )
            
            if masked_result.success:
                effective_image_bytes = masked_result.image_bytes
                # Update bounds if image was cropped
                if masked_result.was_cropped:
                    effective_bounds = {
                        "min_lat": masked_result.geo_bounds.min_lat,
                        "max_lat": masked_result.geo_bounds.max_lat,
                        "min_lng": masked_result.geo_bounds.min_lng,
                        "max_lng": masked_result.geo_bounds.max_lng,
                    }
                    logger.info(f"      ✅ Image masked and cropped: {masked_result.masked_width}x{masked_result.masked_height}")
                else:
                    logger.info(f"      ✅ Image masked (no crop needed)")
            else:
                logger.warning(f"      ⚠️ Masking failed: {masked_result.error_message}")
                logger.warning(f"      Continuing with original image...")
        else:
            logger.info("   ℹ️ No property boundary - using full image (less accurate)")
        
        # ============ STEP 2: Run CV detection on (masked) image ============
        
        # Try Replicate Grounded SAM first (primary - more accurate)
        if self.is_configured and not self._replicate_failed:
            logger.info("   🎯 Using Replicate Grounded SAM (primary)...")
            
            result = await self._detect_with_replicate(
                effective_image_bytes, 
                effective_bounds, 
                property_boundary=None,  # Already masked - no post-clipping needed
                detect_asphalt=detect_asphalt, 
                detect_concrete=detect_concrete, 
                detect_buildings=detect_buildings
            )
            
            # Check if Replicate succeeded AND found surfaces
            if result.success and result.total_paved_area_m2 > 0:
                logger.info(f"   ✅ Replicate SAM detected {result.total_paved_area_sqft:,.0f} sqft of paved surfaces")
                return result
            
            # Check if billing/payment/rate limit issue
            if result.error_message:
                error_lower = result.error_message.lower()
                if "402" in result.error_message or "429" in result.error_message or "payment" in error_lower or "credit" in error_lower or "throttle" in error_lower:
                    logger.warning("   ⚠️ Replicate billing/rate limit issue - switching to Roboflow fallback")
                    self._replicate_failed = True
                else:
                    logger.warning(f"   ⚠️ Replicate error: {result.error_message}")
            
            # Replicate found nothing - fallback to Roboflow
            if result.total_paved_area_m2 == 0:
                logger.info("   ℹ️ Replicate found no surfaces - trying Roboflow fallback...")
        
        # Fallback to Roboflow (free but less accurate)
        logger.info("   🔄 Using Roboflow segmentation model (fallback)...")
        return await self._detect_with_roboflow_fallback(
            effective_image_bytes, 
            effective_bounds, 
            property_boundary=None  # Already masked
        )
    
    async def _detect_with_replicate(
        self,
        image_bytes: bytes,
        image_bounds: Dict[str, float],
        property_boundary: Optional[Polygon] = None,
        detect_asphalt: bool = True,
        detect_concrete: bool = True,
        detect_buildings: bool = False,  # Default False - we typically want to exclude buildings
    ) -> SurfaceDetectionResult:
        """
        Detect paved surfaces using Replicate's Grounded SAM.
        
        OPTIMIZED: Uses single combined prompt for all paved surfaces to minimize API calls.
        Cost: ~$0.002 per image instead of $0.006 for 3 separate calls.
        """
        result = SurfaceDetectionResult()
        result.detection_method = "grounded_sam_replicate"
        
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
            
            logger.info(f"   🎯 Running Grounded SAM via Replicate...")
            logger.info(f"      📐 Image: {result.image_width}x{result.image_height}")
            
            # OPTIMIZED: Single API call for all paved surfaces
            # This is more efficient than separate asphalt/concrete calls
            if detect_asphalt or detect_concrete:
                logger.info(f"      🔍 Detecting paved surfaces...")
                
                paved_surfaces, error = await self._run_grounded_sam(
                    image_data_uri=image_data_uri,
                    prompt=self.SURFACE_PROMPTS["paved"],  # Combined prompt
                    surface_type="asphalt",  # Categorize as asphalt for now
                    image_bounds=image_bounds,
                    image_width=result.image_width,
                    image_height=result.image_height,
                    property_boundary=property_boundary,
                )
                
                # Check for errors
                if error:
                    error_lower = error.lower()
                    # Critical errors - return immediately to trigger fallback
                    if any(x in error for x in ["402", "429"]) or any(x in error_lower for x in ["payment", "credit", "throttle", "timeout"]):
                        logger.warning(f"      ⚠️ Replicate critical error: {error}")
                        result.error_message = error
                        result.success = False
                        return result
                    else:
                        # Non-critical error - log and continue (might still work with building detection)
                        logger.warning(f"      ⚠️ Detection error: {error}")
                        result.error_message = error
                
                if paved_surfaces:
                    result.asphalt_surfaces = paved_surfaces
                    logger.info(f"      ✅ Found {len(paved_surfaces)} paved regions")
                else:
                    logger.info(f"      ℹ️ No paved surfaces detected")
            
            # Optional: Detect buildings separately (typically skipped)
            if detect_buildings:
                logger.info(f"      🔍 Detecting buildings...")
                
                building_surfaces, error = await self._run_grounded_sam(
                    image_data_uri=image_data_uri,
                    prompt=self.SURFACE_PROMPTS["building"],
                    surface_type="building",
                    image_bounds=image_bounds,
                    image_width=result.image_width,
                    image_height=result.image_height,
                    property_boundary=property_boundary,
                )
                
                if building_surfaces:
                    result.building_surfaces = building_surfaces
                    logger.info(f"      ✅ Found {len(building_surfaces)} buildings")
            
            # Aggregate results
            result = self._aggregate_results(result, image_bounds)
            result.success = True
            
            logger.info(f"   📊 Paved surfaces detected: {result.total_paved_area_sqft:,.0f} sqft")
            
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
        """
        Convert mask data to geographic polygon.
        
        Handles multiple formats:
        - List of polygon points: [[x1,y1], [x2,y2], ...]
        - Flat list: [x1, y1, x2, y2, ...]
        - RLE encoded mask: {"counts": [...], "size": [h, w]}
        - Binary mask image: numpy array or base64 encoded
        """
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
                # RLE encoded format: {"counts": [...], "size": [h, w]}
                if "counts" in mask_data and "size" in mask_data:
                    polygon = self._decode_rle_to_polygon(
                        mask_data, image_bounds, image_width, image_height
                    )
                    if polygon:
                        return polygon
            
            elif isinstance(mask_data, str):
                # Base64 encoded binary mask image
                polygon = self._decode_base64_mask_to_polygon(
                    mask_data, image_bounds, image_width, image_height
                )
                if polygon:
                    return polygon
            
            return None
            
        except Exception as e:
            logger.debug(f"      ⚠️ Failed to parse mask: {e}")
            return None
    
    def _decode_rle_to_polygon(
        self,
        rle_data: Dict,
        image_bounds: Dict[str, float],
        image_width: int,
        image_height: int,
    ) -> Optional[Polygon]:
        """Decode RLE mask to polygon using OpenCV contours."""
        try:
            import cv2
            import numpy as np
            
            counts = rle_data.get("counts", [])
            size = rle_data.get("size", [image_height, image_width])
            h, w = size[0], size[1]
            
            # Decode RLE to binary mask
            if isinstance(counts, str):
                # Compressed RLE (COCO format) - decode using pycocotools if available
                try:
                    from pycocotools import mask as mask_utils
                    binary_mask = mask_utils.decode(rle_data)
                except ImportError:
                    # Manual decompression for simple RLE
                    binary_mask = self._simple_rle_decode(counts, h, w)
            else:
                # Uncompressed RLE (list of counts)
                binary_mask = self._simple_rle_decode(counts, h, w)
            
            if binary_mask is None:
                return None
            
            # Find contours in the binary mask
            contours, _ = cv2.findContours(
                binary_mask.astype(np.uint8), 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            if not contours:
                return None
            
            # Get the largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Simplify contour
            epsilon = 0.005 * cv2.arcLength(largest_contour, True)
            simplified = cv2.approxPolyDP(largest_contour, epsilon, True)
            
            if len(simplified) < 3:
                return None
            
            # Convert to geo coordinates
            lat_range = image_bounds["max_lat"] - image_bounds["min_lat"]
            lng_range = image_bounds["max_lng"] - image_bounds["min_lng"]
            
            geo_points = []
            for point in simplified:
                px, py = point[0]
                lng = image_bounds["min_lng"] + (px / w) * lng_range
                lat = image_bounds["max_lat"] - (py / h) * lat_range
                geo_points.append((lng, lat))
            
            polygon = Polygon(geo_points)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            
            return polygon
            
        except Exception as e:
            logger.debug(f"      ⚠️ RLE decode failed: {e}")
            return None
    
    def _simple_rle_decode(self, counts: Any, height: int, width: int) -> Optional[Any]:
        """Decode simple RLE format to binary mask."""
        try:
            import numpy as np
            
            if isinstance(counts, str):
                # Can't decode compressed string without pycocotools
                return None
            
            # Uncompressed RLE: alternating counts of 0s and 1s
            mask = np.zeros(height * width, dtype=np.uint8)
            position = 0
            value = 0
            
            for count in counts:
                mask[position:position + count] = value
                position += count
                value = 1 - value  # Alternate between 0 and 1
            
            return mask.reshape((height, width), order='F')  # Column-major for COCO format
            
        except Exception:
            return None
    
    def _decode_base64_mask_to_polygon(
        self,
        base64_mask: str,
        image_bounds: Dict[str, float],
        image_width: int,
        image_height: int,
    ) -> Optional[Polygon]:
        """Decode base64 encoded mask image to polygon."""
        try:
            import cv2
            import numpy as np
            
            # Decode base64
            if base64_mask.startswith('data:'):
                base64_mask = base64_mask.split(',')[1]
            
            mask_bytes = base64.b64decode(base64_mask)
            mask_array = np.frombuffer(mask_bytes, dtype=np.uint8)
            mask_image = cv2.imdecode(mask_array, cv2.IMREAD_GRAYSCALE)
            
            if mask_image is None:
                return None
            
            # Threshold to binary
            _, binary_mask = cv2.threshold(mask_image, 127, 255, cv2.THRESH_BINARY)
            
            # Find contours
            contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                return None
            
            # Get the largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Simplify
            epsilon = 0.005 * cv2.arcLength(largest_contour, True)
            simplified = cv2.approxPolyDP(largest_contour, epsilon, True)
            
            if len(simplified) < 3:
                return None
            
            # Convert to geo coordinates
            h, w = mask_image.shape
            lat_range = image_bounds["max_lat"] - image_bounds["min_lat"]
            lng_range = image_bounds["max_lng"] - image_bounds["min_lng"]
            
            geo_points = []
            for point in simplified:
                px, py = point[0]
                lng = image_bounds["min_lng"] + (px / w) * lng_range
                lat = image_bounds["max_lat"] - (py / h) * lat_range
                geo_points.append((lng, lat))
            
            polygon = Polygon(geo_points)
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            
            return polygon
            
        except Exception as e:
            logger.debug(f"      ⚠️ Base64 mask decode failed: {e}")
            return None
    
    def _aggregate_results(
        self,
        result: SurfaceDetectionResult,
        image_bounds: Dict[str, float],
    ) -> SurfaceDetectionResult:
        """Aggregate and merge detection results."""
        
        # Merge asphalt polygons and create GeoJSON
        if result.asphalt_surfaces:
            polygons = [s.polygon for s in result.asphalt_surfaces if s.polygon and not s.polygon.is_empty]
            if polygons:
                result.asphalt_polygon = unary_union(polygons)
                result.total_asphalt_area_m2 = sum(s.area_m2 for s in result.asphalt_surfaces)
                result.total_asphalt_area_sqft = result.total_asphalt_area_m2 * 10.764
                # Create merged GeoJSON
                result.asphalt_geojson = {
                    "type": "Feature",
                    "geometry": mapping(result.asphalt_polygon),
                    "properties": {
                        "surface_type": "asphalt",
                        "area_m2": result.total_asphalt_area_m2,
                        "area_sqft": result.total_asphalt_area_sqft,
                        "color": self.SURFACE_COLORS.get("asphalt", "#374151"),
                        "label": "Paved Surface",
                    }
                }
                # Add to surfaces list
                result.surfaces.append({
                    "surface_type": "asphalt",
                    "area_m2": result.total_asphalt_area_m2,
                    "area_sqft": result.total_asphalt_area_sqft,
                    "geojson": result.asphalt_geojson,
                })
        
        # Merge concrete polygons and create GeoJSON
        if result.concrete_surfaces:
            polygons = [s.polygon for s in result.concrete_surfaces if s.polygon and not s.polygon.is_empty]
            if polygons:
                result.concrete_polygon = unary_union(polygons)
                result.total_concrete_area_m2 = sum(s.area_m2 for s in result.concrete_surfaces)
                result.total_concrete_area_sqft = result.total_concrete_area_m2 * 10.764
                # Create merged GeoJSON
                result.concrete_geojson = {
                    "type": "Feature",
                    "geometry": mapping(result.concrete_polygon),
                    "properties": {
                        "surface_type": "concrete",
                        "area_m2": result.total_concrete_area_m2,
                        "area_sqft": result.total_concrete_area_sqft,
                        "color": self.SURFACE_COLORS.get("concrete", "#9CA3AF"),
                        "label": "Concrete",
                    }
                }
                # Add to surfaces list
                result.surfaces.append({
                    "surface_type": "concrete",
                    "area_m2": result.total_concrete_area_m2,
                    "area_sqft": result.total_concrete_area_sqft,
                    "geojson": result.concrete_geojson,
                })
        
        # Merge building polygons and create GeoJSON
        if result.building_surfaces:
            polygons = [s.polygon for s in result.building_surfaces if s.polygon and not s.polygon.is_empty]
            if polygons:
                result.building_polygon = unary_union(polygons)
                result.building_area_m2 = sum(s.area_m2 for s in result.building_surfaces)
                # Create merged GeoJSON
                result.building_geojson = {
                    "type": "Feature",
                    "geometry": mapping(result.building_polygon),
                    "properties": {
                        "surface_type": "building",
                        "area_m2": result.building_area_m2,
                        "color": self.SURFACE_COLORS.get("building", "#DC2626"),
                        "label": "Building",
                    }
                }
                
                # SUBTRACT buildings from paved surfaces (fixes roof detection issue)
                if result.asphalt_polygon and not result.asphalt_polygon.is_empty:
                    try:
                        original_area = result.total_asphalt_area_m2
                        result.asphalt_polygon = result.asphalt_polygon.difference(result.building_polygon)
                        if not result.asphalt_polygon.is_empty:
                            result.total_asphalt_area_m2 = self._calculate_area_m2(result.asphalt_polygon, image_bounds)
                            result.total_asphalt_area_sqft = result.total_asphalt_area_m2 * 10.764
                            # Update GeoJSON
                            result.asphalt_geojson = {
                                "type": "Feature",
                                "geometry": mapping(result.asphalt_polygon),
                                "properties": {
                                    "surface_type": "asphalt",
                                    "area_m2": result.total_asphalt_area_m2,
                                    "area_sqft": result.total_asphalt_area_sqft,
                                    "color": self.SURFACE_COLORS.get("asphalt", "#374151"),
                                    "label": "Paved Surface",
                                }
                            }
                            # Update surfaces list
                            if result.surfaces:
                                for s in result.surfaces:
                                    if s.get("surface_type") == "asphalt":
                                        s["area_m2"] = result.total_asphalt_area_m2
                                        s["area_sqft"] = result.total_asphalt_area_sqft
                                        s["geojson"] = result.asphalt_geojson
                            
                            logger.info(f"      ✂️ Subtracted buildings: {original_area:,.0f}m² → {result.total_asphalt_area_m2:,.0f}m²")
                        else:
                            result.total_asphalt_area_m2 = 0
                            result.total_asphalt_area_sqft = 0
                    except Exception as e:
                        logger.debug(f"      ⚠️ Failed to subtract buildings: {e}")
        
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
