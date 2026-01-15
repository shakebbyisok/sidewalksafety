"""
Property Imagery Pipeline - Clean and Simple

This is the simplified pipeline that:
1. Takes a property location (lat/lng)
2. Gets property boundary from Regrid
3. Fetches high-res satellite imagery of the polygon
4. Returns the image ready for analysis

No SAM, no Modal, no complex segmentation - just clean imagery.
"""

import logging
import os
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from shapely.geometry import Polygon, MultiPolygon, Point
from PIL import Image

from app.core.regrid_service import regrid_service, PropertyParcel
from app.core.polygon_imagery_service import get_polygon_imagery_service

logger = logging.getLogger(__name__)


class PropertyImageryResult:
    """Result of property imagery pipeline."""
    
    def __init__(
        self,
        success: bool,
        image: Optional[Image.Image] = None,
        image_base64: Optional[str] = None,
        polygon: Optional[Polygon] = None,
        parcel: Optional[PropertyParcel] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        self.success = success
        self.image = image
        self.image_base64 = image_base64
        self.polygon = polygon
        self.parcel = parcel
        self.metadata = metadata or {}
        self.error_message = error_message
    
    @property
    def area_sqm(self) -> float:
        """Property area in square meters."""
        return self.metadata.get("polygon_area_sqm", 0)
    
    @property
    def area_sqft(self) -> float:
        """Property area in square feet."""
        return self.area_sqm * 10.764
    
    @property
    def image_size(self) -> Tuple[int, int]:
        """Image dimensions (width, height)."""
        if self.image:
            return self.image.size
        return (0, 0)


class PropertyImageryPipeline:
    """
    Clean pipeline for getting property satellite imagery.
    
    Usage:
        pipeline = PropertyImageryPipeline()
        result = await pipeline.get_property_image(lat, lng, address)
        if result.success:
            result.image.save("property.jpg")
    """
    
    # Default settings
    DEFAULT_ZOOM = 20  # High detail
    DEFAULT_BOUNDARY_COLOR = (255, 0, 0)  # Red
    DEFAULT_BOUNDARY_WIDTH = 4
    DEFAULT_PADDING_PERCENT = 15.0
    
    # Debug settings
    SAVE_DEBUG_IMAGES = True
    DEBUG_IMAGE_DIR = "debug_images/pipeline"
    
    def __init__(self):
        self.imagery_service = get_polygon_imagery_service()
    
    async def get_property_image(
        self,
        lat: float,
        lng: float,
        address: Optional[str] = None,
        zoom: int = None,
        draw_boundary: bool = True,
        save_debug: bool = None,
    ) -> PropertyImageryResult:
        """
        Get high-resolution satellite image for a property.
        
        Args:
            lat: Latitude of the property
            lng: Longitude of the property
            address: Optional address for better Regrid lookup
            zoom: Tile zoom level (default: 20)
            draw_boundary: Whether to draw polygon boundary on image
            save_debug: Whether to save debug images
        
        Returns:
            PropertyImageryResult with image and metadata
        """
        zoom = zoom or self.DEFAULT_ZOOM
        save_debug = save_debug if save_debug is not None else self.SAVE_DEBUG_IMAGES
        
        logger.info(f"\n{'='*60}")
        logger.info(f"PROPERTY IMAGERY PIPELINE")
        logger.info(f"Location: {lat}, {lng}")
        if address:
            logger.info(f"Address: {address}")
        logger.info(f"{'='*60}")
        
        # ============ Step 1: Get Property Polygon from Regrid ============
        logger.info(f"\n[1] Fetching property boundary from Regrid...")
        
        polygon = None
        parcel = None
        
        try:
            parcel = await regrid_service.get_validated_parcel(lat, lng, address)
            
            if parcel and parcel.polygon:
                polygon = parcel.polygon
                logger.info(f"    Parcel ID: {parcel.parcel_id}")
                logger.info(f"    Address: {parcel.address}")
                logger.info(f"    Area: {parcel.area_m2:.0f} m² ({parcel.area_acres or 0:.2f} acres)")
                logger.info(f"    Land Use: {parcel.land_use}")
            else:
                logger.warning(f"    No parcel found - using estimated boundary")
        except Exception as e:
            logger.warning(f"    Regrid error: {e} - using estimated boundary")
        
        # If no Regrid polygon, create an estimated one
        if polygon is None:
            polygon = self._create_estimated_polygon(lat, lng)
            logger.info(f"    Created estimated polygon (~100m x 100m)")
        
        # ============ Step 2: Fetch Satellite Imagery ============
        logger.info(f"\n[2] Fetching satellite imagery...")
        
        try:
            img, metadata = self.imagery_service.get_polygon_image(
                polygon=polygon,
                zoom=zoom,
                draw_boundary=draw_boundary,
                boundary_color=self.DEFAULT_BOUNDARY_COLOR,
                boundary_width=self.DEFAULT_BOUNDARY_WIDTH,
                padding_percent=self.DEFAULT_PADDING_PERCENT,
                source="google",
            )
            
            logger.info(f"    Image size: {img.size[0]}x{img.size[1]} pixels")
            logger.info(f"    Property area: {metadata.get('polygon_area_sqm', 0):.0f} m²")
            logger.info(f"    Source: Google Satellite Tiles")
            
        except Exception as e:
            logger.error(f"    Imagery fetch failed: {e}")
            return PropertyImageryResult(
                success=False,
                error_message=f"Failed to fetch satellite imagery: {e}"
            )
        
        # ============ Step 3: Save Debug Image ============
        if save_debug:
            self._save_debug_image(img, lat, lng, parcel)
        
        # ============ Step 4: Get Base64 for API usage ============
        base64_str, _ = self.imagery_service.get_polygon_image_base64(
            polygon=polygon,
            zoom=zoom,
            draw_boundary=draw_boundary,
            boundary_color=self.DEFAULT_BOUNDARY_COLOR,
            boundary_width=self.DEFAULT_BOUNDARY_WIDTH,
            padding_percent=self.DEFAULT_PADDING_PERCENT,
            source="google",
        )
        
        logger.info(f"\n[COMPLETE] Property imagery ready")
        logger.info(f"{'='*60}\n")
        
        return PropertyImageryResult(
            success=True,
            image=img,
            image_base64=base64_str,
            polygon=polygon,
            parcel=parcel,
            metadata=metadata,
        )
    
    def _create_estimated_polygon(self, lat: float, lng: float, size_m: float = 100) -> Polygon:
        """Create an estimated polygon around coordinates."""
        # 1 degree lat ≈ 111km
        # 1 degree lng ≈ 85km at mid-latitudes
        delta_lat = (size_m / 2) / 111000
        delta_lng = (size_m / 2) / 85000
        
        return Polygon([
            (lng - delta_lng, lat - delta_lat),
            (lng - delta_lng, lat + delta_lat),
            (lng + delta_lng, lat + delta_lat),
            (lng + delta_lng, lat - delta_lat),
            (lng - delta_lng, lat - delta_lat),
        ])
    
    def _save_debug_image(
        self, 
        img: Image.Image, 
        lat: float, 
        lng: float, 
        parcel: Optional[PropertyParcel]
    ) -> str:
        """Save debug image and return path."""
        os.makedirs(self.DEBUG_IMAGE_DIR, exist_ok=True)
        
        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if parcel and parcel.address:
            safe_addr = parcel.address[:30].replace(" ", "_").replace(",", "")
            filename = f"{timestamp}_{safe_addr}.jpg"
        else:
            filename = f"{timestamp}_{lat:.4f}_{lng:.4f}.jpg"
        
        filepath = os.path.join(self.DEBUG_IMAGE_DIR, filename)
        img.save(filepath, quality=95)
        
        logger.info(f"\n[DEBUG] Image saved: {filepath}")
        
        return filepath


# Singleton instance
property_imagery_pipeline = PropertyImageryPipeline()

