"""
Unified Search Service

Handles all property search types:
1. Draw polygon - Spatial query within drawn area
2. Pin drop - Single parcel lookup (already exists)
3. ZIP code - Parcels within ZIP + filters
4. Natural language - Claude parses → structured query
5. System category - LBCS code filtering
6. Brand search - Google Places API

Key Design:
- All searches return a unified SearchResult format
- Supports preview (count only) before full search
- Stores search sessions for history/discovery
"""

import logging
from typing import Optional, List, Dict, Any, Literal
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

from shapely.geometry import shape, mapping, Polygon, MultiPolygon, Point, box
from shapely.ops import unary_union

from app.core.regrid_service import RegridService, PropertyParcel

logger = logging.getLogger(__name__)


class SearchType(str, Enum):
    """Available search types."""
    PIN = "pin"
    POLYGON = "polygon"
    ZIP = "zip"
    COUNTY = "county"
    NLP = "nlp"
    CATEGORY = "category"
    BRAND = "brand"


# LBCS-based property categories
# Using broader ranges because LBCS data coverage varies by county
# lbcs_activity is the primary field we query
# We also provide keyword fallbacks for usedesc/land_use fields
PROPERTY_CATEGORIES = {
    "parking": {
        "label": "Parking Lots",
        "lbcs_codes": [(4150, 4160)],  # 4150=Surface parking, 4160=Parking structure
        "keywords": ["parking", "park lot", "surface lot"],  # Fallback keywords for usedesc
        "description": "Surface and structured parking facilities",
        "icon": "square-parking",
    },
    "gas_station": {
        "label": "Gas Stations",
        "lbcs_codes": [(2523, 2523), (4170, 4170)],  # 2523=Gas station/service, 4170=Service station
        "keywords": ["gas", "fuel", "service station", "filling"],
        "description": "Fuel stations and auto service",
        "icon": "fuel",
    },
    "retail": {
        "label": "Retail",
        "lbcs_codes": [(2100, 2199)],  # Shopping/retail
        "keywords": ["retail", "store", "shop", "mall", "commercial"],
        "description": "Shopping centers, stores, malls",
        "icon": "store",
    },
    "restaurant": {
        "label": "Restaurants",
        # Broader range: 2500-2599 covers all food/beverage establishments
        # 2510=restaurants, 2520=bars, 2530=fast food, 2540=ice cream, 2550=catering
        "lbcs_codes": [(2500, 2599)],
        "keywords": ["restaurant", "food", "dining", "eating", "cafe", "diner", "bar", "tavern", "fast food"],
        "description": "Restaurants, fast food, cafes, bars",
        "icon": "utensils",
    },
    "industrial": {
        "label": "Industrial",
        "lbcs_codes": [(3000, 3999)],  # All industrial/manufacturing
        "keywords": ["industrial", "warehouse", "manufacturing", "factory", "distribution"],
        "description": "Warehouses, manufacturing, distribution",
        "icon": "factory",
    },
    "vacant": {
        "label": "Vacant Land",
        "lbcs_codes": [(9000, 9999)],  # All undeveloped
        "keywords": ["vacant", "undeveloped", "empty lot", "raw land"],
        "description": "Undeveloped or unused parcels",
        "icon": "trees",
    },
    "office": {
        "label": "Office",
        "lbcs_codes": [(2200, 2299)],  # Office buildings
        "keywords": ["office", "professional", "business park"],
        "description": "Office buildings and business parks",
        "icon": "building-2",
    },
    "multifamily": {
        "label": "Multi-Family",
        "lbcs_codes": [(1200, 1299)],  # Multi-family residential
        "keywords": ["apartment", "multi-family", "multifamily", "condo", "townhouse"],
        "description": "Apartment complexes, condos",
        "icon": "building",
    },
}


@dataclass
class SearchFilters:
    """Filters that can be applied to any search."""
    category_id: Optional[str] = None  # Property category from PROPERTY_CATEGORIES
    lbcs_codes: Optional[List[tuple]] = None  # Direct LBCS code ranges
    min_acres: Optional[float] = None
    max_acres: Optional[float] = None
    owner_contains: Optional[str] = None
    year_built_min: Optional[int] = None
    year_built_max: Optional[int] = None


