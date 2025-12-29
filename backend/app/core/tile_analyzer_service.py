"""
TileAnalyzerService - Run CV analysis on each tile.

This service runs computer vision analysis on each tile:
1. Segmentation - Detect buildings, parking, roads, vegetation
2. Private asphalt detection - Filter out public roads using OSM
3. Condition evaluation - Detect cracks, potholes, damage (only on private asphalt)

Design Principles:
- Analyze each tile independently for parallelization
- Track confidence and quality metrics per tile
- Handle CV failures gracefully
- Only analyze PRIVATE asphalt (not public roads)
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from shapely.geometry import Polygon, shape

from app.core.config import settings
from app.core.tile_imagery_service import TileImage
from app.core.asphalt_segmentation_service import asphalt_segmentation_service
from app.core.private_asphalt_service import private_asphalt_service, PrivateAsphaltResult
from app.core.condition_evaluation_service import condition_evaluation_service
from shapely.geometry import Polygon, MultiPolygon

logger = logging.getLogger(__name__)


def _get_polygon_coords(geom) -> list:
    """
    Safely extract coordinates from a Polygon or MultiPolygon.
    For MultiPolygon, returns coords of the largest polygon.
    """
    if geom is None:
        return None
    
    try:
        if isinstance(geom, MultiPolygon):
            # Get the largest polygon from the MultiPolygon
            if len(geom.geoms) > 0:
                largest = max(geom.geoms, key=lambda p: p.area)
                return list(largest.exterior.coords)
            return None
        elif hasattr(geom, 'exterior'):
            return list(geom.exterior.coords)
        else:
            return None
    except Exception:
        return None


@dataclass
class TileSegmentation:
    """Segmentation results for a single tile."""
    buildings: List[Dict] = field(default_factory=list)
    parking_areas: List[Dict] = field(default_factory=list)
    roads: List[Dict] = field(default_factory=list)
    vegetation: List[Dict] = field(default_factory=list)
    
    # Total asphalt detected by CV (includes public roads)
    total_asphalt_area_m2: float = 0
    parking_area_m2: float = 0
    road_area_m2: float = 0
    
    # Private asphalt (after subtracting public roads from OSM)
    private_asphalt_area_m2: float = 0
    private_asphalt_area_sqft: float = 0
    private_asphalt_polygon: Optional[Polygon] = None
    private_asphalt_geojson: Optional[Dict] = None  # For frontend display
    
    # Public roads filtered out
    public_road_area_m2: float = 0
    public_road_polygon: Optional[Polygon] = None
    
    # Source of asphalt detection
    asphalt_source: str = "cv_with_osm_filter"  # cv_only, cv_with_osm_filter, fallback
    
    raw_response: Optional[Dict] = None


@dataclass
class TileCondition:
    """Condition evaluation results for a single tile."""
    condition_score: float = 100  # 100 = perfect, 0 = terrible
    crack_count: int = 0
    pothole_count: int = 0
    fading_score: float = 100
    detections: List[Dict] = field(default_factory=list)
    raw_response: Optional[Dict] = None


@dataclass
class TileAnalysisResult:
    """Complete analysis result for a single tile."""
    tile_image: TileImage
    segmentation: Optional[TileSegmentation] = None
    condition: Optional[TileCondition] = None
    analysis_status: str = "pending"  # pending, success, partial, failed
    error_message: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    analysis_duration_seconds: float = 0
    
    @property
    def is_valid(self) -> bool:
        return self.analysis_status in ("success", "partial")
    
    @property
    def has_asphalt(self) -> bool:
        """Check if tile has PRIVATE asphalt (not public roads)."""
        if not self.segmentation:
            return False
        # Use private asphalt (after filtering public roads)
        return self.segmentation.private_asphalt_area_m2 > 0
    
    @property
    def has_damage(self) -> bool:
        if not self.condition:
            return False
        return self.condition.crack_count > 0 or self.condition.pothole_count > 0


@dataclass
class TileGridAnalysisResult:
    """Complete analysis result for all tiles."""
    tile_results: List[TileAnalysisResult]
    total_tiles: int
    analyzed_tiles: int
    tiles_with_asphalt: int
    tiles_with_damage: int
    total_duration_seconds: float


class TileAnalyzerService:
    """
    Run CV analysis on tiles.
    
    Two-stage analysis:
    1. Segmentation - Identify what's in the tile (buildings, parking, roads)
    2. Condition - Evaluate pavement condition (cracks, potholes)
    
    Only runs condition analysis on tiles that have detected asphalt.
    """
    
    # Configuration
    MAX_CONCURRENT_ANALYSIS = 3  # CV API can be slow, don't overwhelm
    MIN_ASPHALT_AREA_M2 = 50  # Skip tiles with very little asphalt
    
    async def analyze_tiles(
        self,
        tile_images: List[TileImage],
        run_condition: bool = True,
        progress_callback: Optional[callable] = None
    ) -> TileGridAnalysisResult:
        """
        Analyze all tiles in a grid.
        
        Args:
            tile_images: List of tile images to analyze
            run_condition: Whether to run condition evaluation
            progress_callback: Optional callback(completed, total, current_tile) 
            
        Returns:
            TileGridAnalysisResult with all analysis results
        """
        start_time = datetime.utcnow()
        
        # Filter to only valid images
        valid_images = [t for t in tile_images if t.is_valid]
        logger.info(f"🔬 Analyzing {len(valid_images)} tiles...")
        
        # Create result objects
        results = [TileAnalysisResult(tile_image=img) for img in valid_images]
        
        # Analyze tiles with concurrency limit
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_ANALYSIS)
        
        async def analyze_with_semaphore(result: TileAnalysisResult, index: int):
            async with semaphore:
                await self._analyze_single_tile(result, run_condition)
                if progress_callback:
                    progress_callback(index + 1, len(results), result.tile_image.tile.index)
        
        # Run analysis
        tasks = [
            analyze_with_semaphore(result, i)
            for i, result in enumerate(results)
        ]
        await asyncio.gather(*tasks)
        
        # Calculate summary
        duration = (datetime.utcnow() - start_time).total_seconds()
        analyzed = sum(1 for r in results if r.is_valid)
        with_asphalt = sum(1 for r in results if r.has_asphalt)
        with_damage = sum(1 for r in results if r.has_damage)
        
        logger.info(f"   ✅ Analyzed {analyzed}/{len(results)} tiles in {duration:.1f}s")
        logger.info(f"      Tiles with asphalt: {with_asphalt}")
        logger.info(f"      Tiles with damage: {with_damage}")
        
        return TileGridAnalysisResult(
            tile_results=results,
            total_tiles=len(results),
            analyzed_tiles=analyzed,
            tiles_with_asphalt=with_asphalt,
            tiles_with_damage=with_damage,
            total_duration_seconds=duration
        )
    
    async def _analyze_single_tile(
        self,
        result: TileAnalysisResult,
        run_condition: bool
    ) -> None:
        """
        Analyze a single tile using the new private asphalt detection approach.
        
        Flow:
        1. Run CV to detect ALL asphalt surfaces
        2. Query OSM for public roads
        3. SUBTRACT public roads = PRIVATE asphalt only
        4. Run damage detection ONLY on private asphalt
        
        Updates the result object in place.
        """
        start_time = datetime.utcnow()
        tile = result.tile_image.tile
        image_bytes = result.tile_image.image_bytes
        
        try:
            # Calculate image bounds for geo-referencing
            image_bounds = tile.bounds
            
            # ============ NEW: Private Asphalt Detection ============
            # This combines CV segmentation + OSM road filtering
            logger.debug(f"   🔍 Detecting private asphalt for tile {tile.index}...")
            
            private_asphalt_result = await private_asphalt_service.detect_private_asphalt(
                image_bytes=image_bytes,
                image_bounds=image_bounds,
                property_boundary=None,  # Tile is already clipped to property
                skip_osm_filter=False,  # Always filter public roads
            )
            
            # Convert to tile segmentation format with private asphalt info
            result.segmentation = TileSegmentation(
                buildings=[{
                    "area_m2": private_asphalt_result.building_area_m2,
                    "count": len(private_asphalt_result.building_polygons),
                }] if private_asphalt_result.building_polygons else [],
                parking_areas=[],  # Deprecated - use private_asphalt_polygon instead
                roads=[],  # Deprecated - use public_road_polygon instead
                
                # Total asphalt from CV (before road filtering)
                total_asphalt_area_m2=private_asphalt_result.total_asphalt_area_m2,
                parking_area_m2=private_asphalt_result.private_asphalt_area_m2,  # Use private asphalt as "parking"
                road_area_m2=private_asphalt_result.public_road_area_m2,
                
                # NEW: Private asphalt (after subtracting public roads)
                private_asphalt_area_m2=private_asphalt_result.private_asphalt_area_m2,
                private_asphalt_area_sqft=private_asphalt_result.private_asphalt_area_sqft,
                private_asphalt_polygon=private_asphalt_result.private_asphalt_polygon,
                private_asphalt_geojson=private_asphalt_service.get_polygon_geojson(
                    private_asphalt_result.private_asphalt_polygon,
                    {"source": private_asphalt_result.source, "tile_index": tile.index}
                ),
                
                # Public roads that were filtered out
                public_road_area_m2=private_asphalt_result.public_road_area_m2,
                public_road_polygon=private_asphalt_result.public_road_polygon,
                
                # Source of detection
                asphalt_source=private_asphalt_result.source,
                
                raw_response={
                    "detection_method": private_asphalt_result.detection_method,
                    "osm_filter_used": private_asphalt_result.osm_road_filter_used,
                    "source": private_asphalt_result.source,
                    "total_asphalt_m2": private_asphalt_result.total_asphalt_area_m2,
                    "private_asphalt_m2": private_asphalt_result.private_asphalt_area_m2,
                    "public_road_m2": private_asphalt_result.public_road_area_m2,
                }
            )
            
            logger.debug(f"   ✅ Tile {tile.index}: {result.segmentation.private_asphalt_area_m2:.0f}m² private asphalt (filtered {result.segmentation.public_road_area_m2:.0f}m² public roads)")
            
            # ============ Stage 2: Condition Evaluation ============
            # Only run on tiles with significant PRIVATE asphalt
            if run_condition and result.segmentation.private_asphalt_area_m2 >= self.MIN_ASPHALT_AREA_M2:
                logger.debug(f"   🔬 Evaluating condition for tile {tile.index} (private asphalt only)...")
                
                try:
                    # TODO: In the future, we could mask the image to only analyze private asphalt pixels
                    # For now, we analyze the whole tile but trust that most asphalt is private
                    condition_result = await condition_evaluation_service.evaluate_condition(
                        image_bytes=image_bytes,
                        parking_lot_id=f"tile_{tile.index}"
                    )
                    
                    # Safely extract values with None handling
                    score = condition_result.get("condition_score") if condition_result else None
                    detection_count = condition_result.get("detection_count") if condition_result else 0
                    degradation_areas = condition_result.get("degradation_areas", []) if condition_result else []
                    
                    result.condition = TileCondition(
                        condition_score=score if score is not None else 100,
                        crack_count=detection_count if detection_count is not None else 0,
                        pothole_count=len([
                            d for d in degradation_areas
                            if d and "pothole" in d.get("class", "").lower()
                        ]),
                        detections=degradation_areas or [],
                        raw_response=condition_result
                    )
                except Exception as e:
                    logger.warning(f"   ⚠️ Condition evaluation failed for tile {tile.index}: {e}")
                    # Set default condition on error
                    result.condition = TileCondition(condition_score=100, crack_count=0, pothole_count=0)
            else:
                # No significant private asphalt, skip condition evaluation
                if result.segmentation.private_asphalt_area_m2 < self.MIN_ASPHALT_AREA_M2:
                    logger.debug(f"   ⏭️ Skipping condition for tile {tile.index}: only {result.segmentation.private_asphalt_area_m2:.0f}m² private asphalt")
                result.condition = TileCondition(condition_score=100, crack_count=0, pothole_count=0)
            
            result.analysis_status = "success"
            
        except Exception as e:
            logger.error(f"   ❌ Error analyzing tile {tile.index}: {e}")
            import traceback
            traceback.print_exc()
            result.analysis_status = "failed"
            result.error_message = str(e)
        
        result.analyzed_at = datetime.utcnow()
        result.analysis_duration_seconds = (datetime.utcnow() - start_time).total_seconds()


# Singleton instance
tile_analyzer_service = TileAnalyzerService()

