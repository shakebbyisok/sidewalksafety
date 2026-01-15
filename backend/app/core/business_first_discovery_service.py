"""
Business-First Discovery Service

Searches for businesses by priority type (HOA, apartments, shopping centers, etc.)
and returns them with contact info for lead generation.

This is the first step in the business-first discovery pipeline:
1. Find businesses by type → 2. Find their parking lots → 3. Evaluate condition
"""

import logging
import httpx
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from shapely.geometry import Point

from app.core.config import settings

logger = logging.getLogger(__name__)


class BusinessTier(str, Enum):
    """Business priority tiers for lead scoring."""
    PREMIUM = "premium"
    HIGH = "high"
    STANDARD = "standard"


# Business type definitions with IDs for frontend selection
# Each type has an ID, queries to search, and the tier it belongs to
# NOTE: We search for ACTUAL properties, not management companies
#       (e.g., "apartment complex" returns the building, not the management office)
BUSINESS_TYPES = {
    # Premium tier - Large properties with significant parking/roads
    "apartments": {
        "tier": BusinessTier.PREMIUM,
        "queries": ["apartment complex", "apartments for rent", "apartment building"],
    },
    "condos": {
        "tier": BusinessTier.PREMIUM,
        "queries": ["condominium complex", "condo building"],
    },
    "townhomes": {
        "tier": BusinessTier.PREMIUM,
        "queries": ["townhome community", "townhouse complex"],
    },
    "mobile_home": {
        "tier": BusinessTier.PREMIUM,
        "queries": ["mobile home park", "trailer park", "manufactured home community"],
    },
    # High tier - Commercial properties with large parking lots
    "shopping": {
        "tier": BusinessTier.HIGH,
        "queries": ["shopping center", "shopping mall", "retail plaza", "strip mall"],
    },
    "hotels": {
        "tier": BusinessTier.HIGH,
        "queries": ["hotel", "motel", "extended stay"],
    },
    "offices": {
        "tier": BusinessTier.HIGH,
        "queries": ["office park", "office complex", "business park"],
    },
    "warehouses": {
        "tier": BusinessTier.HIGH,
        "queries": ["warehouse", "distribution center", "industrial park", "logistics center"],
    },
    # Standard tier - Medium-sized properties
    "churches": {
        "tier": BusinessTier.STANDARD,
        "queries": ["church", "religious center", "place of worship"],
    },
    "schools": {
        "tier": BusinessTier.STANDARD,
        "queries": ["school", "private school", "charter school"],
    },
    "hospitals": {
        "tier": BusinessTier.STANDARD,
        "queries": ["hospital", "medical center", "urgent care"],
    },
    "gyms": {
        "tier": BusinessTier.STANDARD,
        "queries": ["gym", "fitness center", "recreation center"],
    },
    "grocery": {
        "tier": BusinessTier.STANDARD,
        "queries": ["grocery store", "supermarket"],
    },
    "car_dealers": {
        "tier": BusinessTier.STANDARD,
        "queries": ["car dealership", "auto dealership"],
    },
}


def get_queries_for_tier(tier: BusinessTier) -> List[str]:
    """Get all search queries for a tier."""
    queries = []
    for type_id, type_def in BUSINESS_TYPES.items():
        if type_def["tier"] == tier:
            queries.extend(type_def["queries"])
    return queries


def get_queries_for_type_ids(type_ids: List[str]) -> Dict[BusinessTier, List[str]]:
    """Get queries grouped by tier for specific type IDs."""
    result: Dict[BusinessTier, List[str]] = {}
    for type_id in type_ids:
        if type_id in BUSINESS_TYPES:
            type_def = BUSINESS_TYPES[type_id]
            tier = type_def["tier"]
            if tier not in result:
                result[tier] = []
            result[tier].extend(type_def["queries"])
    return result


@dataclass
class DiscoveredBusiness:
    """Business discovered from Google Places with contact info."""
    places_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    tier: BusinessTier
    business_type: str  # The query that found it
    
    # Contact info (from Places Details API)
    phone: Optional[str] = None
    website: Optional[str] = None
    
    # Additional metadata
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    types: List[str] = field(default_factory=list)
    raw_data: Optional[Dict[str, Any]] = None
    
    @property
    def location(self) -> Point:
        """Return location as Shapely Point."""
        return Point(self.longitude, self.latitude)
    
    @property
    def has_contact_info(self) -> bool:
        """Check if business has any contact info."""
        return bool(self.phone or self.website)