@dataclass
class SearchQuery:
    """Structured search query."""
    search_type: SearchType
    
    # Geography (one of these, depending on search_type)
    polygon_geojson: Optional[Dict] = None  # GeoJSON polygon
    point: Optional[Dict] = None  # {"lat": float, "lng": float}
    zip_code: Optional[str] = None
    county_fips: Optional[str] = None
    state_code: Optional[str] = None
    viewport: Optional[Dict] = None  # {"minLat", "maxLat", "minLng", "maxLng"}
    
    # For NLP
    raw_query: Optional[str] = None
    
    # For brand search
    brand_name: Optional[str] = None
    
    # Filters
    filters: SearchFilters = field(default_factory=SearchFilters)
    
    # Pagination - Regrid supports up to 1000 per request
    limit: int = 1000
    offset: int = 0


@dataclass
class SearchResultParcel:
    """A single parcel in search results."""
    parcel_id: str
    address: Optional[str]
    owner: Optional[str]
    lat: float
    lng: float
    area_acres: Optional[float]
    area_sqft: Optional[float]
    land_use: Optional[str]
    zoning: Optional[str]
    year_built: Optional[int]
    polygon_geojson: Optional[Dict]
    lbcs_activity: Optional[int] = None
    lbcs_activity_desc: Optional[str] = None
    
    # For brand search results
    brand_name: Optional[str] = None
    place_id: Optional[str] = None


@dataclass
class SearchResult:
    """Result of a search operation."""
    success: bool
    search_type: SearchType
    query: SearchQuery
    total_count: int
    parcels: List[SearchResultParcel]
    error: Optional[str] = None
    preview_only: bool = False  # True if this was just a count preview
    search_session_id: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)


