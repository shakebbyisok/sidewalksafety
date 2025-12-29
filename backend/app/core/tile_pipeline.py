"""
TilePipeline - Clean orchestrator for tile-based property analysis.

This is the main entry point for analyzing a property using the tile-based approach:
1. Calculate tile grid based on property size estimate
2. Fetch high-resolution satellite imagery for each tile
3. Run CV analysis on each tile (segmentation + condition)
4. Aggregate results into property-level metrics
5. Store everything in the database

Design Principles:
- Single responsibility: One class orchestrates the pipeline
- Clear stages with logging
- Graceful error handling
- Progress tracking
"""

import logging
import uuid
from typing import Optional, Tuple, Dict
from datetime import datetime
from shapely.geometry import Point, Polygon

from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape

from app.core.config import settings
from app.core.tile_service import tile_service, TileGrid
from app.core.tile_imagery_service import tile_imagery_service, TileImageryResult
from app.core.tile_analyzer_service import tile_analyzer_service, TileGridAnalysisResult
from app.core.result_aggregator_service import result_aggregator_service, AggregatedPropertyAnalysis

from app.models.property_analysis import PropertyAnalysis
from app.models.analysis_tile import AnalysisTile
from app.models.parking_lot import ParkingLot
from app.models.business import Business

logger = logging.getLogger(__name__)


