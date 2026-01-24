"""
County Service

Provides US county data for search:
- Autocomplete search for counties
- County boundary GeoJSON retrieval
- FIPS code mapping

Data source: US Census Bureau TIGER/Line
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class County:
    """US County data."""
    fips: str           # 5-digit FIPS code (state + county)
    name: str           # County name
    state: str          # State abbreviation
    state_fips: str     # 2-digit state FIPS
    full_name: str      # "County Name, ST"
    

# US States with their FIPS codes
US_STATES = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "72": "PR",
}

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}


class CountyService:
    """
    Service for US county data.
    
    Uses Census Bureau TIGERweb API for county data and boundaries.
    """
    
    def __init__(self):
        self._counties_cache: Optional[List[County]] = None
        self._boundaries_cache: Dict[str, Dict] = {}
    
    async def get_all_counties(self) -> List[County]:
        """
        Get list of all US counties.
        
        Uses Census Bureau API to fetch county list.
        Results are cached after first call.
        """
        if self._counties_cache:
            return self._counties_cache
        
        try:
            # Fetch from Census Bureau API
            url = "https://api.census.gov/data/2020/dec/pl?get=NAME&for=county:*"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.warning(f"Census API error: {response.status_code}")
                    return self._get_fallback_counties()
                
                data = response.json()
                
                # Parse response: [["NAME", "state", "county"], ["Autauga County, Alabama", "01", "001"], ...]
                counties = []
                for row in data[1:]:  # Skip header row
                    name_full = row[0]  # "County Name, State Name"
                    state_fips = row[1]
                    county_fips = row[2]
                    
                    # Parse name
                    parts = name_full.split(", ")
                    county_name = parts[0] if parts else name_full
                    
                    state_abbr = US_STATES.get(state_fips, "")
                    fips = f"{state_fips}{county_fips}"
                    
                    counties.append(County(
                        fips=fips,
                        name=county_name,
                        state=state_abbr,
                        state_fips=state_fips,
                        full_name=f"{county_name}, {state_abbr}",
                    ))
                
                # Sort by state, then county name
                counties.sort(key=lambda c: (c.state, c.name))
                
                self._counties_cache = counties
                logger.info(f"Loaded {len(counties)} US counties from Census API")
                return counties
                
        except Exception as e:
            logger.error(f"Failed to fetch counties from Census API: {e}")
            return self._get_fallback_counties()
    
    def _get_fallback_counties(self) -> List[County]:
        """Return a minimal fallback list of major counties."""
        # Just return empty for now - will load from API
        return []
    
    async def search_counties(
        self,
        query: str,
        limit: int = 20,
    ) -> List[County]:
        """
        Search counties by name (autocomplete).
        
        Args:
            query: Search string (e.g., "Dallas", "Los An", "TX")
            limit: Max results to return
            
        Returns:
            List of matching counties
        """
        counties = await self.get_all_counties()
        
        if not query or len(query) < 2:
            return []
        
        query_lower = query.lower().strip()
        
        # Score matches
        scored = []
        for county in counties:
            score = 0
            name_lower = county.name.lower()
            full_lower = county.full_name.lower()
            
            # Exact match on county name
            if name_lower == query_lower:
                score = 100
            # Starts with query
            elif name_lower.startswith(query_lower):
                score = 80
            # Full name starts with query
            elif full_lower.startswith(query_lower):
                score = 70
            # State abbreviation match
            elif county.state.lower() == query_lower:
                score = 60
            # Contains query
            elif query_lower in full_lower:
                score = 40
            
            if score > 0:
                scored.append((score, county))
        
        # Sort by score desc, then alphabetically
        scored.sort(key=lambda x: (-x[0], x[1].full_name))
        
        return [c for _, c in scored[:limit]]
    
    async def get_county_boundary(
        self,
        fips: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get GeoJSON boundary for a county.
        
        Args:
            fips: 5-digit FIPS code
            
        Returns:
            GeoJSON Polygon/MultiPolygon geometry
        """
        if fips in self._boundaries_cache:
            return self._boundaries_cache[fips]
        
        try:
            # Use Census TIGERweb for boundaries
            # This is the cartographic boundary (simplified, good for display)
            state_fips = fips[:2]
            county_fips = fips[2:]
            
            url = (
                f"https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
                f"tigerWMS_Current/MapServer/86/query"
                f"?where=STATE='{state_fips}'+AND+COUNTY='{county_fips}'"
                f"&outFields=NAME,STATE,COUNTY,GEOID"
                f"&f=geojson"
                f"&outSR=4326"
            )
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.warning(f"TIGERweb boundary fetch failed: {response.status_code}")
                    return None
                
                data = response.json()
                
                features = data.get("features", [])
                if not features:
                    logger.warning(f"No boundary found for FIPS {fips}")
                    return None
                
                # Get the geometry from first feature
                geometry = features[0].get("geometry")
                
                if geometry:
                    self._boundaries_cache[fips] = geometry
                    
                return geometry
                
        except Exception as e:
            logger.error(f"Failed to fetch county boundary for {fips}: {e}")
            return None
    
    async def get_county_by_fips(self, fips: str) -> Optional[County]:
        """Get a county by its FIPS code."""
        counties = await self.get_all_counties()
        
        for county in counties:
            if county.fips == fips:
                return county
        
        return None


# Singleton
county_service = CountyService()
