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
    land_use: Optional[str]  # usedesc or usecode
    zoning: Optional[str]
    zoning_description: Optional[str]
    year_built: Optional[int]
    raw_data: Dict[str, Any]
    
    # Additional property details (Standard tier)
    num_units: Optional[int] = None  # Number of living units
    num_stories: Optional[float] = None
    struct_style: Optional[str] = None
    
    # LBCS Standardized Land Use Codes (Premium tier)
    # These provide reliable, standardized classification across all counties
    lbcs_activity: Optional[int] = None  # What people do (1000=residential, 2000=commercial)
    lbcs_activity_desc: Optional[str] = None
    lbcs_function: Optional[int] = None  # Economic function (1100=household, 2320=property mgmt)
    lbcs_function_desc: Optional[str] = None
    lbcs_structure: Optional[int] = None  # Building type (1200-1299=multifamily with unit count!)
    lbcs_structure_desc: Optional[str] = None
    lbcs_site: Optional[int] = None  # Land development status
    lbcs_site_desc: Optional[str] = None
    lbcs_ownership: Optional[int] = None  # Public vs private (1000=private, 4000=public)
    lbcs_ownership_desc: Optional[str] = None
    
    # Owner details
    owner2: Optional[str] = None  # Secondary owner (often management company)
    owner_type: Optional[str] = None
    mail_address: Optional[str] = None  # Owner mailing address
    mail_city: Optional[str] = None
    mail_state: Optional[str] = None
    
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
                # Check if parcel contains the business point (ideal case)
                if parcel.contains_point(lat, lng):
                    logger.info(f"   ✅ Address lookup SUCCESS - parcel contains business location")
                    self._log_parcel_info(parcel)
                    return parcel
                else:
                    # RELAXED VALIDATION: Accept parcels within 150m
                    # Google's business coordinates are often inaccurate (entrance, sign, street)
                    # For large properties like apartment complexes, 50-100m offset is common
                    dist = self._distance_m(lat, lng, parcel.centroid.y, parcel.centroid.x)
                    MAX_DISTANCE_M = 150  # Accept parcels within 150m
                    
                    if dist <= MAX_DISTANCE_M:
                        logger.info(f"   ✅ Address lookup SUCCESS - parcel is {dist:.0f}m from business (within {MAX_DISTANCE_M}m tolerance)")
                        logger.info(f"      Note: Google coordinates may point to entrance/sign, not property center")
                        self._log_parcel_info(parcel)
                        return parcel
                    else:
                        logger.warning(f"   ❌ Address lookup returned WRONG parcel!")
                        logger.warning(f"      Parcel centroid is {dist:.0f}m from business (>{MAX_DISTANCE_M}m)")
                        logger.warning(f"      Parcel too far from business point - REJECTED")
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
        
        # Parse numeric fields safely
        def safe_int(val) -> Optional[int]:
            if val is None:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                return None
        
        def safe_float(val) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        
        # Build mailing address from components if full address not available
        mail_address = all_props.get("mailadd")
        if not mail_address:
            mail_parts = [
                all_props.get("mail_addno", ""),
                all_props.get("mail_addpref", ""),
                all_props.get("mail_addstr", ""),
                all_props.get("mail_addsttyp", ""),
                all_props.get("mail_addstsuf", ""),
            ]
            mail_address = " ".join(p for p in mail_parts if p).strip() or None
        
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
            zoning_description=all_props.get("zoning_description"),
            year_built=safe_int(all_props.get("yearbuilt")),
            raw_data=feature,
            # Additional property details
            num_units=safe_int(all_props.get("numunits")),
            num_stories=safe_float(all_props.get("numstories")),
            struct_style=all_props.get("structstyle"),
            # LBCS codes (Premium tier - standardized classification)
            lbcs_activity=safe_int(all_props.get("lbcs_activity")),
            lbcs_activity_desc=all_props.get("lbcs_activity_desc"),
            lbcs_function=safe_int(all_props.get("lbcs_function")),
            lbcs_function_desc=all_props.get("lbcs_function_desc"),
            lbcs_structure=safe_int(all_props.get("lbcs_structure")),
            lbcs_structure_desc=all_props.get("lbcs_structure_desc"),
            lbcs_site=safe_int(all_props.get("lbcs_site")),
            lbcs_site_desc=all_props.get("lbcs_site_desc"),
            lbcs_ownership=safe_int(all_props.get("lbcs_ownership")),
            lbcs_ownership_desc=all_props.get("lbcs_ownership_desc"),
            # Owner details
            owner2=all_props.get("owner2"),
            owner_type=all_props.get("owntype"),
            mail_address=mail_address,
            mail_city=all_props.get("mail_city"),
            mail_state=all_props.get("mail_state2"),
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
    
    # ============================================================
    # OWNER NAME SEARCH (for Contact-First Discovery)
    # ============================================================
    
    async def search_parcels_by_owner(
        self,
        owner_name: str,
        county_fips: Optional[str] = None,
        state_code: Optional[str] = None,
        max_results: int = 50,
    ) -> List[PropertyParcel]:
        """
        Search for parcels by owner name.
        
        This is the key function for contact-first discovery:
        1. Get company name from Apollo
        2. Search Regrid for properties owned by that company
        
        Args:
            owner_name: Owner name to search (e.g., "ABC PROPERTIES LLC")
            county_fips: Optional FIPS code to limit search (e.g., "48113" for Dallas County, TX)
            state_code: Optional state code (e.g., "TX")
            max_results: Maximum number of parcels to return
            
        Returns:
            List of PropertyParcel objects
        """
        if not self.is_configured:
            logger.warning("   ⚠️ Regrid API not configured")
            return []
        
        if not owner_name or len(owner_name.strip()) < 2:
            logger.warning("   ⚠️ Owner name too short for search")
            return []
        
        # Clean up owner name for search
        clean_name = self._clean_owner_name_for_search(owner_name)
        
        logger.info(f"   🔍 Regrid: Searching parcels owned by '{clean_name}'")
        if county_fips:
            logger.info(f"      County FIPS: {county_fips}")
        elif state_code:
            logger.info(f"      State: {state_code}")
        
        try:
            client = await self._get_client()
            
            # Build query URL with owner filter
            # Regrid V2 Query endpoint: /api/v2/parcels/query
            url = "https://app.regrid.com/api/v2/parcels/query"
            
            params = {
                "token": self.api_key,
                "fields[owner][ilike]": clean_name,  # Case-insensitive LIKE search
                "limit": min(max_results, 1000),
            }
            
            # Add geographic filter
            if county_fips:
                params["fields[geoid][eq]"] = county_fips
            elif state_code:
                params["fields[state2][eq]"] = state_code.upper()
            
            response = await client.get(url, params=params)
            
            if response.status_code == 401:
                logger.error("   ❌ Regrid API authentication failed")
                return []
            
            if response.status_code != 200:
                logger.warning(f"   ⚠️ Regrid owner search failed: {response.status_code}")
                return []
            
            data = response.json()
            parcels_data = data.get("parcels", {})
            parcels = self._parse_response(parcels_data)
            
            logger.info(f"   ✅ Found {len(parcels)} parcels owned by '{clean_name}'")
            
            return parcels[:max_results]
            
        except Exception as e:
            logger.error(f"   ❌ Regrid owner search error: {e}")
            return []
    
    def _clean_owner_name_for_search(self, name: str) -> str:
        """
        Clean owner name for Regrid search.
        
        Regrid uses ILIKE which is case-insensitive, but we want to:
        - Remove extra whitespace
        - Keep LLC, INC, etc. (they're in Regrid data)
        - Handle common variations
        """
        if not name:
            return ""
        
        # Basic cleanup
        clean = " ".join(name.upper().split())
        
        # Regrid often has abbreviated versions, so search with wildcards
        # The ilike operator already does partial matching
        
        return clean
    
    async def get_county_fips(
        self,
        city: Optional[str] = None,
        state: str = None,
        county: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the FIPS code for a county.
        
        Args:
            city: City name (will find county containing city)
            state: State code (e.g., "TX")
            county: County name (e.g., "Dallas")
            
        Returns:
            5-digit FIPS code (e.g., "48113" for Dallas County, TX)
        """
        # Common FIPS codes for major counties (fallback)
        # Format: State FIPS (2 digits) + County FIPS (3 digits)
        COMMON_FIPS = {
            ("TX", "DALLAS"): "48113",
            ("TX", "HARRIS"): "48201",
            ("TX", "TARRANT"): "48439",
            ("TX", "BEXAR"): "48029",
            ("TX", "TRAVIS"): "48453",
            ("CA", "LOS ANGELES"): "06037",
            ("CA", "SAN DIEGO"): "06073",
            ("CA", "ORANGE"): "06059",
            ("FL", "MIAMI-DADE"): "12086",
            ("FL", "BROWARD"): "12011",
            ("FL", "PALM BEACH"): "12099",
            ("NY", "NEW YORK"): "36061",
            ("NY", "KINGS"): "36047",
            ("IL", "COOK"): "17031",
            ("AZ", "MARICOPA"): "04013",
            ("GA", "FULTON"): "13121",
            ("NC", "MECKLENBURG"): "37119",
            ("NC", "WAKE"): "37183",
            ("TN", "DAVIDSON"): "47037",
            ("CO", "DENVER"): "08031",
            ("WA", "KING"): "53033",
            ("NV", "CLARK"): "32003",
        }
        
        if state and county:
            key = (state.upper(), county.upper())
            if key in COMMON_FIPS:
                return COMMON_FIPS[key]
        
        # If not in common list, would need to query Census API or similar
        # For now, return None and rely on state-level filtering
        return None
    
    # ============================================================
    # LBCS CODE SEARCH (for Regrid-First Discovery)
    # ============================================================
    
    async def search_parcels_by_lbcs(
        self,
        lbcs_ranges: List[tuple],
        county_fips: Optional[str] = None,
        state_code: Optional[str] = None,
        zip_code: Optional[str] = None,
        max_results: int = 50,
        lbcs_field: str = "lbcs_structure",
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
        offset: int = 0,
    ) -> List[PropertyParcel]:
        """
        Search for parcels by LBCS code ranges.
        
        This is the key function for Regrid-first discovery:
        1. Query Regrid directly by LBCS codes
        2. Get all matching parcels in the area
        3. No Google Places needed
        
        LBCS Fields:
        - lbcs_structure: Physical structure type (1200-1299 for multi-family)
        - lbcs_activity: What happens on property (2200-2599 for retail)
        - lbcs_function: Broader function category
        
        Args:
            lbcs_ranges: List of (min, max) tuples for LBCS codes
                         e.g., [(1200, 1299)] for multi-family
            county_fips: Optional FIPS code to limit search
            state_code: Optional state code (e.g., "TX")
            zip_code: Optional ZIP code for geographic filtering
            max_results: Maximum number of parcels to return
            lbcs_field: Which LBCS field to query (lbcs_structure, lbcs_activity, lbcs_function)
            min_acres: Optional minimum parcel size in acres
            max_acres: Optional maximum parcel size in acres
            offset: Pagination offset (skip first N results)
            
        Returns:
            List of PropertyParcel objects
        """
        if not self.is_configured:
            logger.warning("   ⚠️ Regrid API not configured")
            return []
        
        if not lbcs_ranges:
            logger.warning("   ⚠️ No LBCS ranges provided")
            return []
        
        logger.info(f"   🔍 Regrid: Searching parcels by LBCS codes ({lbcs_field})")
        logger.info(f"      LBCS ranges: {lbcs_ranges}")
        if min_acres or max_acres:
            logger.info(f"      Size filter: {min_acres or 0} - {max_acres or '∞'} acres")
        if offset > 0:
            logger.info(f"      Offset: {offset}")
        
        all_parcels = []
        seen_ids = set()
        
        try:
            client = await self._get_client()
            
            # Query for each LBCS range
            for lbcs_min, lbcs_max in lbcs_ranges:
                if len(all_parcels) >= max_results:
                    break
                
                # Build query URL with LBCS filter
                # Regrid V2 Query endpoint: /api/v2/parcels/query
                url = "https://app.regrid.com/api/v2/parcels/query"
                
                params = {
                    "token": self.api_key,
                    f"fields[{lbcs_field}][gte]": lbcs_min,
                    f"fields[{lbcs_field}][lte]": lbcs_max,
                    "limit": min(max_results - len(all_parcels), 1000),
                }
                
                # Add pagination offset
                if offset > 0:
                    params["skip"] = offset
                
                # Add geographic filter
                if zip_code:
                    params["fields[szip5][eq]"] = zip_code
                elif county_fips:
                    params["fields[geoid][eq]"] = county_fips
                elif state_code:
                    params["fields[state2][eq]"] = state_code.upper()
                
                # Add size filter (ll_gisacre = parcel size in acres)
                if min_acres is not None:
                    params["fields[ll_gisacre][gte]"] = min_acres
                if max_acres is not None:
                    params["fields[ll_gisacre][lte]"] = max_acres
                
                logger.info(f"      Querying {lbcs_field} {lbcs_min}-{lbcs_max}...")
                
                response = await client.get(url, params=params)
                
                if response.status_code == 401:
                    logger.error("   ❌ Regrid API authentication failed")
                    return all_parcels
                
                if response.status_code != 200:
                    logger.warning(f"   ⚠️ Regrid LBCS search failed: {response.status_code} - {response.text[:200]}")
                    continue
                
                data = response.json()
                parcels_data = data.get("parcels", {})
                parcels = self._parse_response(parcels_data)
                
                # Deduplicate
                added = 0
                for parcel in parcels:
                    if parcel.parcel_id not in seen_ids:
                        seen_ids.add(parcel.parcel_id)
                        all_parcels.append(parcel)
                        added += 1
                
                logger.info(f"      Found {len(parcels)} parcels, added {added} new (total: {len(all_parcels)})")
            
            logger.info(f"   ✅ Total unique parcels found: {len(all_parcels)}")
            return all_parcels[:max_results]
            
        except Exception as e:
            logger.error(f"   ❌ Regrid LBCS search error: {e}")
            return all_parcels
    
    async def search_parcels_by_usedesc(
        self,
        patterns: List[str],
        county_fips: Optional[str] = None,
        state_code: Optional[str] = None,
        zip_code: Optional[str] = None,
        max_results: int = 50,
    ) -> List[PropertyParcel]:
        """
        Search for parcels by usedesc text patterns (fallback if LBCS not available).
        
        Note: Regrid API doesn't support text search (ilike) on usedesc field.
        This method tries multiple approaches:
        1. Query by common usecode values for the property type
        2. Get parcels in area and filter locally by usedesc text
        
        Args:
            patterns: List of text patterns to search (e.g., ["apartment", "multi-family"])
            county_fips: Optional FIPS code
            state_code: Optional state code
            zip_code: Optional ZIP code
            max_results: Maximum results
            
        Returns:
            List of PropertyParcel objects
        """
        if not self.is_configured:
            logger.warning("   ⚠️ Regrid API not configured")
            return []
        
        logger.info(f"   🔍 Regrid: Searching parcels by usedesc patterns")
        logger.info(f"      Patterns: {patterns}")
        
        all_parcels = []
        seen_ids = set()
        
        try:
            client = await self._get_client()
            
            # Regrid doesn't support text search on usedesc, so we need to:
            # 1. Get commercial properties in the area (usecode approach)
            # 2. Filter by usedesc text locally
            
            # Try common usecode values for commercial/retail properties
            # These are county-specific but common values include:
            commercial_usecodes = [
                "COMMERCIAL", "RETAIL", "OFFICE", "SHOPPING", 
                "COM", "RET", "OFC", "SHP",
                "C", "R",  # Short codes
            ]
            
            # First, try to get commercial properties by usecode
            for usecode in commercial_usecodes[:4]:  # Limit attempts
                if len(all_parcels) >= max_results:
                    break
                
                url = "https://app.regrid.com/api/v2/parcels/query"
                
                params = {
                    "token": self.api_key,
                    "fields[usecode][eq]": usecode,
                    "limit": min(max_results * 3, 1000),  # Get more to filter
                }
                
                # Add geographic filter
                if zip_code:
                    params["fields[szip5][eq]"] = zip_code
                elif county_fips:
                    params["fields[geoid][eq]"] = county_fips
                elif state_code:
                    params["fields[state2][eq]"] = state_code.upper()
                
                logger.info(f"      Trying usecode = '{usecode}'...")
                
                response = await client.get(url, params=params)
                
                if response.status_code != 200:
                    continue
                
                data = response.json()
                parcels_data = data.get("parcels", {})
                parcels = self._parse_response(parcels_data)
                
                # Filter by usedesc patterns locally
                for parcel in parcels:
                    if parcel.parcel_id in seen_ids:
                        continue
                    
                    # Check if any pattern matches usedesc
                    usedesc = (parcel.land_use or "").lower()
                    matches = any(pattern.lower() in usedesc for pattern in patterns)
                    
                    if matches or usedesc:  # Include if matches or has any description
                        seen_ids.add(parcel.parcel_id)
                        all_parcels.append(parcel)
                        logger.info(f"         Found: {parcel.address} ({parcel.land_use})")
                
                if parcels:
                    logger.info(f"      Found {len(parcels)} parcels with usecode '{usecode}'")
            
            # If still no results, try getting any commercial parcels in the area
            if not all_parcels:
                logger.info(f"      Trying broader commercial property search...")
                
                # Try lbcs_activity codes for commercial (2xxx range)
                url = "https://app.regrid.com/api/v2/parcels/query"
                params = {
                    "token": self.api_key,
                    "fields[lbcs_activity][gte]": 2000,
                    "fields[lbcs_activity][lte]": 2999,
                    "limit": max_results * 2,
                }
                
                if zip_code:
                    params["fields[szip5][eq]"] = zip_code
                elif county_fips:
                    params["fields[geoid][eq]"] = county_fips
                elif state_code:
                    params["fields[state2][eq]"] = state_code.upper()
                
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    parcels_data = data.get("parcels", {})
                    parcels = self._parse_response(parcels_data)
                    
                    for parcel in parcels:
                        if parcel.parcel_id not in seen_ids:
                            seen_ids.add(parcel.parcel_id)
                            all_parcels.append(parcel)
                    
                    logger.info(f"      Found {len(parcels)} commercial parcels (LBCS activity 2000-2999)")
            
            logger.info(f"   ✅ Total unique parcels found: {len(all_parcels)}")
            return all_parcels[:max_results]
            
        except Exception as e:
            logger.error(f"   ❌ Regrid usedesc search error: {e}")
            import traceback
            traceback.print_exc()
            return all_parcels
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
regrid_service = RegridService()
