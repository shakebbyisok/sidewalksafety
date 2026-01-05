"""
Polygon Masking Service

Masks satellite imagery to property boundary before sending to CV.

PURPOSE:
- CV models detect surfaces OUTSIDE the property boundary
- Even with post-clipping, detections from neighbors affect accuracy
- By masking the image BEFORE CV, we focus the model on the property only

APPROACH:
1. Convert Regrid polygon (lat/lng) to pixel coordinates
2. Create a feathered mask (soft edges to avoid artifacts)
3. Apply mask: property pixels visible, outside pixels = neutral gray
4. Tight crop to minimize gray area
5. Return masked image ready for CV

The neutral gray (#808080) is "boring" to CV models - no features to detect.
Soft edge feathering prevents the mask boundary from being detected as a road edge.
"""

import logging
import math
import numpy as np
from io import BytesIO
from PIL import Image, ImageDraw, ImageFilter
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from shapely.geometry import Polygon, MultiPolygon

logger = logging.getLogger(__name__)


@dataclass
class ImageGeoBounds:
    """Geographic bounds of an image with coordinate transformation methods."""
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float
    image_width: int
    image_height: int
    
    def geo_to_pixel(self, lat: float, lng: float) -> Tuple[int, int]:
        """Convert lat/lng to pixel coordinates."""
        # X: longitude maps to horizontal pixels (left to right)
        x = (lng - self.min_lng) / (self.max_lng - self.min_lng) * self.image_width
        # Y: latitude maps to vertical pixels (top to bottom, inverted)
        y = (self.max_lat - lat) / (self.max_lat - self.min_lat) * self.image_height
        return (int(round(x)), int(round(y)))
    
    def pixel_to_geo(self, x: int, y: int) -> Tuple[float, float]:
        """Convert pixel coordinates to lat/lng."""
        lng = self.min_lng + (x / self.image_width) * (self.max_lng - self.min_lng)
        lat = self.max_lat - (y / self.image_height) * (self.max_lat - self.min_lat)
        return (lat, lng)
    
    def polygon_to_pixels(self, polygon: Polygon) -> List[Tuple[int, int]]:
        """Convert Shapely polygon exterior to pixel coordinates."""
        if polygon is None or polygon.is_empty:
            return []
        
        pixel_coords = []
        for lng, lat in polygon.exterior.coords:
            pixel_coords.append(self.geo_to_pixel(lat, lng))
        
        return pixel_coords
    
    def crop_bounds(self, min_x: int, min_y: int, max_x: int, max_y: int) -> 'ImageGeoBounds':
        """Create new bounds for a cropped region."""
        # Calculate geo coordinates for the crop region
        new_min_lat, _ = self.pixel_to_geo(0, max_y)
        new_max_lat, _ = self.pixel_to_geo(0, min_y)
        _, new_min_lng = self.pixel_to_geo(min_x, 0)
        _, new_max_lng = self.pixel_to_geo(max_x, 0)
        
        return ImageGeoBounds(
            min_lat=new_min_lat,
            max_lat=new_max_lat,
            min_lng=new_min_lng,
            max_lng=new_max_lng,
            image_width=max_x - min_x,
            image_height=max_y - min_y,
        )


@dataclass
class MaskedImageResult:
    """Result from the polygon masking pipeline."""
    # Masked image
    image_bytes: bytes
    image_array: np.ndarray
    
    # Dimensions
    original_width: int
    original_height: int
    masked_width: int
    masked_height: int
    
    # Crop info (for coordinate mapping)
    crop_offset_x: int
    crop_offset_y: int
    was_cropped: bool
    
    # Updated geo bounds (after crop)
    geo_bounds: ImageGeoBounds
    original_geo_bounds: ImageGeoBounds
    
    # Polygon in pixel coordinates (for debugging)
    polygon_pixels: List[Tuple[int, int]]
    
    # Metadata
    success: bool
    error_message: Optional[str] = None