class SearchService:
    """
    Unified search service for all property search types.
    """
    
    def __init__(self):
        self.regrid = RegridService()
    
    async def search(
        self,
        query: SearchQuery,
        preview_only: bool = False,
    ) -> SearchResult:
        """
        Execute a search based on the query type.
        
        Args:
            query: Structured search query
            preview_only: If True, only return count (faster, cheaper)
            
        Returns:
            SearchResult with parcels or count
        """
        logger.info(f"🔍 Search: type={query.search_type}, preview={preview_only}")
        
        try:
            if query.search_type == SearchType.PIN:
                return await self._search_pin(query, preview_only)
            elif query.search_type == SearchType.POLYGON:
                return await self._search_polygon(query, preview_only)
            elif query.search_type == SearchType.ZIP:
                return await self._search_zip(query, preview_only)
            elif query.search_type == SearchType.CATEGORY:
                return await self._search_category(query, preview_only)
            elif query.search_type == SearchType.BRAND:
                return await self._search_brand(query, preview_only)
            elif query.search_type == SearchType.NLP:
                # NLP should be parsed first by NLPSearchService
                return SearchResult(
                    success=False,
                    search_type=query.search_type,
                    query=query,
                    total_count=0,
                    parcels=[],
                    error="NLP queries must be parsed first",
                )
            else:
                return SearchResult(
                    success=False,
                    search_type=query.search_type,
                    query=query,
                    total_count=0,
                    parcels=[],
                    error=f"Unknown search type: {query.search_type}",
                )
        except Exception as e:
            logger.error(f"Search error: {e}")
            import traceback
            traceback.print_exc()
            return SearchResult(
                success=False,
                search_type=query.search_type,
                query=query,
                total_count=0,
                parcels=[],
                error=str(e),
            )
    
    async def _search_pin(
        self,
        query: SearchQuery,
        preview_only: bool,
    ) -> SearchResult:
        """Search by pin drop - single parcel lookup."""
        if not query.point:
            return SearchResult(
                success=False,
                search_type=SearchType.PIN,
                query=query,
                total_count=0,
                parcels=[],
                error="Point coordinates required",
            )
        
        lat = query.point["lat"]
        lng = query.point["lng"]
        
        parcel = await self.regrid.get_validated_parcel(lat, lng)
        
        if not parcel:
            return SearchResult(
                success=True,
                search_type=SearchType.PIN,
                query=query,
                total_count=0,
                parcels=[],
                preview_only=preview_only,
            )
        
        result_parcel = self._parcel_to_result(parcel)
        
        return SearchResult(
            success=True,
            search_type=SearchType.PIN,
            query=query,
            total_count=1,
            parcels=[result_parcel] if not preview_only else [],
            preview_only=preview_only,
        )
    
    async def _search_polygon(
        self,
        query: SearchQuery,
        preview_only: bool,
    ) -> SearchResult:
        """Search by drawn polygon - spatial query."""
        if not query.polygon_geojson:
            return SearchResult(
                success=False,
                search_type=SearchType.POLYGON,
                query=query,
                total_count=0,
                parcels=[],
                error="Polygon GeoJSON required",
            )
        
        # Get LBCS codes from category or filters
        lbcs_ranges = self._get_lbcs_ranges(query.filters)
        print(f"Polygon search - category_id: {query.filters.category_id}, lbcs_ranges: {lbcs_ranges}, min_acres: {query.filters.min_acres}")
        
        # Require category filter to avoid returning too many parcels
        if not lbcs_ranges and not query.filters.min_acres:
            return SearchResult(
                success=False,
                search_type=SearchType.POLYGON,
                query=query,
                total_count=0,
                parcels=[],
                error="Polygon search requires a property type or size filter. Select a category first.",
            )
        
        # Query Regrid with spatial filter
        parcels = await self._query_regrid_spatial(
            polygon_geojson=query.polygon_geojson,
            lbcs_ranges=lbcs_ranges,
            min_acres=query.filters.min_acres,
            max_acres=query.filters.max_acres,
            limit=query.limit,
            offset=query.offset,
        )
        
        result_parcels = [self._parcel_to_result(p) for p in parcels]
        
        return SearchResult(
            success=True,
            search_type=SearchType.POLYGON,
            query=query,
            total_count=len(result_parcels),
            parcels=result_parcels if not preview_only else [],
            preview_only=preview_only,
        )
    
    async def _search_zip(
        self,
        query: SearchQuery,
        preview_only: bool,
    ) -> SearchResult:
        """Search by ZIP code - requires filters."""
        if not query.zip_code:
            return SearchResult(
                success=False,
                search_type=SearchType.ZIP,
                query=query,
                total_count=0,
                parcels=[],
                error="ZIP code required",
            )
        
        # Get LBCS codes from category or filters
        lbcs_ranges = self._get_lbcs_ranges(query.filters)
        
        if not lbcs_ranges and not query.filters.min_acres:
            # No filters - would return too many results
            return SearchResult(
                success=False,
                search_type=SearchType.ZIP,
                query=query,
                total_count=0,
                parcels=[],
                error="ZIP search requires category or size filter to narrow results",
            )
        
        # Query Regrid by ZIP with filters
        parcels = await self.regrid.search_parcels_by_lbcs(
            lbcs_ranges=lbcs_ranges or [(1000, 9999)],  # All if no category
            zip_code=query.zip_code,
            max_results=query.limit,
            min_acres=query.filters.min_acres,
            max_acres=query.filters.max_acres,
            offset=query.offset,
        )
        
        result_parcels = [self._parcel_to_result(p) for p in parcels]
        
        return SearchResult(
            success=True,
            search_type=SearchType.ZIP,
            query=query,
            total_count=len(result_parcels),
            parcels=result_parcels if not preview_only else [],
            preview_only=preview_only,
        )
    
    async def _search_category(
        self,
        query: SearchQuery,
        preview_only: bool,
    ) -> SearchResult:
        """Search by system category (LBCS codes)."""
        if not query.filters.category_id:
            return SearchResult(
                success=False,
                search_type=SearchType.CATEGORY,
                query=query,
                total_count=0,
                parcels=[],
                error="Category ID required",
            )
        
        category = PROPERTY_CATEGORIES.get(query.filters.category_id)
        if not category:
            return SearchResult(
                success=False,
                search_type=SearchType.CATEGORY,
                query=query,
                total_count=0,
                parcels=[],
                error=f"Unknown category: {query.filters.category_id}",
            )
        
        lbcs_ranges = category["lbcs_codes"]
        
        # Determine geographic scope
        if query.polygon_geojson:
            parcels = await self._query_regrid_spatial(
                polygon_geojson=query.polygon_geojson,
                lbcs_ranges=lbcs_ranges,
                min_acres=query.filters.min_acres,
                max_acres=query.filters.max_acres,
                limit=query.limit,
                offset=query.offset,
            )
        elif query.zip_code:
            parcels = await self.regrid.search_parcels_by_lbcs(
                lbcs_ranges=lbcs_ranges,
                zip_code=query.zip_code,
                max_results=query.limit,
                min_acres=query.filters.min_acres,
                max_acres=query.filters.max_acres,
                offset=query.offset,
            )
        elif query.viewport:
            # Convert viewport to polygon and search
            viewport_polygon = self._viewport_to_polygon(query.viewport)
            parcels = await self._query_regrid_spatial(
                polygon_geojson=viewport_polygon,
                lbcs_ranges=lbcs_ranges,
                min_acres=query.filters.min_acres,
                max_acres=query.filters.max_acres,
                limit=query.limit,
                offset=query.offset,
            )
        else:
            return SearchResult(
                success=False,
                search_type=SearchType.CATEGORY,
                query=query,
                total_count=0,
                parcels=[],
                error="Geographic scope required (polygon, ZIP, or viewport)",
            )
        
        result_parcels = [self._parcel_to_result(p) for p in parcels]
        
        return SearchResult(
            success=True,
            search_type=SearchType.CATEGORY,
            query=query,
            total_count=len(result_parcels),
            parcels=result_parcels if not preview_only else [],
            preview_only=preview_only,
        )
    
    async def _search_brand(
        self,
        query: SearchQuery,
        preview_only: bool,
    ) -> SearchResult:
        """Search by brand name using Google Places API."""
        if not query.brand_name:
            return SearchResult(
                success=False,
                search_type=SearchType.BRAND,
                query=query,
                total_count=0,
                parcels=[],
                error="Brand name required",
            )
        
        # Import Google Places service
        from app.core.brand_search_service import BrandSearchService
        brand_service = BrandSearchService()
        
        # Determine geographic scope
        if query.viewport:
            results = await brand_service.search_brand_in_viewport(
                brand_name=query.brand_name,
                viewport=query.viewport,
                limit=query.limit,
            )
        elif query.zip_code:
            results = await brand_service.search_brand_in_zip(
                brand_name=query.brand_name,
                zip_code=query.zip_code,
                limit=query.limit,
            )
        elif query.state_code:
            results = await brand_service.search_brand_in_state(
                brand_name=query.brand_name,
                state_code=query.state_code,
                limit=query.limit,
            )
        else:
            return SearchResult(
                success=False,
                search_type=SearchType.BRAND,
                query=query,
                total_count=0,
                parcels=[],
                error="Geographic scope required (viewport, ZIP, or state)",
            )
        
        return SearchResult(
            success=True,
            search_type=SearchType.BRAND,
            query=query,
            total_count=len(results),
            parcels=results if not preview_only else [],
            preview_only=preview_only,
        )
    
    async def _query_regrid_with_lbcs(
        self,
        polygon_geojson: Dict,
        lbcs_ranges: List[tuple],
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
        limit: int = 500,
    ) -> List[PropertyParcel]:
        """
        Query Regrid using /parcels/query endpoint with server-side LBCS filtering.
        
        Strategy:
        - Use bbox (bounding box) + LBCS filter for server-side filtering
        - Then post-filter to ensure parcels are actually inside the polygon
        - This is MUCH more accurate than /parcels/area + local filter
        """
        import httpx
        from app.core.config import settings
        from shapely.geometry import shape
        
        if not settings.REGRID_API_KEY:
            logger.warning("Regrid API key not configured")
            return []
        
        try:
            # Parse polygon for local filtering
            polygon_shape = shape(polygon_geojson)
            minx, miny, maxx, maxy = polygon_shape.bounds
            
            # Build bbox string: "minx,miny,maxx,maxy"
            bbox = f"{minx},{miny},{maxx},{maxy}"
            
            url = "https://app.regrid.com/api/v2/parcels/query"
            
            all_parcels = []
            
            # Query each LBCS range separately to maximize matches
            for lbcs_min, lbcs_max in lbcs_ranges:
                # Build query parameters
                params = {
                    "token": settings.REGRID_API_KEY,
                    "limit": min(limit, 1000),
                    "bbox": bbox,  # Bounding box filter
                }
                
                # Add LBCS filter - server-side filtering!
                params["fields[lbcs_activity][gte]"] = lbcs_min
                params["fields[lbcs_activity][lte]"] = lbcs_max
                
                # Add acreage filters
                if min_acres is not None:
                    params["fields[ll_gisacre][gte]"] = min_acres
                if max_acres is not None:
                    params["fields[ll_gisacre][lte]"] = max_acres
                
                print(f"Querying LBCS {lbcs_min}-{lbcs_max} via /parcels/query with bbox + LBCS filter...")
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    try:
                        response = await client.get(url, params=params)
                        print(f"Response status: {response.status_code}")
                        
                        if response.status_code != 200:
                            print(f"Regrid error: {response.text[:300]}")
                            continue
                        
                        data = response.json()
                        
                        # /parcels/query returns: {"parcels": {"type": "FeatureCollection", ...}}
                        parcels_data = data.get("parcels", data)  # Handle both formats
                        if isinstance(parcels_data, dict):
                            features = parcels_data.get("features", [])
                        else:
                            features = []
                        
                        print(f"Found {len(features)} parcels in bbox for LBCS {lbcs_min}-{lbcs_max}")
                        
                        # Parse using RegridService
                        parcels = self.regrid._parse_response(parcels_data)
                        all_parcels.extend(parcels)
                            
                    except httpx.TimeoutException:
                        print(f"⚠️ Regrid request timed out")
                        continue
                    except httpx.RequestError as e:
                        print(f"⚠️ Regrid request error: {e}")
                        continue
            
            # Deduplicate by parcel_id
            seen_ids = set()
            unique_parcels = []
            for p in all_parcels:
                if p.parcel_id not in seen_ids:
                    seen_ids.add(p.parcel_id)
                    unique_parcels.append(p)
            
            print(f"Server-side LBCS filter returned {len(unique_parcels)} unique parcels")
            
            # Post-filter: ensure parcels are actually inside the polygon (not just bbox)
            if unique_parcels:
                filtered = []
                for parcel in unique_parcels:
                    if parcel.has_valid_geometry:
                        # Check if parcel centroid is in polygon (faster than full intersection)
                        if polygon_shape.contains(parcel.centroid):
                            filtered.append(parcel)
                        # Or if polygons intersect
                        elif polygon_shape.intersects(parcel.polygon):
                            filtered.append(parcel)
                
                print(f"✓ After polygon filter: {len(filtered)} parcels (from {len(unique_parcels)} in bbox)")
                return filtered
            
            # FALLBACK: If LBCS returned 0, try keyword search on usedesc field
            # Get keywords for this category
            keywords = []
            for cat_id, cat_info in PROPERTY_CATEGORIES.items():
                if cat_info.get("lbcs_codes") == lbcs_ranges:
                    keywords = cat_info.get("keywords", [])
                    print(f"LBCS returned 0, trying keyword fallback with: {keywords[:3]}...")
                    break
            
            if keywords:
                keyword_parcels = await self._query_regrid_by_keywords(
                    polygon_geojson=polygon_geojson,
                    keywords=keywords,
                    min_acres=min_acres,
                    max_acres=max_acres,
                    limit=limit,
                )
                if keyword_parcels:
                    print(f"✓ Keyword fallback found {len(keyword_parcels)} parcels")
                    return keyword_parcels
            
            return unique_parcels
            
        except Exception as e:
            print(f"Regrid query error: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _query_regrid_by_keywords(
        self,
        polygon_geojson: Dict,
        keywords: List[str],
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
        limit: int = 200,
    ) -> List[PropertyParcel]:
        """
        Fallback search using keywords on usedesc field.
        
        Uses /parcels/query with usedesc[ilike] for pattern matching.
        This catches parcels that don't have LBCS codes but have descriptive text.
        """
        import httpx
        from app.core.config import settings
        from shapely.geometry import shape
        
        if not settings.REGRID_API_KEY:
            return []
        
        try:
            polygon_shape = shape(polygon_geojson)
            minx, miny, maxx, maxy = polygon_shape.bounds
            bbox = f"{minx},{miny},{maxx},{maxy}"
            
            url = "https://app.regrid.com/api/v2/parcels/query"
            
            all_parcels = []
            seen_ids = set()
            
            # Try each keyword (limit to first 3 to avoid too many requests)
            for keyword in keywords[:3]:
                if len(all_parcels) >= limit:
                    break
                    
                params = {
                    "token": settings.REGRID_API_KEY,
                    "limit": min(limit - len(all_parcels), 500),
                    "bbox": bbox,
                    "fields[usedesc][ilike]": f"%{keyword}%",  # Case-insensitive LIKE
                }
                
                if min_acres is not None:
                    params["fields[ll_gisacre][gte]"] = min_acres
                if max_acres is not None:
                    params["fields[ll_gisacre][lte]"] = max_acres
                
                print(f"  Trying keyword '{keyword}'...")
                
                async with httpx.AsyncClient(timeout=20.0) as client:
                    try:
                        response = await client.get(url, params=params)
                        
                        if response.status_code != 200:
                            continue
                        
                        data = response.json()
                        parcels_data = data.get("parcels", data)
                        
                        if isinstance(parcels_data, dict):
                            features = parcels_data.get("features", [])
                            if features:
                                print(f"    Found {len(features)} for '{keyword}'")
                                parcels = self.regrid._parse_response(parcels_data)
                                
                                # Add unique parcels that are in polygon
                                for p in parcels:
                                    if p.parcel_id not in seen_ids and p.has_valid_geometry:
                                        if polygon_shape.contains(p.centroid) or polygon_shape.intersects(p.polygon):
                                            seen_ids.add(p.parcel_id)
                                            all_parcels.append(p)
                                            
                    except Exception:
                        continue
            
            return all_parcels[:limit]
            
        except Exception as e:
            print(f"Keyword search error: {e}")
            return []

    async def _query_regrid_spatial(
        self,
        polygon_geojson: Dict,
        lbcs_ranges: Optional[List[tuple]] = None,
        min_acres: Optional[float] = None,
        max_acres: Optional[float] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[PropertyParcel]:
        """
        Query Regrid with spatial polygon filter.
        
        Uses the correct /api/v2/parcels/area endpoint:
        - POST request with GeoJSON polygon in body
        - Supports field filtering
        - Max polygon size: 350 sq miles (Regrid limit is 380)
        """
        import httpx
        from app.core.config import settings
        from shapely.geometry import shape
        
        # Area limits for different endpoints
        MAX_AREA_SQ_MILES = 350  # /parcels/area allows up to 380
        QUERY_AREA_LIMIT = 80  # /parcels/query allows up to 80 sq mi for polygon queries
        
        if not settings.REGRID_API_KEY:
            logger.warning("Regrid API key not configured")
            return []
        
        try:
            # Parse polygon for later filtering
            polygon_shape = shape(polygon_geojson)
            minx, miny, maxx, maxy = polygon_shape.bounds
            
            # Calculate approximate area in sq miles
            # At ~32 deg lat, 1 deg lat ≈ 69 miles, 1 deg lng ≈ 58 miles
            width_miles = (maxx - minx) * 58
            height_miles = (maxy - miny) * 69
            approx_area_sqmi = width_miles * height_miles
            
            print(f"Polygon bounds: ({miny:.4f}, {minx:.4f}) to ({maxy:.4f}, {maxx:.4f})")
            print(f"Approximate area: {approx_area_sqmi:.1f} sq miles")
            
            if approx_area_sqmi > MAX_AREA_SQ_MILES:
                print(f"⚠️ Area too large ({approx_area_sqmi:.1f} sq mi > {MAX_AREA_SQ_MILES} sq mi limit).")
                return []
            
            # STRATEGY:
            # - If we have LBCS filters AND area ≤ 80 sq mi: Use /parcels/query (server-side filtering)
            # - Otherwise: Use /parcels/area (local filtering)
            # 
            # /parcels/query with LBCS filters is MUCH better for type searches because
            # it filters on the server, returning only matching parcels.
            
            use_query_endpoint = lbcs_ranges and approx_area_sqmi <= QUERY_AREA_LIMIT
            
            if use_query_endpoint:
                print(f"✓ Using /parcels/query (server-side LBCS filter, area {approx_area_sqmi:.1f} ≤ {QUERY_AREA_LIMIT} sq mi)")
                parcels = await self._query_regrid_with_lbcs(
                    polygon_geojson=polygon_geojson,
                    lbcs_ranges=lbcs_ranges,
                    min_acres=min_acres,
                    max_acres=max_acres,
                    limit=limit,
                )
                # Server-side filtering already done, return directly
                return parcels
            
            # Fall back to /parcels/area (no server-side LBCS filtering)
            print(f"→ Using /parcels/area (local filtering, area {approx_area_sqmi:.1f} sq mi)")
            url = "https://app.regrid.com/api/v2/parcels/area"
            
            # Build request body
            body = {
                "token": settings.REGRID_API_KEY,
                "geojson": polygon_geojson,
                "limit": min(limit, 1000),
            }
            
            # Add acreage filters
            fields = {}
            if min_acres is not None:
                fields["ll_gisacre"] = {"gte": min_acres}
            if max_acres is not None:
                if "ll_gisacre" in fields:
                    fields["ll_gisacre"]["lte"] = max_acres
                else:
                    fields["ll_gisacre"] = {"lte": max_acres}
            
            if fields:
                body["fields"] = fields
            
            # Log request
            safe_body = {k: v for k, v in body.items() if k != 'token'}
            safe_body['geojson'] = f"<Polygon with {len(polygon_geojson.get('coordinates', [[]])[0])} points>"
            print(f"Regrid area request: {safe_body}")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    print(f"Making Regrid POST /parcels/area request...")
                    response = await client.post(
                        url,
                        json=body,
                        headers={"Content-Type": "application/json"}
                    )
                    print(f"Regrid response status: {response.status_code}")
                except httpx.TimeoutException:
                    print(f"⚠️ Regrid request timed out after 30s")
                    return []
                except httpx.RequestError as e:
                    print(f"⚠️ Regrid request error: {e}")
                    return []
                
                if response.status_code != 200:
                    print(f"Regrid error ({response.status_code}): {response.text[:500]}")
                    return []
                
                data = response.json()
                print(f"Response keys: {list(data.keys())}")
                
                parcels_data = data.get("parcels", {})
                if isinstance(parcels_data, dict):
                    features = parcels_data.get("features", [])
                else:
                    features = []
                
                print(f"Regrid returned {len(features)} parcels")
                
                parcels = self.regrid._parse_response(parcels_data)
                filtered_parcels = parcels
                
                print(f"Parsed {len(filtered_parcels)} parcels from area query")
                
                # Apply local filtering using LBCS codes AND keyword fallbacks
                # This is needed because LBCS data coverage varies significantly by county
                if lbcs_ranges and filtered_parcels:
                    # Get keywords for fallback filtering if available
                    category_id = None  # Will be set if we're filtering by category
                    keywords = []
                    
                    # Try to get keywords from query context
                    # This would need to be passed in, but for now extract from the LBCS ranges
                    for cat_id, cat_info in PROPERTY_CATEGORIES.items():
                        if cat_info.get("lbcs_codes") == lbcs_ranges:
                            keywords = cat_info.get("keywords", [])
                            category_id = cat_id
                            break
                    
                    lbcs_matched = []
                    keyword_matched = []
                    lbcs_unknown = 0
                    lbcs_other = 0
                    
                    for parcel in filtered_parcels:
                        lbcs = parcel.lbcs_activity
                        matched_by_lbcs = False
                        
                        if lbcs:
                            # Check if LBCS code is in any of the requested ranges
                            for lbcs_min, lbcs_max in lbcs_ranges:
                                if lbcs_min <= lbcs <= lbcs_max:
                                    matched_by_lbcs = True
                                    break
                            
                            if matched_by_lbcs:
                                lbcs_matched.append(parcel)
                            else:
                                lbcs_other += 1
                        else:
                            # No LBCS data - try keyword matching on usedesc/land_use
                            lbcs_unknown += 1
                            
                            if keywords:
                                use_desc = (parcel.land_use or "").lower()
                                for kw in keywords:
                                    if kw.lower() in use_desc:
                                        keyword_matched.append(parcel)
                                        break
                    
                    print(f"LBCS filter: {len(lbcs_matched)} LBCS matched, {len(keyword_matched)} keyword matched, {lbcs_unknown} no LBCS, {lbcs_other} different type")
                    
                    # Combine LBCS matches with keyword matches (deduped)
                    matched_ids = set(p.parcel_id for p in lbcs_matched)
                    all_matched = lbcs_matched.copy()
                    for p in keyword_matched:
                        if p.parcel_id not in matched_ids:
                            all_matched.append(p)
                            matched_ids.add(p.parcel_id)
                    
                    if all_matched:
                        print(f"✅ Returning {len(all_matched)} matched parcels")
                        return all_matched
                    else:
                        # No matches found - this is likely because:
                        # 1. LBCS data coverage is limited (varies by county)
                        # 2. The property type doesn't exist in this area
                        print(f"⚠️ No parcels matched filters. LBCS coverage may be limited in this area.")
                        return []  # Return empty, don't return unrelated parcels!
                
                return filtered_parcels
                
        except Exception as e:
            logger.error(f"Regrid spatial query error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _viewport_to_polygon(self, viewport: Dict) -> Dict:
        """Convert viewport bounds to GeoJSON polygon."""
        min_lat = viewport["minLat"]
        max_lat = viewport["maxLat"]
        min_lng = viewport["minLng"]
        max_lng = viewport["maxLng"]
        
        return {
            "type": "Polygon",
            "coordinates": [[
                [min_lng, min_lat],
                [max_lng, min_lat],
                [max_lng, max_lat],
                [min_lng, max_lat],
                [min_lng, min_lat],
            ]]
        }
    
    def _get_lbcs_ranges(self, filters: SearchFilters) -> Optional[List[tuple]]:
        """Get LBCS ranges from filters."""
        if filters.lbcs_codes:
            return filters.lbcs_codes
        
        if filters.category_id:
            category = PROPERTY_CATEGORIES.get(filters.category_id)
            if category:
                return category["lbcs_codes"]
        
        return None
    
    def _parcel_to_result(self, parcel: PropertyParcel) -> SearchResultParcel:
        """Convert PropertyParcel to SearchResultParcel."""
        polygon_geojson = None
        if parcel.has_valid_geometry:
            polygon_geojson = mapping(parcel.polygon)
        
        area_sqft = None
        if parcel.area_m2:
            area_sqft = parcel.area_m2 * 10.7639
        
        return SearchResultParcel(
            parcel_id=parcel.parcel_id,
            address=parcel.address,
            owner=parcel.owner,
            lat=parcel.centroid.y,
            lng=parcel.centroid.x,
            area_acres=parcel.area_acres,
            area_sqft=area_sqft,
            land_use=parcel.land_use,
            zoning=parcel.zoning,
            year_built=parcel.year_built,
            polygon_geojson=polygon_geojson,
            lbcs_activity=parcel.lbcs_activity,
            lbcs_activity_desc=parcel.lbcs_activity_desc,
        )
    
    def get_categories(self) -> Dict[str, Dict]:
        """Get all available property categories."""
        return PROPERTY_CATEGORIES


# Singleton instance
search_service = SearchService()
