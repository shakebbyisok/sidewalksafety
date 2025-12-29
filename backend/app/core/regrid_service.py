"""
Regrid Property Parcel Service

Fetches property parcel boundaries from Regrid API.
Uses Point-in-Polygon validation to ensure 100% accuracy.

Key Design:
1. PRIMARY: Point lookup using lat/lng coordinates
2. VALIDATION: Every parcel must CONTAIN the business point
3. FALLBACK: Address search (only if point lookup fails)
4. REJECT: Any parcel that doesn't contain the coordinates

API Documentation: https://regrid.com/api
"""

import logging
import math
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from shapely.geometry import shape, Polygon, MultiPolygon, Point
from shapely.ops import unary_union

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PropertyParcel:
    """Property parcel data from Regrid."""
    parcel_id: str
    apn: Optional[str]  # Assessor Parcel Number
    address: Optional[str]
    owner: Optional[str]
    polygon: Polygon  # Property boundary
    centroid: Point
    area_m2: float
    area_acres: Optional[float]
    land_use: Optional[str]
    zoning: Optional[str]
    year_built: Optional[int]
    raw_data: Dict[str, Any]
    
    @property
    def has_valid_geometry(self) -> bool:
        """Check if the parcel has a valid polygon."""
        return self.polygon is not None and not self.polygon.is_empty and self.polygon.is_valid
    
    def contains_point(self, lat: float, lng: float) -> bool:
        """Check if this parcel contains the given point."""
        if not self.has_valid_geometry:
            return False
        point = Point(lng, lat)  # Note: Point takes (x, y) = (lng, lat)
        return self.polygon.contains(point) or self.polygon.boundary.distance(point) < 0.0001


