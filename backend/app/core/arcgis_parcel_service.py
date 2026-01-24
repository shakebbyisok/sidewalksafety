"""
Regrid Tileserver Parcel Service

Fetches parcel geometries from Regrid's MVT vector tiles.
Uses tiles endpoint (200k/month quota) NOT records endpoint (2k/month quota).

Tiles include: geometry + address, owner, parcelnumb, ll_uuid
Size filtering is done client-side after decoding tiles.
"""

import httpx
import logging
import math
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import asyncio

import mercantile
from shapely.geometry import shape, mapping, Polygon, MultiPolygon, Point
from shapely.ops import transform
import pyproj
import mapbox_vector_tile as mvt

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryParcel:
    """Parcel data from Regrid tiles"""
    id: str
    address: str
    acreage: float
    apn: str
    regrid_id: str
    geometry: Dict[str, Any]
    centroid: Dict[str, float]
    owner: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "address": self.address,
            "acreage": self.acreage,
            "apn": self.apn,
            "regrid_id": self.regrid_id,
            "geometry": self.geometry,
            "centroid": self.centroid,
            "owner": self.owner,
        }


class RegridTileService:
    """
    Fetches parcel geometries from Regrid Tileserver API.
    
    Uses MVT tiles which have 200k/month quota (vs 2k/month for records).
    Tiles contain: geometry, address, owner, parcelnumb, ll_uuid
    """
    
    # Optimal zoom level - balance between detail and tile count
    ZOOM_LEVEL = 15
    
    # Max tiles to fetch per request (avoid overwhelming the API)
    MAX_TILES = 100
    
    # Max concurrent tile requests
    MAX_CONCURRENT = 10
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        self.base_url = "https://tiles.regrid.com"
        self.token = settings.REGRID_TILESERVER_TOKEN or settings.REGRID_API_KEY
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)
        
    async def query_parcels_in_area(
        self,
        geometry: Dict[str, Any],
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
        limit: int = 500,
    ) -> List[DiscoveryParcel]:
        """
        Fetch parcels within the given geometry using Regrid tiles.
        
        Args:
            geometry: GeoJSON Polygon or MultiPolygon defining search area
            min_acres: Minimum parcel size (filtered client-side)
            max_acres: Maximum parcel size (filtered client-side)
            limit: Max parcels to return
            
        Returns:
            List of DiscoveryParcel with real geometries
        """
        if not self.token:
            logger.error("No REGRID_TILESERVER_TOKEN configured")
            return []
        
        try:
            search_shape = shape(geometry)
            bounds = search_shape.bounds  # (minx, miny, maxx, maxy)
            
            logger.info(f"Querying Regrid tiles for bounds: {bounds}")
            
            # Calculate tiles that cover the search area
            tiles = list(mercantile.tiles(
                bounds[0], bounds[1], bounds[2], bounds[3],
                zooms=self.ZOOM_LEVEL
            ))
            
            logger.info(f"Need {len(tiles)} tiles at zoom {self.ZOOM_LEVEL}")
            
            if len(tiles) > self.MAX_TILES:
                logger.warning(f"Too many tiles ({len(tiles)}), limiting to {self.MAX_TILES}")
                tiles = tiles[:self.MAX_TILES]
            
            # Fetch all tiles concurrently
            all_parcels: List[DiscoveryParcel] = []
            seen_ids: Set[str] = set()
            
            # Batch fetch tiles with progress logging
            logger.info(f"Fetching {len(tiles)} tiles (max {self.MAX_CONCURRENT} concurrent)...")
            
            tasks = [self._fetch_tile(tile, search_shape) for tile in tiles]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            tiles_with_data = 0
            tiles_empty = 0
            tiles_error = 0
            
            for result in results:
                if isinstance(result, Exception):
                    tiles_error += 1
                    continue
                
                if result:
                    tiles_with_data += 1
                else:
                    tiles_empty += 1
                    
                for parcel in result:
                    if parcel.id not in seen_ids:
                        seen_ids.add(parcel.id)
                        all_parcels.append(parcel)
            
            logger.info(f"Tiles: {tiles_with_data} with data, {tiles_empty} empty, {tiles_error} errors")
            logger.info(f"Found {len(all_parcels)} unique parcels")
            
            # Filter by acreage (client-side)
            filtered = self._filter_by_size(all_parcels, min_acres, max_acres)
            logger.info(f"After size filter ({min_acres}-{max_acres} acres): {len(filtered)} parcels")
            
            # Sort by acreage descending (largest first)
            filtered.sort(key=lambda p: p.acreage, reverse=True)
            
            return filtered[:limit]
            
        except Exception as e:
            logger.error(f"Error querying Regrid tiles: {e}", exc_info=True)
            return []
    
    async def _fetch_tile(
        self,
        tile: mercantile.Tile,
        search_shape: Polygon | MultiPolygon,
    ) -> List[DiscoveryParcel]:
        """Fetch and decode a single MVT tile"""
        async with self._semaphore:
            return await self._fetch_tile_internal(tile, search_shape)
    
    async def _fetch_tile_internal(
        self,
        tile: mercantile.Tile,
        search_shape: Polygon | MultiPolygon,
    ) -> List[DiscoveryParcel]:
        """Internal tile fetch with semaphore already acquired"""
        try:
            url = f"{self.base_url}/api/v1/parcels/{tile.z}/{tile.x}/{tile.y}.mvt"
            params = {"token": self.token}
            
            response = await self.client.get(url, params=params)
            
            if response.status_code == 204:
                # No content - tile has no parcels (coverage gap or empty area)
                # This is normal, not an error
                return []
            
            if response.status_code != 200:
                logger.debug(f"Tile {tile} returned {response.status_code}")
                return []
            
            if not response.content:
                return []
            
            # Decode MVT
            tile_data = mvt.decode(response.content)
            
            # Find parcels layer
            parcels_layer = tile_data.get('parcels', {})
            if not parcels_layer:
                # Try first layer if 'parcels' not found
                for name, data in tile_data.items():
                    parcels_layer = data
                    break
            
            features = parcels_layer.get('features', [])
            if not features:
                return []
            
            # Get tile bounds for coordinate conversion
            tile_bounds = mercantile.bounds(tile)
            
            # Parse features
            parcels = []
            for feature in features:
                parcel = self._parse_feature(feature, tile, tile_bounds, search_shape)
                if parcel:
                    parcels.append(parcel)
            
            logger.debug(f"Tile {tile}: {len(parcels)} parcels")
            return parcels
            
        except httpx.TimeoutException:
            logger.debug(f"Timeout fetching tile {tile}")
            return []
        except Exception as e:
            logger.debug(f"Error fetching tile {tile}: {type(e).__name__}: {e}")
            return []
    
    def _parse_feature(
        self,
        feature: Dict[str, Any],
        tile: mercantile.Tile,
        tile_bounds: mercantile.LngLatBbox,
        search_shape: Polygon | MultiPolygon,
    ) -> Optional[DiscoveryParcel]:
        """Parse an MVT feature into a DiscoveryParcel"""
        try:
            props = feature.get('properties', {})
            geom = feature.get('geometry')
            
            if not geom:
                return None
            
            geom_type = geom.get('type')
            if geom_type not in ['Polygon', 'MultiPolygon']:
                return None
            
            # Convert MVT tile coordinates to WGS84
            wgs84_geom = self._mvt_to_wgs84(geom, tile_bounds)
            if not wgs84_geom:
                return None
            
            # Check if parcel intersects search area
            try:
                parcel_shape = shape(wgs84_geom)
                if not parcel_shape.is_valid:
                    parcel_shape = parcel_shape.buffer(0)
                    
                if not search_shape.intersects(parcel_shape):
                    return None
            except Exception:
                return None
            
            # Calculate acreage from geometry
            acreage = self._calculate_acreage(parcel_shape)
            
            # Extract properties
            address = props.get('address', '') or ''
            owner = props.get('owner', '') or ''
            parcelnumb = props.get('parcelnumb', '') or ''
            ll_uuid = props.get('ll_uuid', '') or ''
            
            # Generate ID
            parcel_id = ll_uuid or parcelnumb or f"{hash(str(wgs84_geom))}"
            
            # Calculate centroid
            centroid = parcel_shape.centroid
            
            return DiscoveryParcel(
                id=parcel_id,
                address=address,
                acreage=round(acreage, 2),
                apn=parcelnumb,
                regrid_id=ll_uuid,
                geometry=wgs84_geom,
                centroid={"lat": centroid.y, "lng": centroid.x},
                owner=owner,
            )
            
        except Exception as e:
            logger.debug(f"Error parsing feature: {e}")
            return None
    
    def _mvt_to_wgs84(
        self,
        geom: Dict[str, Any],
        bounds: mercantile.LngLatBbox,
    ) -> Optional[Dict[str, Any]]:
        """Convert MVT tile coordinates to WGS84 lat/lng"""
        try:
            extent = 4096  # Standard MVT extent
            
            def convert_coord(coord: List[float]) -> List[float]:
                x, y = coord[0], coord[1]
                
                # Convert tile coords (0-4096) to 0-1 range
                px = x / extent
                py = y / extent
                
                # Convert to lng/lat
                lng = bounds.west + (bounds.east - bounds.west) * px
                # Y is inverted in MVT
                lat = bounds.north - (bounds.north - bounds.south) * py
                
                return [lng, lat]
            
            def convert_ring(ring: List[List[float]]) -> List[List[float]]:
                return [convert_coord(c) for c in ring]
            
            if geom['type'] == 'Polygon':
                new_coords = [convert_ring(ring) for ring in geom['coordinates']]
                return {'type': 'Polygon', 'coordinates': new_coords}
            
            elif geom['type'] == 'MultiPolygon':
                new_coords = [
                    [convert_ring(ring) for ring in polygon]
                    for polygon in geom['coordinates']
                ]
                return {'type': 'MultiPolygon', 'coordinates': new_coords}
            
            return None
            
        except Exception as e:
            logger.debug(f"Error converting coordinates: {e}")
            return None
    
    def _calculate_acreage(self, geom: Polygon | MultiPolygon) -> float:
        """Calculate area in acres using appropriate UTM projection"""
        try:
            centroid = geom.centroid
            
            # Determine UTM zone
            utm_zone = int((centroid.x + 180) / 6) + 1
            hemisphere = 'north' if centroid.y >= 0 else 'south'
            
            # Project to UTM for accurate area calculation
            wgs84 = pyproj.CRS('EPSG:4326')
            utm = pyproj.CRS(f'+proj=utm +zone={utm_zone} +{hemisphere} +ellps=WGS84')
            
            transformer = pyproj.Transformer.from_crs(wgs84, utm, always_xy=True)
            projected = transform(transformer.transform, geom)
            
            # Convert sq meters to acres (1 acre = 4046.86 sq meters)
            return projected.area / 4046.86
            
        except Exception:
            return 0.0
    
    def _filter_by_size(
        self,
        parcels: List[DiscoveryParcel],
        min_acres: Optional[float],
        max_acres: Optional[float],
    ) -> List[DiscoveryParcel]:
        """Filter parcels by acreage"""
        filtered = []
        for p in parcels:
            if min_acres is not None and p.acreage < min_acres:
                continue
            if max_acres is not None and p.acreage > max_acres:
                continue
            filtered.append(p)
        return filtered
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
_service: Optional[RegridTileService] = None


def get_parcel_discovery_service() -> RegridTileService:
    """Get or create the parcel discovery service singleton"""
    global _service
    if _service is None:
        _service = RegridTileService()
    return _service