class BusinessFirstDiscoveryService:
    """
    Service to discover businesses by type for lead generation.
    
    Searches Google Places for high-value business types (HOAs, apartments, etc.)
    and retrieves their contact information.
    """
    
    def __init__(self):
        self.google_places_key = settings.GOOGLE_PLACES_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/place"
    
    async def discover_businesses(
        self,
        center_lat: float,
        center_lng: float,
        radius_meters: int = 5000,
        tiers: Optional[List[BusinessTier]] = None,
        business_type_ids: Optional[List[str]] = None,
        max_per_tier: int = 20,
        max_total: int = 50,
    ) -> List[DiscoveredBusiness]:
        """
        Discover businesses in an area, prioritized by tier.
        
        Args:
            center_lat: Center latitude of search area
            center_lng: Center longitude of search area
            radius_meters: Search radius in meters (default 5km)
            tiers: Which tiers to search (default: all)
            business_type_ids: Specific business type IDs to search (e.g., ["hoa", "apartments"])
            max_per_tier: Maximum businesses per tier
            max_total: Maximum total businesses to return
        
        Returns:
            List of DiscoveredBusiness sorted by tier (premium first)
        """
        if not self.google_places_key:
            logger.error("Google Places API key not configured")
            return []
        
        all_businesses: List[DiscoveredBusiness] = []
        seen_place_ids: set = set()
        
        # Determine which queries to use
        if business_type_ids:
            # Use specific business types
            tier_queries = get_queries_for_type_ids(business_type_ids)
            # Search in tier order (premium first)
            search_order = [BusinessTier.PREMIUM, BusinessTier.HIGH, BusinessTier.STANDARD]
            
            for tier in search_order:
                if len(all_businesses) >= max_total:
                    break
                
                if tier not in tier_queries:
                    continue
                
                tier_businesses = await self._search_tier(
                    center_lat=center_lat,
                    center_lng=center_lng,
                    radius_meters=radius_meters,
                    tier=tier,
                    queries=tier_queries[tier],
                    max_results=max_per_tier,
                    seen_place_ids=seen_place_ids,
                )
                
                for business in tier_businesses:
                    if len(all_businesses) >= max_total:
                        break
                    all_businesses.append(business)
                    seen_place_ids.add(business.places_id)
        else:
            # Use tiers (default: all)
            if tiers is None:
                tiers = [BusinessTier.PREMIUM, BusinessTier.HIGH, BusinessTier.STANDARD]
            
            for tier in tiers:
                if len(all_businesses) >= max_total:
                    break
                
                tier_businesses = await self._search_tier(
                    center_lat=center_lat,
                    center_lng=center_lng,
                    radius_meters=radius_meters,
                    tier=tier,
                    queries=get_queries_for_tier(tier),
                    max_results=max_per_tier,
                    seen_place_ids=seen_place_ids,
                )
                
                for business in tier_businesses:
                    if len(all_businesses) >= max_total:
                        break
                    all_businesses.append(business)
                    seen_place_ids.add(business.places_id)
        
        logger.info(
            f"Discovered {len(all_businesses)} businesses: "
            f"premium={len([b for b in all_businesses if b.tier == BusinessTier.PREMIUM])}, "
            f"high={len([b for b in all_businesses if b.tier == BusinessTier.HIGH])}, "
            f"standard={len([b for b in all_businesses if b.tier == BusinessTier.STANDARD])}"
        )
        
        return all_businesses
    
    async def _search_tier(
        self,
        center_lat: float,
        center_lng: float,
        radius_meters: int,
        tier: BusinessTier,
        queries: List[str],
        max_results: int,
        seen_place_ids: set,
        max_pages_per_query: int = 3,  # Google allows up to 3 pages (60 results)
    ) -> List[DiscoveredBusiness]:
        """
        Search for businesses in a specific tier using provided queries.
        Supports pagination to get more results.
        """
        
        tier_businesses: List[DiscoveredBusiness] = []
        
        for query in queries:
            if len(tier_businesses) >= max_results:
                break
            
            try:
                # First page
                results, next_page_token = await self._text_search(
                    query=query,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    radius_meters=radius_meters,
                )
                
                pages_fetched = 1
                
                while True:
                    for place in results:
                        place_id = place.get("place_id")
                        if not place_id or place_id in seen_place_ids:
                            continue
                        
                        if len(tier_businesses) >= max_results:
                            break
                        
                        # Get detailed info including phone/website
                        business = await self._create_business_from_place(
                            place=place,
                            tier=tier,
                            query=query,
                        )
                        
                        if business:
                            tier_businesses.append(business)
                            seen_place_ids.add(place_id)
                    
                    # Check if we have enough or need more
                    if len(tier_businesses) >= max_results:
                        break
                    
                    # Fetch next page if available
                    if next_page_token and pages_fetched < max_pages_per_query:
                        results, next_page_token = await self._text_search(
                            query=query,
                            center_lat=center_lat,
                            center_lng=center_lng,
                            radius_meters=radius_meters,
                            next_page_token=next_page_token,
                        )
                        pages_fetched += 1
                    else:
                        break
                        
            except Exception as e:
                logger.warning(f"Error searching for '{query}': {e}")
        
        return tier_businesses
    
    async def _text_search(
        self,
        query: str,
        center_lat: float,
        center_lng: float,
        radius_meters: int,
        next_page_token: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Perform Google Places Text Search.
        
        Returns:
            Tuple of (results, next_page_token)
            next_page_token is None if no more pages
        """
        import asyncio
        
        url = f"{self.base_url}/textsearch/json"
        
        params = {
            "key": self.google_places_key,
        }
        
        if next_page_token:
            # When using pagetoken, no other params needed
            params["pagetoken"] = next_page_token
            # Google requires a short delay before using next_page_token
            await asyncio.sleep(2)
        else:
            params["query"] = query
            params["location"] = f"{center_lat},{center_lng}"
            params["radius"] = radius_meters
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                logger.error(f"Places API error: {response.status_code}")
                return [], None
            
            data = response.json()
            
            if data.get("status") != "OK":
                if data.get("status") != "ZERO_RESULTS":
                    logger.warning(f"Places API status: {data.get('status')}")
                return [], None
            
            results = data.get("results", [])
            token = data.get("next_page_token")
            
            return results, token
    
    async def _get_place_details(self, place_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed place info including phone and website."""
        
        url = f"{self.base_url}/details/json"
        
        params = {
            "place_id": place_id,
            "fields": "formatted_phone_number,website,name,formatted_address",
            "key": self.google_places_key,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if data.get("status") != "OK":
                return None
            
            return data.get("result")
    
    async def _create_business_from_place(
        self,
        place: Dict[str, Any],
        tier: BusinessTier,
        query: str,
    ) -> Optional[DiscoveredBusiness]:
        """Create DiscoveredBusiness from Places API response."""
        
        try:
            place_id = place.get("place_id")
            geometry = place.get("geometry", {})
            location = geometry.get("location", {})
            
            lat = location.get("lat")
            lng = location.get("lng")
            
            if not all([place_id, lat, lng]):
                return None
            
            # Get detailed info (phone, website)
            details = await self._get_place_details(place_id)
            
            phone = None
            website = None
            if details:
                phone = details.get("formatted_phone_number")
                website = details.get("website")
            
            return DiscoveredBusiness(
                places_id=place_id,
                name=place.get("name", "Unknown"),
                address=place.get("formatted_address", ""),
                latitude=lat,
                longitude=lng,
                tier=tier,
                business_type=query,
                phone=phone,
                website=website,
                rating=place.get("rating"),
                user_ratings_total=place.get("user_ratings_total"),
                types=place.get("types", []),
                raw_data=place,
            )
            
        except Exception as e:
            logger.warning(f"Error creating business from place: {e}")
            return None
    
    async def discover_in_polygon(
        self,
        polygon_coords: List[tuple],
        tiers: Optional[List[BusinessTier]] = None,
        max_per_tier: int = 20,
        max_total: int = 50,
    ) -> List[DiscoveredBusiness]:
        """
        Discover businesses within a polygon area.
        
        Uses the polygon centroid as search center with appropriate radius.
        
        Args:
            polygon_coords: List of (lng, lat) tuples defining polygon
            tiers: Which tiers to search
            max_per_tier: Max per tier
            max_total: Max total
        
        Returns:
            List of DiscoveredBusiness within the polygon
        """
        from shapely.geometry import Polygon as ShapelyPolygon
        
        polygon = ShapelyPolygon(polygon_coords)
        centroid = polygon.centroid
        
        # Calculate radius from polygon bounds
        bounds = polygon.bounds  # (minx, miny, maxx, maxy)
        lat_range = bounds[3] - bounds[1]
        lng_range = bounds[2] - bounds[0]
        
        # Convert to meters (approximate)
        radius_lat = lat_range * 111000 / 2
        radius_lng = lng_range * 111000 / 2
        radius_meters = int(max(radius_lat, radius_lng) * 1.2)  # 20% buffer
        
        # Search
        businesses = await self.discover_businesses(
            center_lat=centroid.y,
            center_lng=centroid.x,
            radius_meters=min(radius_meters, 50000),  # Max 50km
            tiers=tiers,
            max_per_tier=max_per_tier,
            max_total=max_total,
        )
        
        # Filter to only businesses within polygon
        filtered = [
            b for b in businesses
            if polygon.contains(b.location)
        ]
        
        logger.info(f"Filtered to {len(filtered)} businesses within polygon")
        
        return filtered


# Singleton instance
business_first_discovery_service = BusinessFirstDiscoveryService()