class PolygonMaskingService:
    """
    Masks satellite imagery to property polygon boundary.
    
    Usage:
        result = await polygon_masking_service.mask_to_polygon(
            image_bytes=satellite_image,
            polygon=regrid_polygon,
            image_bounds={"min_lat": ..., "max_lat": ..., "min_lng": ..., "max_lng": ...}
        )
        # result.image_bytes is ready for CV
    """
    
    # Neutral gray - "boring" to CV models
    BACKGROUND_COLOR = (128, 128, 128)
    
    # Feather radius for soft edges (pixels)
    FEATHER_RADIUS = 5
    
    # Padding around polygon for tight crop (pixels)
    CROP_PADDING = 20
    
    # Minimum image dimension after crop
    MIN_DIMENSION = 100
    
    def mask_to_polygon(
        self,
        image_bytes: bytes,
        polygon: Polygon,
        image_bounds: Dict[str, float],
        background_color: Tuple[int, int, int] = None,
        feather_radius: int = None,
        crop_padding: int = None,
        tight_crop: bool = True,
    ) -> MaskedImageResult:
        """
        Mask satellite image to property polygon boundary.
        
        Args:
            image_bytes: Satellite image as bytes (JPEG/PNG)
            polygon: Shapely Polygon in lat/lng coordinates (from Regrid)
            image_bounds: Dict with min_lat, max_lat, min_lng, max_lng
            background_color: RGB tuple for masked area (default: neutral gray)
            feather_radius: Pixels for soft edge (default: 5)
            crop_padding: Pixels of padding around polygon (default: 20)
            tight_crop: Whether to crop to polygon bounding box
            
        Returns:
            MaskedImageResult with masked image ready for CV
        """
        background_color = background_color or self.BACKGROUND_COLOR
        feather_radius = feather_radius if feather_radius is not None else self.FEATHER_RADIUS
        crop_padding = crop_padding if crop_padding is not None else self.CROP_PADDING
        
        try:
            # ============ STEP 1: Load and validate image ============
            image = Image.open(BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            original_width, original_height = image.size
            
            logger.info(f"   🎭 Polygon masking: {original_width}x{original_height} image")
            
            # ============ STEP 2: Create geo-bounds helper ============
            bounds = ImageGeoBounds(
                min_lat=image_bounds["min_lat"],
                max_lat=image_bounds["max_lat"],
                min_lng=image_bounds["min_lng"],
                max_lng=image_bounds["max_lng"],
                image_width=original_width,
                image_height=original_height,
            )
            
            # ============ STEP 3: Handle polygon type ============
            if isinstance(polygon, MultiPolygon):
                # Use the largest polygon
                polygon = max(polygon.geoms, key=lambda p: p.area)
                logger.info(f"      Using largest polygon from MultiPolygon")
            
            if polygon is None or polygon.is_empty:
                logger.warning(f"      ⚠️ Empty polygon - returning original image")
                return MaskedImageResult(
                    image_bytes=image_bytes,
                    image_array=np.array(image),
                    original_width=original_width,
                    original_height=original_height,
                    masked_width=original_width,
                    masked_height=original_height,
                    crop_offset_x=0,
                    crop_offset_y=0,
                    was_cropped=False,
                    geo_bounds=bounds,
                    original_geo_bounds=bounds,
                    polygon_pixels=[],
                    success=True,
                )
            
            # ============ STEP 4: Convert polygon to pixel coordinates ============
            polygon_pixels = bounds.polygon_to_pixels(polygon)
            
            if len(polygon_pixels) < 3:
                logger.warning(f"      ⚠️ Invalid polygon (< 3 points) - returning original")
                return MaskedImageResult(
                    image_bytes=image_bytes,
                    image_array=np.array(image),
                    original_width=original_width,
                    original_height=original_height,
                    masked_width=original_width,
                    masked_height=original_height,
                    crop_offset_x=0,
                    crop_offset_y=0,
                    was_cropped=False,
                    geo_bounds=bounds,
                    original_geo_bounds=bounds,
                    polygon_pixels=polygon_pixels,
                    success=True,
                )
            
            logger.info(f"      📐 Polygon: {len(polygon_pixels)} vertices")
            
            # ============ STEP 5: Create feathered mask ============
            mask = self._create_feathered_mask(
                polygon_pixels=polygon_pixels,
                image_size=(original_width, original_height),
                feather_radius=feather_radius,
            )
            
            # ============ STEP 6: Apply mask to image ============
            masked_image = self._apply_mask(
                image=image,
                mask=mask,
                background_color=background_color,
            )
            
            # ============ STEP 7: Tight crop (optional) ============
            crop_offset_x = 0
            crop_offset_y = 0
            was_cropped = False
            final_bounds = bounds
            
            if tight_crop:
                cropped_image, crop_offset_x, crop_offset_y, adjusted_pixels = self._tight_crop(
                    image=masked_image,
                    polygon_pixels=polygon_pixels,
                    padding=crop_padding,
                )
                
                if cropped_image is not None:
                    masked_image = cropped_image
                    polygon_pixels = adjusted_pixels
                    was_cropped = True
                    
                    # Update bounds for cropped region
                    final_bounds = bounds.crop_bounds(
                        min_x=crop_offset_x,
                        min_y=crop_offset_y,
                        max_x=crop_offset_x + masked_image.width,
                        max_y=crop_offset_y + masked_image.height,
                    )
                    
                    logger.info(f"      ✂️ Cropped: {masked_image.width}x{masked_image.height}")
            
            # ============ STEP 8: Convert to bytes ============
            output_buffer = BytesIO()
            masked_image.save(output_buffer, format='JPEG', quality=95)
            masked_bytes = output_buffer.getvalue()
            
            logger.info(f"      ✅ Masked image ready: {len(masked_bytes)/1024:.1f}KB")
            
            return MaskedImageResult(
                image_bytes=masked_bytes,
                image_array=np.array(masked_image),
                original_width=original_width,
                original_height=original_height,
                masked_width=masked_image.width,
                masked_height=masked_image.height,
                crop_offset_x=crop_offset_x,
                crop_offset_y=crop_offset_y,
                was_cropped=was_cropped,
                geo_bounds=final_bounds,
                original_geo_bounds=bounds,
                polygon_pixels=polygon_pixels,
                success=True,
            )
            
        except Exception as e:
            logger.error(f"      ❌ Polygon masking failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Return original image on failure
            try:
                image = Image.open(BytesIO(image_bytes))
                return MaskedImageResult(
                    image_bytes=image_bytes,
                    image_array=np.array(image),
                    original_width=image.width,
                    original_height=image.height,
                    masked_width=image.width,
                    masked_height=image.height,
                    crop_offset_x=0,
                    crop_offset_y=0,
                    was_cropped=False,
                    geo_bounds=ImageGeoBounds(
                        min_lat=image_bounds["min_lat"],
                        max_lat=image_bounds["max_lat"],
                        min_lng=image_bounds["min_lng"],
                        max_lng=image_bounds["max_lng"],
                        image_width=image.width,
                        image_height=image.height,
                    ),
                    original_geo_bounds=ImageGeoBounds(
                        min_lat=image_bounds["min_lat"],
                        max_lat=image_bounds["max_lat"],
                        min_lng=image_bounds["min_lng"],
                        max_lng=image_bounds["max_lng"],
                        image_width=image.width,
                        image_height=image.height,
                    ),
                    polygon_pixels=[],
                    success=False,
                    error_message=str(e),
                )
            except:
                raise
    
    def _create_feathered_mask(
        self,
        polygon_pixels: List[Tuple[int, int]],
        image_size: Tuple[int, int],
        feather_radius: int,
    ) -> Image.Image:
        """
        Create a grayscale mask with soft edges.
        
        The mask is:
        - White (255) inside the polygon
        - Black (0) outside the polygon
        - Gradient at the edges (feathered)
        """
        width, height = image_size
        
        # Create binary mask
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        
        # Draw filled polygon
        draw.polygon(polygon_pixels, fill=255)
        
        # Apply Gaussian blur for feathering
        if feather_radius > 0:
            # Blur creates the soft edge effect
            mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_radius))
        
        return mask
    
    def _apply_mask(
        self,
        image: Image.Image,
        mask: Image.Image,
        background_color: Tuple[int, int, int],
    ) -> Image.Image:
        """
        Apply mask to image, blending with background color.
        
        Where mask is white (255): show original image
        Where mask is black (0): show background color
        Where mask is gray: blend proportionally
        """
        # Convert to numpy for efficient blending
        img_array = np.array(image, dtype=np.float32)
        mask_array = np.array(mask, dtype=np.float32) / 255.0
        
        # Expand mask to 3 channels
        mask_3ch = np.stack([mask_array] * 3, axis=-1)
        
        # Create background
        background = np.full_like(img_array, background_color, dtype=np.float32)
        
        # Blend: result = image * alpha + background * (1 - alpha)
        result = img_array * mask_3ch + background * (1 - mask_3ch)
        
        # Convert back to PIL Image
        result = np.clip(result, 0, 255).astype(np.uint8)
        return Image.fromarray(result)
    
    def _tight_crop(
        self,
        image: Image.Image,
        polygon_pixels: List[Tuple[int, int]],
        padding: int,
    ) -> Tuple[Optional[Image.Image], int, int, List[Tuple[int, int]]]:
        """
        Crop image to polygon bounding box + padding.
        
        Returns:
            (cropped_image, offset_x, offset_y, adjusted_polygon_pixels)
            or (None, 0, 0, polygon_pixels) if crop not possible
        """
        if not polygon_pixels:
            return None, 0, 0, polygon_pixels
        
        width, height = image.size
        
        # Calculate bounding box
        xs = [p[0] for p in polygon_pixels]
        ys = [p[1] for p in polygon_pixels]
        
        min_x = max(0, min(xs) - padding)
        max_x = min(width, max(xs) + padding)
        min_y = max(0, min(ys) - padding)
        max_y = min(height, max(ys) + padding)
        
        # Check minimum dimensions
        crop_width = max_x - min_x
        crop_height = max_y - min_y
        
        if crop_width < self.MIN_DIMENSION or crop_height < self.MIN_DIMENSION:
            logger.info(f"      ℹ️ Crop too small ({crop_width}x{crop_height}), skipping")
            return None, 0, 0, polygon_pixels
        
        # Crop the image
        cropped = image.crop((min_x, min_y, max_x, max_y))
        
        # Adjust polygon coordinates for the crop
        adjusted_pixels = [(x - min_x, y - min_y) for x, y in polygon_pixels]
        
        return cropped, min_x, min_y, adjusted_pixels


# Singleton instance
polygon_masking_service = PolygonMaskingService()