class TilePipeline:
    """
    Clean orchestrator for tile-based property analysis.
    
    Usage:
        pipeline = TilePipeline()
        result = await pipeline.analyze_property(
            db=db,
            lat=38.947,
            lng=-121.100,
            business_name="Auburn HOA",
            property_type="hoa",
            user_id=user_id
        )
    """
    
    def __init__(self):
        self.tile_service = tile_service
        self.imagery_service = tile_imagery_service
        self.analyzer_service = tile_analyzer_service
        self.aggregator_service = result_aggregator_service
    
    async def analyze_property(
        self,
        db: Session,
        lat: float,
        lng: float,
        user_id: uuid.UUID,
        business_id: Optional[uuid.UUID] = None,
        parking_lot_id: Optional[uuid.UUID] = None,
        business_name: Optional[str] = None,
        address: Optional[str] = None,
        property_type: str = "default",
        property_boundary: Optional[Polygon] = None,
        regrid_parcel: Optional[any] = None,  # PropertyParcel from Regrid
        min_zoom: int = 18,
        max_zoom: int = 20
    ) -> Optional[PropertyAnalysis]:
        """
        Analyze a property using the tile-based pipeline.
        
        Args:
            db: Database session
            lat: Property center latitude
            lng: Property center longitude
            user_id: User who initiated the analysis
            business_id: Optional linked business
            parking_lot_id: Optional linked parking lot
            business_name: Business name for logging
            address: Property address
            property_type: Type of property (hoa, apartment_complex, etc.)
            property_boundary: Optional exact property boundary polygon
            min_zoom: Minimum zoom level for tiles
            max_zoom: Maximum zoom level for tiles
            
        Returns:
            PropertyAnalysis with all results stored in DB
        """
        logger.info(f"")
        logger.info(f"{'='*60}")
        logger.info(f"🏗️  TILE PIPELINE: {business_name or 'Unknown'}")
        logger.info(f"{'='*60}")
        logger.info(f"   📍 Location: ({lat}, {lng})")
        logger.info(f"   📋 Type: {property_type}")
        
        try:
            # ============ STAGE 1: Calculate Tile Grid ============
            logger.info(f"")
            logger.info(f"   📐 STAGE 1: Calculating tile grid...")
            
            if property_boundary:
                # Use exact boundary from Regrid
                tile_grid = self.tile_service.calculate_tile_grid(
                    boundary=property_boundary,
                    min_zoom=min_zoom,
                    max_zoom=max_zoom
                )
                if regrid_parcel:
                    logger.info(f"      ✅ Using REGRID property boundary")
                    logger.info(f"         Owner: {regrid_parcel.owner}")
                    logger.info(f"         Parcel: {regrid_parcel.parcel_id}")
                else:
                    logger.info(f"      Using provided property boundary")
            else:
                # Estimate based on property type
                radius_m = self.tile_service.estimate_property_radius(property_type)
                tile_grid = self.tile_service.calculate_tiles_for_point(
                    lat=lat,
                    lng=lng,
                    radius_m=radius_m,
                    zoom=19  # High resolution
                )
                logger.info(f"      Estimated radius: {radius_m}m based on property type")
                
                # Create an estimated boundary from the tile grid
                property_boundary = self._create_estimated_boundary(lat, lng, radius_m)
                logger.info(f"      📐 Created estimated boundary: {radius_m*2}m x {radius_m*2}m")
            
            logger.info(f"      📊 Grid: {tile_grid.rows}x{tile_grid.cols} = {tile_grid.total_tiles} tiles")
            logger.info(f"      🔍 Zoom: {tile_grid.zoom}")
            logger.info(f"      📏 Tile size: {tile_grid.tile_size_m:.0f}m")
            logger.info(f"      📐 Estimated property: {tile_grid.property_area_m2:,.0f} m²")
            
            # ============ STAGE 2: Fetch Satellite Imagery ============
            logger.info(f"")
            logger.info(f"   🛰️  STAGE 2: Fetching satellite imagery...")
            
            imagery_result = await self.imagery_service.fetch_tile_imagery(
                tile_grid=tile_grid,
                progress_callback=lambda done, total: logger.debug(f"      Fetched {done}/{total} tiles")
            )
            
            logger.info(f"      ✅ Fetched {imagery_result.successful_tiles}/{imagery_result.total_tiles} tiles")
            logger.info(f"      💾 Total size: {imagery_result.total_size_bytes/1024/1024:.1f} MB")
            logger.info(f"      ⏱️  Duration: {imagery_result.fetch_duration_seconds:.1f}s")
            
            if imagery_result.successful_tiles == 0:
                raise ValueError("Failed to fetch any satellite imagery")
            
            # ============ STAGE 3: Run CV Analysis ============
            logger.info(f"")
            logger.info(f"   🔬 STAGE 3: Running CV analysis...")
            
            analysis_result = await self.analyzer_service.analyze_tiles(
                tile_images=[t for t in imagery_result.tiles if t.is_valid],
                run_condition=True,
                progress_callback=lambda done, total, idx: logger.debug(f"      Analyzed tile {idx} ({done}/{total})")
            )
            
            logger.info(f"      ✅ Analyzed {analysis_result.analyzed_tiles}/{analysis_result.total_tiles} tiles")
            logger.info(f"      🅿️  Tiles with asphalt: {analysis_result.tiles_with_asphalt}")
            logger.info(f"      ⚠️  Tiles with damage: {analysis_result.tiles_with_damage}")
            logger.info(f"      ⏱️  Duration: {analysis_result.total_duration_seconds:.1f}s")
            
            # ============ STAGE 4: Aggregate Results ============
            logger.info(f"")
            logger.info(f"   📊 STAGE 4: Aggregating results...")
            
            aggregated = self.aggregator_service.aggregate(
                tile_grid=tile_grid,
                analysis_result=analysis_result,
                property_id=str(parking_lot_id) if parking_lot_id else None,
                business_name=business_name,
                address=address
            )
            
            logger.info(f"      📏 Total asphalt: {aggregated.asphalt.total_area_sqft:,.0f} sqft")
            logger.info(f"      🎯 Condition score: {aggregated.condition.overall_score:.0f}/100")
            logger.info(f"      🔥 Hotspots: {len(aggregated.hotspots)}")
            logger.info(f"      ⭐ Lead quality: {aggregated.lead_quality.upper()}")
            
            # ============ STAGE 5: Save to Database ============
            logger.info(f"")
            logger.info(f"   💾 STAGE 5: Saving to database...")
            
            property_analysis = await self._save_to_database(
                db=db,
                tile_grid=tile_grid,
                imagery_result=imagery_result,
                analysis_result=analysis_result,
                aggregated=aggregated,
                user_id=user_id,
                business_id=business_id,
                parking_lot_id=parking_lot_id,
                lat=lat,
                lng=lng,
                property_boundary=property_boundary,
                regrid_parcel=regrid_parcel
            )
            
            logger.info(f"      ✅ Saved PropertyAnalysis: {property_analysis.id}")
            logger.info(f"      📊 Saved {len(analysis_result.tile_results)} tiles")
            
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"✅ PIPELINE COMPLETE: {business_name or 'Unknown'}")
            logger.info(f"{'='*60}")
            
            return property_analysis
            
        except Exception as e:
            logger.error(f"")
            logger.error(f"❌ PIPELINE FAILED: {str(e)}")
            logger.exception(e)
            
            # Try to save failed analysis
            try:
                property_analysis = PropertyAnalysis(
                    id=uuid.uuid4(),
                    parking_lot_id=parking_lot_id,
                    user_id=user_id,
                    business_id=business_id,
                    business_location=from_shape(Point(lng, lat), srid=4326),
                    status="failed",
                    error_message=str(e),
                    created_at=datetime.utcnow()
                )
                db.add(property_analysis)
                db.commit()
                return property_analysis
            except Exception:
                db.rollback()
                return None
    
    async def _save_to_database(
        self,
        db: Session,
        tile_grid: TileGrid,
        imagery_result: TileImageryResult,
        analysis_result: TileGridAnalysisResult,
        aggregated: AggregatedPropertyAnalysis,
        user_id: uuid.UUID,
        business_id: Optional[uuid.UUID],
        parking_lot_id: Optional[uuid.UUID],
        lat: float,
        lng: float,
        property_boundary: Optional[Polygon] = None,
        regrid_parcel: Optional[any] = None
    ) -> PropertyAnalysis:
        """Save all results to the database."""
        
        # Create PropertyAnalysis record
        analysis_id = uuid.uuid4()
        
        property_analysis = PropertyAnalysis(
            id=analysis_id,
            parking_lot_id=parking_lot_id,
            user_id=user_id,
            business_id=business_id,
            business_location=from_shape(Point(lng, lat), srid=4326),
            
            # Property boundary from Regrid (if available)
            property_boundary_polygon=from_shape(property_boundary, srid=4326) if property_boundary else None,
            property_boundary_source="regrid" if regrid_parcel else "estimated",
            property_parcel_id=regrid_parcel.parcel_id if regrid_parcel else None,
            property_owner=regrid_parcel.owner if regrid_parcel else None,
            property_apn=regrid_parcel.apn if regrid_parcel else None,
            property_land_use=regrid_parcel.land_use if regrid_parcel else None,
            property_zoning=regrid_parcel.zoning if regrid_parcel else None,
            
            # Analysis type
            analysis_type="tiled",
            
            # Aggregated asphalt metrics
            total_asphalt_area_m2=aggregated.asphalt.total_area_m2,
            total_asphalt_area_sqft=aggregated.asphalt.total_area_sqft,
            parking_area_m2=aggregated.asphalt.parking_area_m2,
            parking_area_sqft=aggregated.asphalt.parking_area_sqft,
            road_area_m2=aggregated.asphalt.road_area_m2,
            road_area_sqft=aggregated.asphalt.road_area_sqft,
            
            # Private asphalt (after filtering public roads)
            private_asphalt_area_m2=aggregated.asphalt.private_asphalt_area_m2,
            private_asphalt_area_sqft=aggregated.asphalt.private_asphalt_area_sqft,
            
            # Total paved area (asphalt + concrete)
            total_paved_area_m2=aggregated.asphalt.private_asphalt_area_m2,  # Same for now
            total_paved_area_sqft=aggregated.asphalt.private_asphalt_area_sqft,
            
            # Merged GeoJSON from all tiles
            private_asphalt_geojson=self._merge_tile_geojsons(analysis_result),
            
            # Public roads filtered out
            public_road_area_m2=aggregated.asphalt.public_road_area_m2,
            
            # Aggregated condition metrics
            weighted_condition_score=aggregated.condition.overall_score,
            worst_tile_score=aggregated.condition.worst_tile_score,
            best_tile_score=aggregated.condition.best_tile_score,
            total_crack_count=aggregated.condition.total_crack_count,
            total_pothole_count=aggregated.condition.total_pothole_count,
            total_detection_count=aggregated.condition.total_detection_count,
            damage_density=aggregated.condition.damage_density,
            
            # Tile grid info
            total_tiles=tile_grid.total_tiles,
            analyzed_tiles=analysis_result.analyzed_tiles,
            tiles_with_asphalt=analysis_result.tiles_with_asphalt,
            tiles_with_damage=analysis_result.tiles_with_damage,
            tile_zoom_level=tile_grid.zoom,
            tile_grid_rows=tile_grid.rows,
            tile_grid_cols=tile_grid.cols,
            
            # Lead quality
            lead_quality=aggregated.lead_quality,
            hotspot_count=len(aggregated.hotspots),
            
            # Status
            status="completed",
            analyzed_at=datetime.utcnow(),
            created_at=datetime.utcnow()
        )
        
        db.add(property_analysis)
        
        # Create AnalysisTile records
        for tile_result in analysis_result.tile_results:
            tile = tile_result.tile_image.tile
            tile_image = tile_result.tile_image
            
            # Create tile polygon for map display
            tile_polygon = Polygon([
                (tile.bounds["min_lng"], tile.bounds["min_lat"]),
                (tile.bounds["max_lng"], tile.bounds["min_lat"]),
                (tile.bounds["max_lng"], tile.bounds["max_lat"]),
                (tile.bounds["min_lng"], tile.bounds["max_lat"]),
                (tile.bounds["min_lng"], tile.bounds["min_lat"]),
            ])
            
            analysis_tile = AnalysisTile(
                id=uuid.uuid4(),
                property_analysis_id=analysis_id,
                
                # Tile identification
                tile_index=tile.index,
                
                # Location
                center_lat=tile.center_lat,
                center_lng=tile.center_lng,
                zoom_level=tile.zoom,
                
                # Bounds
                bounds_min_lat=tile.bounds["min_lat"],
                bounds_max_lat=tile.bounds["max_lat"],
                bounds_min_lng=tile.bounds["min_lng"],
                bounds_max_lng=tile.bounds["max_lng"],
                
                # Polygon
                tile_polygon=from_shape(tile_polygon, srid=4326),
                
                # Imagery
                satellite_image_base64=tile_image.image_base64,
                image_size_bytes=tile_image.size_bytes,
                
                # Segmentation results (total asphalt from CV)
                asphalt_area_m2=tile_result.segmentation.total_asphalt_area_m2 if tile_result.segmentation else 0,
                parking_area_m2=tile_result.segmentation.parking_area_m2 if tile_result.segmentation else 0,
                road_area_m2=tile_result.segmentation.road_area_m2 if tile_result.segmentation else 0,
                segmentation_raw=tile_result.segmentation.raw_response if tile_result.segmentation else None,
                
                # Private asphalt (after filtering public roads)
                private_asphalt_area_m2=tile_result.segmentation.private_asphalt_area_m2 if tile_result.segmentation else 0,
                private_asphalt_area_sqft=tile_result.segmentation.private_asphalt_area_sqft if tile_result.segmentation else 0,
                private_asphalt_geojson=tile_result.segmentation.private_asphalt_geojson if tile_result.segmentation else None,
                
                # Public roads filtered out
                public_road_area_m2=tile_result.segmentation.public_road_area_m2 if tile_result.segmentation else 0,
                
                # Source of asphalt detection
                asphalt_source=tile_result.segmentation.asphalt_source if tile_result.segmentation else None,
                
                # Condition results
                condition_score=tile_result.condition.condition_score if tile_result.condition else 100,
                crack_count=tile_result.condition.crack_count if tile_result.condition else 0,
                pothole_count=tile_result.condition.pothole_count if tile_result.condition else 0,
                detection_count=len(tile_result.condition.detections) if tile_result.condition else 0,
                condition_raw=tile_result.condition.raw_response if tile_result.condition else None,
                
                # Status
                status=tile_result.analysis_status,
                error_message=tile_result.error_message,
                
                # Timestamps
                imagery_fetched_at=tile_image.fetched_at,
                analyzed_at=tile_result.analyzed_at
            )
            
            db.add(analysis_tile)
        
        # Update parking lot if linked
        if parking_lot_id:
            parking_lot = db.query(ParkingLot).filter(ParkingLot.id == parking_lot_id).first()
            if parking_lot:
                parking_lot.condition_score = aggregated.condition.overall_score
                parking_lot.crack_count = aggregated.condition.total_crack_count
                parking_lot.pothole_count = aggregated.condition.total_pothole_count
                parking_lot.evaluation_status = "completed"
                parking_lot.last_evaluated = datetime.utcnow()
        
        db.commit()
        db.refresh(property_analysis)
        
        return property_analysis
    
    def _create_estimated_boundary(self, lat: float, lng: float, radius_m: float) -> Polygon:
        """
        Create an estimated rectangular boundary polygon around a point.
        
        Used when Regrid doesn't return a parcel boundary.
        """
        import math
        
        # Convert radius to degrees (approximate)
        lat_offset = radius_m / 111000  # 1 degree lat ≈ 111km
        lng_offset = radius_m / (111000 * math.cos(math.radians(lat)))
        
        # Create a rectangular boundary
        min_lat = lat - lat_offset
        max_lat = lat + lat_offset
        min_lng = lng - lng_offset
        max_lng = lng + lng_offset
        
        return Polygon([
            (min_lng, min_lat),
            (max_lng, min_lat),
            (max_lng, max_lat),
            (min_lng, max_lat),
            (min_lng, min_lat),
        ])
    
    def _merge_tile_geojsons(self, analysis_result) -> Optional[Dict]:
        """
        Merge all tile GeoJSONs into a single FeatureCollection.
        """
        features = []
        
        for tile_result in analysis_result.tile_results:
            if tile_result.segmentation and tile_result.segmentation.private_asphalt_geojson:
                geojson = tile_result.segmentation.private_asphalt_geojson
                
                # Handle both single features and FeatureCollections
                if geojson.get("type") == "FeatureCollection":
                    features.extend(geojson.get("features", []))
                elif geojson.get("type") == "Feature":
                    features.append(geojson)
                else:
                    # Assume it's just a geometry
                    features.append({
                        "type": "Feature",
                        "geometry": geojson,
                        "properties": {"surface_type": "paved"}
                    })
        
        if not features:
            return None
        
        return {
            "type": "FeatureCollection",
            "features": features
        }


# Singleton instance
tile_pipeline = TilePipeline()

