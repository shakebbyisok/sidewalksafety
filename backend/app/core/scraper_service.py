import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ScraperService:
    def __init__(self):
        self.apollo_key = settings.APOLLO_API_KEY
        self.google_key = settings.GOOGLE_MAPS_KEY
    
    async def scrape_by_zip(self, zip_code: str, max_deals: int = 50) -> List[Dict[str, Any]]:
        """Scrape businesses by ZIP code."""
        deals = []
        
        # Try Apollo first if available
        if self.apollo_key:
            apollo_deals = await self._scrape_apollo(zip_code=zip_code, max_deals=max_deals)
            deals.extend(apollo_deals)
        
        # If we don't have enough deals, use Google Places
        if len(deals) < max_deals:
            remaining = max_deals - len(deals)
            google_deals = await self._scrape_google_places(zip_code=zip_code, max_deals=remaining)
            deals.extend(google_deals)
        
        return deals[:max_deals]  # Ensure we don't exceed limit
    
    async def scrape_by_county(self, county: str, state: str, max_deals: int = 50) -> List[Dict[str, Any]]:
        """Scrape businesses by county."""
        deals = []
        
        # Try Apollo first if available
        if self.apollo_key:
            apollo_deals = await self._scrape_apollo(county=county, state=state, max_deals=max_deals)
            deals.extend(apollo_deals)
        
        # If we don't have enough deals, use Google Places
        if len(deals) < max_deals:
            remaining = max_deals - len(deals)
            google_deals = await self._scrape_google_places(county=county, state=state, max_deals=remaining)
            deals.extend(google_deals)
        
        return deals[:max_deals]  # Ensure we don't exceed limit
    
    async def _scrape_apollo(self, **kwargs) -> List[Dict[str, Any]]:
        """Scrape from Apollo.io API."""
        if not self.apollo_key:
            return []
        
        max_deals = kwargs.get("max_deals", 50)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Apollo API requires proper payload structure
                payload = {
                    "api_key": self.apollo_key,
                    "page": 1,
                    "per_page": min(max_deals, 25),  # Apollo limits per_page
                }
                
                # Add location filter
                if "zip_code" in kwargs:
                    payload["q_organization_keyword_tags"] = [kwargs["zip_code"]]
                elif "county" in kwargs:
                    payload["q_organization_keyword_tags"] = [f"{kwargs['county']} {kwargs['state']}"]
                else:
                    return []  # Need location filter
                
                response = await client.post(
                    "https://api.apollo.io/v1/organizations/search",
                    json=payload,
                    headers={"Content-Type": "application/json", "Cache-Control": "no-cache"}
                )
                
                if response.status_code == 422:
                    logger.warning("Apollo API validation error - check API key and payload format")
                    return []
                
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
                        
                        if len(deals) >= max_deals:
                            break
                
                return deals[:max_deals]
        except Exception as e:
            logger.error(f"Apollo scraping error: {e}")
            return []
    
    async def _scrape_google_places(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape from Google Places API with pagination.
        
        Cost note: Google Places Text Search costs $32 per 1000 requests.
        Each query + pagination = multiple requests. Use max_deals to control costs.
        """
        if not self.google_key:
            return []
        
        max_deals = kwargs.get("max_deals", 50)
        deals = []
        
        # Prioritized queries - start with most relevant
        queries = []
        if "zip_code" in kwargs:
            zip_code = kwargs["zip_code"]
            # Start with most relevant commercial properties
            queries = [
                f"shopping centers {zip_code}",
                f"malls {zip_code}",
                f"restaurants {zip_code}",
                f"retail stores {zip_code}",
            ]
            # Only add more if we need more deals
            if max_deals > 50:
                queries.extend([
                    f"office buildings {zip_code}",
                    f"hotels {zip_code}",
                ])
        elif "county" in kwargs:
            county = kwargs["county"]
            state = kwargs["state"]
            queries = [
                f"shopping centers {county} {state}",
                f"restaurants {county} {state}",
                f"retail stores {county} {state}",
            ]
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for query in queries:
                    if len(deals) >= max_deals:
                        break
                    
                    next_page_token = None
                    page_count = 0
                    max_pages = 2  # Limit pages to control costs
                    
                    while page_count < max_pages:
                        params = {
                            "query": query,
                            "key": self.google_key,
                        }
                        
                        if next_page_token:
                            params["pagetoken"] = next_page_token
                            # Google requires a delay between page requests
                            import asyncio
                            await asyncio.sleep(2)
                        
                        response = await client.get(
                            "https://maps.googleapis.com/maps/api/place/textsearch/json",
                            params=params
                        )
                        response.raise_for_status()
                        data = response.json()
                        
                        if data.get("status") != "OK":
                            logger.warning(f"Google Places API error: {data.get('status')}")
                            break
                        
                        places = data.get("results", [])
                        
                        for place in places:
                            # Skip if we already have this place_id
                            place_id = place.get("place_id")
                            if any(d.get("places_id") == place_id for d in deals):
                                continue
                            
                            address_components = place.get("formatted_address", "").split(",")
                            
                            # Extract ZIP from address
                            zip_code = ""
                            for component in address_components:
                                component = component.strip()
                                if len(component) == 5 and component.isdigit():
                                    zip_code = component
                                    break
                            
                            deals.append({
                                "business_name": place.get("name", ""),
                                "address": place.get("formatted_address", ""),
                                "city": address_components[-3].strip() if len(address_components) >= 3 else "",
                                "state": address_components[-2].strip() if len(address_components) >= 2 else "",
                                "zip": zip_code,
                                "phone": place.get("formatted_phone_number"),
                                "website": place.get("website"),
                                "category": ", ".join(place.get("types", [])[:3]),
                                "places_id": place_id,
                            })
                        
                        # Check for next page
                        next_page_token = data.get("next_page_token")
                        if not next_page_token:
                            break
                        
                        page_count += 1
                        
                        # Stop if we have enough deals
                        if len(deals) >= max_deals:
                            break
                
                return deals[:max_deals]
        except Exception as e:
            logger.error(f"Google Places scraping error: {e}")
            return deals[:max_deals]  # Return what we got so far, respecting limit
    
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

