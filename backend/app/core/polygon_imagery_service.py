"""
PolygonImageryService - Fetches high-resolution satellite imagery for property polygons.

This service:
1. Takes a Shapely polygon (from Regrid)
2. Fetches Google satellite tiles via contextily
3. Stitches them into one image
4. Draws the polygon boundary on the image
5. Returns image ready for VLM analysis
"""

import contextily as ctx
from shapely.geometry import Polygon, MultiPolygon
from PIL import Image, ImageDraw
import numpy as np
from pyproj import Transformer
from typing import Tuple, Optional, Union
import io
import base64
import logging

logger = logging.getLogger(__name__)


class PolygonImageryService:
    """Service for fetching high-resolution satellite imagery of property polygons."""
    
    # Google satellite tiles - best quality for US
    GOOGLE_TILES = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
    
    # Fallback sources
    ESRI_TILES = ctx.providers.Esri.WorldImagery
    BING_TILES = "https://ecn.t0.tiles.virtualearth.net/tiles/a{q}.jpeg?g=14038"
    
    # Default settings
    DEFAULT_ZOOM = 20  # High detail
    DEFAULT_BOUNDARY_COLOR = (255, 0, 0)  # Red
    DEFAULT_BOUNDARY_WIDTH = 4
    
    def __init__(self):
        """Initialize the service."""
        # Transformer for converting lat/lng to Web Mercator
        self.transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    
    def get_polygon_image(
        self,
        polygon: Union[Polygon, MultiPolygon],
        zoom: int = None,
        draw_boundary: bool = True,
        boundary_color: Tuple[int, int, int] = None,
        boundary_width: int = None,
        padding_percent: float = 10.0,
        source: str = "google",
    ) -> Tuple[Image.Image, dict]:
        """
        Fetch high-resolution satellite image for a polygon.
        
        Args:
            polygon: Shapely Polygon with coordinates in (lng, lat) format
            zoom: Tile zoom level (default: 20 for high detail)
            draw_boundary: Whether to draw the polygon boundary on the image
            boundary_color: RGB tuple for boundary color (default: red)
            boundary_width: Line width for boundary (default: 4)
            padding_percent: Extra padding around polygon (default: 10%)
            source: Tile source - "google", "esri", or "bing"
        
        Returns:
            Tuple of (PIL Image, metadata dict)
        """
        zoom = zoom or self.DEFAULT_ZOOM
        boundary_color = boundary_color or self.DEFAULT_BOUNDARY_COLOR
        boundary_width = boundary_width or self.DEFAULT_BOUNDARY_WIDTH
        
        # Handle MultiPolygon - use the largest polygon
        if isinstance(polygon, MultiPolygon):
            polygon = max(polygon.geoms, key=lambda p: p.area)
        
        # Get bounds with padding
        minx, miny, maxx, maxy = polygon.bounds
        
        # Add padding
        width = maxx - minx
        height = maxy - miny
        pad_x = width * (padding_percent / 100)
        pad_y = height * (padding_percent / 100)
        
        padded_bounds = (
            minx - pad_x,  # west
            miny - pad_y,  # south
            maxx + pad_x,  # east
            maxy + pad_y,  # north
        )
        
        # Select tile source
        tile_source = self._get_tile_source(source)
        
        logger.info(f"Fetching imagery for polygon at zoom {zoom}")
        logger.info(f"Bounds (lng/lat): W={padded_bounds[0]:.6f}, S={padded_bounds[1]:.6f}, E={padded_bounds[2]:.6f}, N={padded_bounds[3]:.6f}")
        
        # Fetch tiles using contextily
        try:
            img_array, extent = ctx.bounds2img(
                padded_bounds[0],  # west
                padded_bounds[1],  # south
                padded_bounds[2],  # east
                padded_bounds[3],  # north
                zoom=zoom,
                source=tile_source,
                ll=True  # Bounds are in lat/lng
            )
        except Exception as e:
            logger.warning(f"Failed with {source}, trying fallback: {e}")
            # Try fallback source
            fallback_source = self.ESRI_TILES if source == "google" else self.GOOGLE_TILES
            img_array, extent = ctx.bounds2img(
                padded_bounds[0], padded_bounds[1], padded_bounds[2], padded_bounds[3],
                zoom=zoom,
                source=fallback_source,
                ll=True
            )
        
        # extent is (left, right, bottom, top) in Web Mercator (EPSG:3857)
        extent_left, extent_right, extent_bottom, extent_top = extent
        
        # Convert to PIL Image
        img = Image.fromarray(img_array)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        logger.info(f"Image size: {img.size[0]}x{img.size[1]} pixels")
        
        # Draw polygon boundary if requested
        if draw_boundary:
            img = self._draw_polygon_boundary(
                img, polygon, extent, boundary_color, boundary_width
            )
        
        # Build metadata
        metadata = {
            "source": source,
            "zoom": zoom,
            "image_width": img.size[0],
            "image_height": img.size[1],
            "bounds_lnglat": {
                "west": padded_bounds[0],
                "south": padded_bounds[1],
                "east": padded_bounds[2],
                "north": padded_bounds[3],
            },
            "bounds_mercator": {
                "left": extent_left,
                "right": extent_right,
                "bottom": extent_bottom,
                "top": extent_top,
            },
            "polygon_area_sqm": self._calculate_area_sqm(polygon),
            "boundary_drawn": draw_boundary,
        }
        
        return img, metadata
    
    def get_polygon_image_base64(
        self,
        polygon: Union[Polygon, MultiPolygon],
        **kwargs
    ) -> Tuple[str, dict]:
        """
        Same as get_polygon_image but returns base64-encoded image.
        
        Useful for sending to APIs (GPT-4o, etc.)
        """
        img, metadata = self.get_polygon_image(polygon, **kwargs)
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        buffer.seek(0)
        
        base64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        metadata["format"] = "jpeg"
        metadata["base64_length"] = len(base64_str)
        
        return base64_str, metadata
    
    def get_polygon_image_bytes(
        self,
        polygon: Union[Polygon, MultiPolygon],
        **kwargs
    ) -> Tuple[bytes, dict]:
        """
        Same as get_polygon_image but returns image bytes.
        """
        img, metadata = self.get_polygon_image(polygon, **kwargs)
        
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        buffer.seek(0)
        
        metadata["format"] = "jpeg"
        return buffer.getvalue(), metadata
    
    def _get_tile_source(self, source: str):
        """Get the tile source URL/provider."""
        sources = {
            "google": self.GOOGLE_TILES,
            "esri": self.ESRI_TILES,
            "bing": self.BING_TILES,
        }
        return sources.get(source.lower(), self.GOOGLE_TILES)
    
    def _draw_polygon_boundary(
        self,
        img: Image.Image,
        polygon: Polygon,
        extent: Tuple[float, float, float, float],
        color: Tuple[int, int, int],
        width: int,
    ) -> Image.Image:
        """Draw the polygon boundary on the image."""
        extent_left, extent_right, extent_bottom, extent_top = extent
        img_width, img_height = img.size
        
        # Get polygon exterior coordinates
        coords = list(polygon.exterior.coords)
        
        # Convert each coordinate from lat/lng to pixel
        pixel_coords = []
        for lng, lat in coords:
            # Convert to Web Mercator
            mx, my = self.transformer.transform(lng, lat)
            
            # Convert to pixel coordinates
            px = (mx - extent_left) / (extent_right - extent_left) * img_width
            py = (extent_top - my) / (extent_top - extent_bottom) * img_height
            pixel_coords.append((px, py))
        
        # Draw the boundary
        draw = ImageDraw.Draw(img)
        
        # Draw as a polygon outline (closed shape)
        if len(pixel_coords) >= 3:
            draw.polygon(pixel_coords, outline=color, width=width)
            
            # Also draw lines for thicker border
            for i in range(len(pixel_coords)):
                start = pixel_coords[i]
                end = pixel_coords[(i + 1) % len(pixel_coords)]
                draw.line([start, end], fill=color, width=width)
        
        # Also draw interior rings (holes) if any
        for interior in polygon.interiors:
            interior_coords = list(interior.coords)
            interior_pixel_coords = []
            for lng, lat in interior_coords:
                mx, my = self.transformer.transform(lng, lat)
                px = (mx - extent_left) / (extent_right - extent_left) * img_width
                py = (extent_top - my) / (extent_top - extent_bottom) * img_height
                interior_pixel_coords.append((px, py))
            
            for i in range(len(interior_pixel_coords)):
                start = interior_pixel_coords[i]
                end = interior_pixel_coords[(i + 1) % len(interior_pixel_coords)]
                draw.line([start, end], fill=color, width=width)
        
        return img
    
    def _calculate_area_sqm(self, polygon: Polygon) -> float:
        """Calculate approximate area in square meters."""
        # Transform to a projected CRS for accurate area calculation
        # Using Web Mercator for simplicity (not perfect but good enough)
        coords = list(polygon.exterior.coords)
        mercator_coords = [self.transformer.transform(lng, lat) for lng, lat in coords]
        mercator_polygon = Polygon(mercator_coords)
        return mercator_polygon.area


# Singleton instance
_service_instance = None

def get_polygon_imagery_service() -> PolygonImageryService:
    """Get or create the singleton service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PolygonImageryService()
    return _service_instance

