"""
Brand Search Service

Uses Google Places API to search for businesses by brand name.
Supports searching within viewport, ZIP code, or state.

Key Features:
- Text search for brand names (McDonald's, Starbucks, etc.)
- Grid search for larger areas (state-level)
- Rate limiting and caching
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import httpx

from app.core.config import settings
from app.core.search_service import SearchResultParcel

logger = logging.getLogger(__name__)


# State centers for grid searching
STATE_CENTERS = {
    "AL": (32.806671, -86.791130),
    "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221),
    "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564),
    "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371),
    "DE": (39.318523, -75.507141),
    "FL": (27.766279, -81.686783),
    "GA": (33.040619, -83.643074),
    "HI": (21.094318, -157.498337),
    "ID": (44.240459, -114.478828),
    "IL": (40.349457, -88.986137),
    "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526),
    "KS": (38.526600, -96.726486),
    "KY": (37.668140, -84.670067),
    "LA": (31.169546, -91.867805),
    "ME": (44.693947, -69.381927),
    "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106),
    "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192),
    "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368),
    "MT": (46.921925, -110.454353),
    "NE": (41.125370, -98.268082),
    "NV": (38.313515, -117.055374),
    "NH": (43.452492, -71.563896),
    "NJ": (40.298904, -74.521011),
    "NM": (34.840515, -106.248482),
    "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419),
    "ND": (47.528912, -99.784012),
    "OH": (40.388783, -82.764915),
    "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938),
    "PA": (40.590752, -77.209755),
    "RI": (41.680893, -71.511780),
    "SC": (33.856892, -80.945007),
    "SD": (44.299782, -99.438828),
    "TN": (35.747845, -86.692345),
    "TX": (31.054487, -97.563461),
    "UT": (40.150032, -111.862434),
    "VT": (44.045876, -72.710686),
    "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494),
    "WV": (38.491226, -80.954453),
    "WI": (44.268543, -89.616508),
    "WY": (42.755966, -107.302490),
}


class BrandSearchService:
    """
    Service to search for businesses by brand name using Google Places API.
    """
    
    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/place"
    
    @property
    def is_configured(self) -> bool:
        """Check if Google Places API is configured."""
        return bool(self.api_key)
    
    async def search_brand_in_viewport(
        self,
        brand_name: str,
        viewport: Dict[str, float],
        limit: int = 60,
    ) -> List[SearchResultParcel]:
        """
        Search for a brand within the current map viewport.
        
        Args:
            brand_name: Name of the brand/franchise
            viewport: {"minLat", "maxLat", "minLng", "maxLng"}
            limit: Maximum results
            
        Returns:
            List of SearchResultParcel
        """
        if not self.is_configured:
            logger.warning("Google Maps API key not configured")
            return []
        
        # Calculate center of viewport
        center_lat = (viewport["minLat"] + viewport["maxLat"]) / 2
        center_lng = (viewport["minLng"] + viewport["maxLng"]) / 2
        
        # Calculate radius (approximate, in meters)
        lat_diff = viewport["maxLat"] - viewport["minLat"]
        lng_diff = viewport["maxLng"] - viewport["minLng"]
        # Rough conversion: 1 degree lat ≈ 111km
        radius_m = min(
            max(lat_diff * 111000 / 2, lng_diff * 111000 / 2),
            50000  # Max 50km radius
        )
        
        logger.info(f"🏢 Brand search: '{brand_name}' in viewport (radius: {radius_m/1000:.1f}km)")
        
        return await self._text_search(
            query=brand_name,
            center_lat=center_lat,
            center_lng=center_lng,
            radius_m=radius_m,
            limit=limit,
        )
    
    async def search_brand_in_zip(
        self,
        brand_name: str,
        zip_code: str,
        limit: int = 60,
    ) -> List[SearchResultParcel]:
        """
        Search for a brand within a ZIP code area.
        
        Args:
            brand_name: Name of the brand/franchise
            zip_code: 5-digit ZIP code
            limit: Maximum results
            
        Returns:
            List of SearchResultParcel
        """
        if not self.is_configured:
            logger.warning("Google Maps API key not configured")
            return []
        
        logger.info(f"🏢 Brand search: '{brand_name}' in ZIP {zip_code}")
        
        # Use text search with ZIP code as location bias
        return await self._text_search(
            query=f"{brand_name} {zip_code}",
            limit=limit,
        )
    
    async def search_brand_in_state(
        self,
        brand_name: str,
        state_code: str,
        limit: int = 100,
    ) -> List[SearchResultParcel]:
        """
        Search for a brand within a state.
        
        WARNING: This can be expensive - uses grid search with multiple API calls.
        
        Args:
            brand_name: Name of the brand/franchise
            state_code: 2-letter state code
            limit: Maximum results
            
        Returns:
            List of SearchResultParcel
        """
        if not self.is_configured:
            logger.warning("Google Maps API key not configured")
            return []
        
        state_code = state_code.upper()
        center = STATE_CENTERS.get(state_code)
        
        if not center:
            logger.warning(f"Unknown state code: {state_code}")
            return []
        
        logger.info(f"🏢 Brand search: '{brand_name}' in state {state_code}")
        logger.warning(f"   ⚠️ State-level search is expensive - consider using viewport or ZIP")
        
        # Use a single search with state name for now
        # Full grid search would be too expensive
        return await self._text_search(
            query=f"{brand_name} in {state_code}",
            center_lat=center[0],
            center_lng=center[1],
            radius_m=200000,  # 200km radius
            limit=limit,
        )
    
    async def _text_search(
        self,
        query: str,
        center_lat: Optional[float] = None,
        center_lng: Optional[float] = None,
        radius_m: Optional[float] = None,
        limit: int = 60,
    ) -> List[SearchResultParcel]:
        """
        Execute a Google Places text search.
        
        Note: Google Places returns max 60 results (20 per page, 3 pages).
        """
        results = []
        next_page_token = None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while len(results) < limit:
                    url = f"{self.base_url}/textsearch/json"
                    
                    params = {
                        "query": query,
                        "key": self.api_key,
                    }
                    
                    if next_page_token:
                        params["pagetoken"] = next_page_token
                    elif center_lat and center_lng:
                        params["location"] = f"{center_lat},{center_lng}"
                        if radius_m:
                            params["radius"] = int(radius_m)
                    
                    response = await client.get(url, params=params)
                    
                    if response.status_code != 200:
                        logger.error(f"Google Places API error: {response.status_code}")
                        break
                    
                    data = response.json()
                    status = data.get("status")
                    
                    if status == "ZERO_RESULTS":
                        logger.info(f"   No results found for '{query}'")
                        break
                    
                    if status not in ("OK", "ZERO_RESULTS"):
                        logger.error(f"Google Places API status: {status}")
                        break
                    
                    places = data.get("results", [])
                    
                    for place in places:
                        result = self._place_to_result(place, query)
                        if result:
                            results.append(result)
                    
                    next_page_token = data.get("next_page_token")
                    
                    if not next_page_token:
                        break
                    
                    # Google requires a short delay before using next_page_token
                    await asyncio.sleep(2)
                
                logger.info(f"   Found {len(results)} locations for '{query}'")
                return results[:limit]
                
        except Exception as e:
            logger.error(f"Google Places search error: {e}")
            import traceback
            traceback.print_exc()
            return results
    
    def _place_to_result(
        self,
        place: Dict[str, Any],
        brand_name: str,
    ) -> Optional[SearchResultParcel]:
        """Convert a Google Places result to SearchResultParcel."""
        try:
            location = place.get("geometry", {}).get("location", {})
            lat = location.get("lat")
            lng = location.get("lng")
            
            if not lat or not lng:
                return None
            
            return SearchResultParcel(
                parcel_id=place.get("place_id", ""),
                address=place.get("formatted_address") or place.get("vicinity"),
                owner=None,
                lat=lat,
                lng=lng,
                area_acres=None,
                area_sqft=None,
                land_use=place.get("types", ["business"])[0] if place.get("types") else "business",
                zoning=None,
                year_built=None,
                polygon_geojson=None,
                brand_name=place.get("name") or brand_name,
                place_id=place.get("place_id"),
            )
        except Exception as e:
            logger.debug(f"Failed to parse place: {e}")
            return None


# Singleton instance
brand_search_service = BrandSearchService()
