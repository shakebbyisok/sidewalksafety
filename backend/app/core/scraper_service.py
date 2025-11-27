import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ScraperService:
    def __init__(self):
        self.apollo_key = settings.APOLLO_API_KEY
        self.google_key = settings.GOOGLE_MAPS_KEY
    
    async def scrape_by_zip(self, zip_code: str) -> List[Dict[str, Any]]:
        """Scrape businesses by ZIP code."""
        deals = []
        
        if self.apollo_key:
            deals.extend(await self._scrape_apollo(zip_code=zip_code))
        
        if not deals:
            deals.extend(await self._scrape_google_places(zip_code=zip_code))
        
        return deals
    
    async def scrape_by_county(self, county: str, state: str) -> List[Dict[str, Any]]:
        """Scrape businesses by county."""
        deals = []
        
        if self.apollo_key:
            deals.extend(await self._scrape_apollo(county=county, state=state))
        
        if not deals:
            deals.extend(await self._scrape_google_places(county=county, state=state))
        
        return deals
    
    async def _scrape_apollo(self, **kwargs) -> List[Dict[str, Any]]:
        """Scrape from Apollo.io API."""
        if not self.apollo_key:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "api_key": self.apollo_key,
                    "q_keywords": [],
                }
                
                if "zip_code" in kwargs:
                    payload["q_keywords"] = [kwargs["zip_code"]]
                elif "county" in kwargs:
                    payload["q_keywords"] = [f"{kwargs['county']} {kwargs['state']}"]
                
                response = await client.post(
                    "https://api.apollo.io/v1/organizations/search",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                data = response.json()
                
                organizations = data.get("organizations", [])
                deals = []
                
                for org in organizations:
                    if self._is_commercial_property(org):
                        street_address = org.get("street_address", "")
                        city = org.get("city", "")
                        state = org.get("state", "")
                        zip_code = org.get("zip_code", "")
                        full_address = f"{street_address}, {city}, {state} {zip_code}".strip(", ")
                        
                        deals.append({
                            "business_name": org.get("name", ""),
                            "address": full_address,
                            "city": city,
                            "state": state,
                            "zip": zip_code,
                            "phone": org.get("phone_numbers", [{}])[0].get("raw_number") if org.get("phone_numbers") else None,
                            "email": org.get("primary_email"),
                            "website": org.get("website_url"),
                            "category": org.get("industry"),
                            "apollo_id": str(org.get("id")),
                        })
                
                return deals
        except Exception as e:
            logger.error(f"Apollo scraping error: {e}")
            return []
    
    async def _scrape_google_places(self, **kwargs) -> List[Dict[str, Any]]:
        """Scrape from Google Places API."""
        if not self.google_key:
            return []
        
        try:
            query = ""
            if "zip_code" in kwargs:
                query = f"commercial properties {kwargs['zip_code']}"
            elif "county" in kwargs:
                query = f"commercial properties {kwargs['county']} {kwargs['state']}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://maps.googleapis.com/maps/api/place/textsearch/json",
                    params={
                        "query": query,
                        "key": self.google_key,
                        "type": "establishment",
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                places = data.get("results", [])
                deals = []
                
                for place in places:
                    address_components = place.get("formatted_address", "").split(",")
                    deals.append({
                        "business_name": place.get("name", ""),
                        "address": place.get("formatted_address", ""),
                        "city": address_components[-3].strip() if len(address_components) >= 3 else "",
                        "state": address_components[-2].strip() if len(address_components) >= 2 else "",
                        "zip": "",
                        "phone": place.get("formatted_phone_number"),
                        "website": place.get("website"),
                        "category": ", ".join(place.get("types", [])[:3]),
                        "places_id": place.get("place_id"),
                    })
                
                return deals
        except Exception as e:
            logger.error(f"Google Places scraping error: {e}")
            return []
    
    def _is_commercial_property(self, org: Dict[str, Any]) -> bool:
        """Filter for commercial properties with parking lots."""
        industry = org.get("industry", "").lower()
        name = org.get("name", "").lower()
        
        commercial_keywords = [
            "mall", "shopping", "restaurant", "retail", "office",
            "parking", "property", "real estate", "hotel", "motel"
        ]
        
        return any(keyword in industry or keyword in name for keyword in commercial_keywords)


scraper_service = ScraperService()