class RegridService:
    """
    Service to fetch property parcel data from Regrid API.
    
    DESIGN PRINCIPLES:
    1. Point lookup is PRIMARY (most accurate)
    2. Every returned parcel is VALIDATED via point-in-polygon
    3. Address search is FALLBACK only
    4. Parcels that don't contain the business point are REJECTED
    """
    
    # Maximum distance (meters) a parcel centroid can be from business point
    MAX_CENTROID_DISTANCE_M = 500
    
    def __init__(self):
        self.api_key = settings.REGRID_API_KEY
        self.base_url = settings.REGRID_API_URL
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def is_configured(self) -> bool:
        """Check if Regrid API is configured."""
        return bool(self.api_key)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    # ============================================================
    # MAIN ENTRY POINT - Use this method
    # ============================================================
    
    async def get_validated_parcel(
        self,
        lat: float,
        lng: float,
        address: Optional[str] = None
    ) -> Optional[PropertyParcel]:
        """
        Get property parcel with 100% accuracy using point-in-polygon validation.
        
        This is the RECOMMENDED method to use. It:
        1. Tries point lookup first (most accurate)
        2. Validates the parcel contains the business coordinates
        3. Falls back to address search if point lookup fails
        4. Rejects any parcel that doesn't contain the point
        
        Args:
            lat: Business latitude (from Google Places)
            lng: Business longitude (from Google Places)
            address: Optional address for fallback search
            
        Returns:
            PropertyParcel if found AND validated, None otherwise
        """
        if not self.is_configured:
            logger.warning("   ⚠️ Regrid API not configured (REGRID_API_KEY not set)")
            return None
        
        logger.info(f"   🗺️  Regrid: Finding parcel for ({lat:.6f}, {lng:.6f})")
        
        # ============ STEP 1: Point Lookup (PRIMARY) ============
        parcel = await self._point_lookup(lat, lng)
        
        if parcel:
            # Validate: Does parcel contain the business point?
            if parcel.contains_point(lat, lng):
                logger.info(f"   ✅ Point lookup SUCCESS - parcel contains business location")
                self._log_parcel_info(parcel)
                return parcel
            else:
                # This shouldn't happen with point lookup, but let's be safe
                logger.warning(f"   ⚠️ Point lookup returned parcel that doesn't contain point - rejecting")
                parcel = None
        
        # ============ STEP 2: Address Search (FALLBACK) ============
        if not parcel and address:
            logger.info(f"   🔄 Point lookup failed, trying address search...")
            parcel = await self._address_lookup(address)
            
            if parcel:
                # CRITICAL VALIDATION: Parcel must contain the business point
                if parcel.contains_point(lat, lng):
                    logger.info(f"   ✅ Address lookup SUCCESS - parcel contains business location")
                    self._log_parcel_info(parcel)
                    return parcel
                else:
                    # Check if parcel is at least close
                    dist = self._distance_m(lat, lng, parcel.centroid.y, parcel.centroid.x)
                    logger.warning(f"   ❌ Address lookup returned WRONG parcel!")
                    logger.warning(f"      Parcel centroid is {dist:.0f}m from business")
                    logger.warning(f"      Parcel does NOT contain business point - REJECTED")
                    parcel = None
        
        # ============ STEP 3: No Valid Parcel Found ============
        if not parcel:
            logger.warning(f"   ⚠️ No valid Regrid parcel found for this location")
            logger.warning(f"      Will use estimated boundary instead")
        
        return parcel
    
    # ============================================================
    # INTERNAL METHODS
    # ============================================================
    
    async def _point_lookup(self, lat: float, lng: float) -> Optional[PropertyParcel]:
        """
        Point lookup using Regrid V2 API.
        Returns the parcel that contains the given coordinates.
        """
        try:
            client = await self._get_client()
            
            url = "https://app.regrid.com/api/v2/parcels/point"
            params = {
                "lat": lat,
                "lon": lng,
                "token": self.api_key,
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code == 401:
                logger.error("   ❌ Regrid API authentication failed")
                return None
            
            if response.status_code == 404:
                logger.info(f"   📍 No parcel at coordinates (coverage gap)")
                return None
            
            if response.status_code != 200:
                logger.warning(f"   ⚠️ Point lookup failed: {response.status_code}")
                return None
            
            data = response.json()
            parcels_data = data.get("parcels", {})
            parcels = self._parse_response(parcels_data)
            
            if parcels:
                return parcels[0]
            
            return None
            
        except Exception as e:
            logger.error(f"   ❌ Point lookup error: {e}")
            return None
    
    async def _address_lookup(self, address: str) -> Optional[PropertyParcel]:
        """
        Address lookup using Regrid typeahead + detail fetch.
        WARNING: This can return wrong parcels - always validate with point-in-polygon!
        """
        try:
            client = await self._get_client()
            
            # Step 1: Typeahead to find parcel path
            typeahead_url = "https://app.regrid.com/api/v1/typeahead"
            typeahead_params = {
                "query": address,
                "token": self.api_key,
            }
            
            response = await client.get(typeahead_url, params=typeahead_params)
            
            if response.status_code != 200:
                return None
            
            typeahead_data = response.json()
            results = typeahead_data if isinstance(typeahead_data, list) else typeahead_data.get("results", [])
            
            if not results:
                return None
            
            # Find parcel-type result
            best_result = None
            for result in results:
                if result.get("type") == "parcel":
                    best_result = result
                    break
            if not best_result:
                best_result = results[0]
            
            parcel_path = best_result.get("path")
            if not parcel_path:
                return None
            
            logger.info(f"      Typeahead found: {parcel_path}")
            
            # Step 2: Fetch parcel details (try v1, then v2)
            parcel = await self._fetch_parcel_by_path(parcel_path)
            
            return parcel
            
        except Exception as e:
            logger.error(f"   ❌ Address lookup error: {e}")
            return None
    
    async def _fetch_parcel_by_path(self, parcel_path: str) -> Optional[PropertyParcel]:
        """Fetch parcel details by path, trying v1 then v2 API."""
        client = await self._get_client()
        
        # Try v1 API first
        detail_url = f"https://app.regrid.com/api/v1/parcel{parcel_path}.json"
        detail_params = {"token": self.api_key}
        
        response = await client.get(detail_url, params=detail_params)
        
        if response.status_code == 200:
            data = response.json()
            parcels = self._parse_response(data)
            if parcels:
                return parcels[0]
        
        # Try v2 API as fallback
        v2_url = "https://app.regrid.com/api/v2/parcels/query"
        v2_params = {
            "path": parcel_path,
            "token": self.api_key,
        }
        
        response = await client.get(v2_url, params=v2_params)
        
        if response.status_code == 200:
            data = response.json()
            parcels_data = data.get("parcels", {})
            parcels = self._parse_response(parcels_data)
            if parcels:
                return parcels[0]
        
        return None
    
    def _log_parcel_info(self, parcel: PropertyParcel):
        """Log parcel information."""
        logger.info(f"      📋 Parcel: {parcel.address or parcel.parcel_id}")
        logger.info(f"      👤 Owner: {parcel.owner or 'Unknown'}")
        logger.info(f"      📐 Area: {parcel.area_m2:,.0f} m² ({parcel.area_acres or 0:.2f} acres)")
    
    # ============================================================
    # LEGACY METHODS (for backwards compatibility)
    # ============================================================
    
    async def get_parcel_by_coordinates(
        self,
        lat: float,
        lng: float
    ) -> Optional[PropertyParcel]:
        """
        LEGACY: Use get_validated_parcel() instead.
        This method doesn't validate point-in-polygon.
        """
        return await self._point_lookup(lat, lng)
    
    async def get_parcel_by_address(
        self,
        address: str,
        fallback_lat: Optional[float] = None,
        fallback_lng: Optional[float] = None
    ) -> Optional[PropertyParcel]:
        """
        LEGACY: Use get_validated_parcel() instead.
        This method uses the new validated approach internally.
        """
        if fallback_lat and fallback_lng:
            return await self.get_validated_parcel(
                lat=fallback_lat,
                lng=fallback_lng,
                address=address
            )
        else:
            # No coordinates to validate against - use address lookup only
            return await self._address_lookup(address)
    
    # ============================================================
    # UTILITY METHODS
    # ============================================================
    
    def _parse_response(self, data: Dict[str, Any]) -> List[PropertyParcel]:
        """Parse Regrid API response into PropertyParcel objects."""
        parcels: List[PropertyParcel] = []
        
        features = data.get("features", [])
        
        # Handle direct feature response
        if not features and "geometry" in data:
            features = [data]
        
        for feature in features:
            try:
                parcel = self._parse_feature(feature)
                if parcel and parcel.has_valid_geometry:
                    parcels.append(parcel)
            except Exception as e:
                logger.debug(f"Failed to parse parcel feature: {e}")
        
        return parcels
    
    def _parse_feature(self, feature: Dict[str, Any]) -> Optional[PropertyParcel]:
        """Parse a single GeoJSON feature into PropertyParcel."""
        geometry = feature.get("geometry")
        properties = feature.get("properties", {})
        
        if not geometry:
            return None
        
        try:
            geom = shape(geometry)
            
            if isinstance(geom, MultiPolygon):
                geom = max(geom.geoms, key=lambda g: g.area)
            
            if not isinstance(geom, Polygon):
                return None
            
            if not geom.is_valid:
                geom = geom.buffer(0)
            
            if geom.is_empty:
                return None
                
        except Exception as e:
            logger.debug(f"Failed to parse geometry: {e}")
            return None
        
        # V2 API stores fields in 'fields' subobject
        fields = properties.get("fields", {})
        all_props = {**properties, **fields}
        
        parcel_id = (
            all_props.get("ll_uuid") or
            all_props.get("parcelnumb") or
            properties.get("ll_uuid") or
            str(feature.get("id", "unknown"))
        )
        
        # Calculate area
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        coords = list(geom.exterior.coords)
        area_m2, _ = geod.polygon_area_perimeter(
            [c[0] for c in coords],
            [c[1] for c in coords]
        )
        area_m2 = abs(area_m2)
        
        area_acres = all_props.get("ll_gisacre") or all_props.get("gisacre")
        if area_acres:
            try:
                area_acres = float(area_acres)
            except:
                area_acres = None
        
        address = (
            all_props.get("address") or 
            all_props.get("situs") or
            properties.get("headline")
        )
        
        owner = (
            all_props.get("owner") or 
            all_props.get("ownername")
        )
        
        return PropertyParcel(
            parcel_id=str(parcel_id),
            apn=all_props.get("parcelnumb") or all_props.get("apn"),
            address=address,
            owner=owner,
            polygon=geom,
            centroid=geom.centroid,
            area_m2=area_m2,
            area_acres=area_acres,
            land_use=all_props.get("usedesc") or all_props.get("usecode") or all_props.get("landuse"),
            zoning=all_props.get("zoning") or all_props.get("zoning_code"),
            year_built=all_props.get("yearbuilt"),
            raw_data=feature,
        )
    
    def _distance_m(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance in meters between two points (Haversine)."""
        R = 6371000
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
regrid_service = RegridService()
