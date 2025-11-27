import logging
import httpx
from typing import Optional, Dict, Any
from decimal import Decimal
from app.core.config import settings

logger = logging.getLogger(__name__)


class GeocodingService:
    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    
    async def geocode_address(self, address: str) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_KEY not configured")
            return None
        
        if not address or len(address.strip()) < 3:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.base_url,
                    params={"address": address, "key": self.api_key}
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != "OK":
                    logger.error(f"Geocoding error: {data.get('status')}")
                    return None
                
                results = data.get("results", [])
                if not results:
                    return None
                
                result = results[0]
                location = result.get("geometry", {}).get("location", {})
                
                return {
                    "latitude": Decimal(str(location.get("lat", 0))),
                    "longitude": Decimal(str(location.get("lng", 0))),
                    "formatted_address": result.get("formatted_address", address),
                    "place_id": result.get("place_id"),
                }
        except Exception as e:
            logger.error(f"Error geocoding address: {e}")
            return None
    
    async def reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Reverse geocode coordinates to get address components (ZIP, county, etc.)."""
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_KEY not configured")
            return None
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "latlng": f"{latitude},{longitude}",
                        "key": self.api_key
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != "OK":
                    logger.error(f"Reverse geocoding error: {data.get('status')}")
                    return None
                
                results = data.get("results", [])
                if not results:
                    return None
                
                result = results[0]
                components = result.get("address_components", [])
                
                # Extract ZIP, county, state, city
                zip_code = None
                county = None
                state = None
                city = None
                
                for component in components:
                    types = component.get("types", [])
                    if "postal_code" in types:
                        zip_code = component.get("long_name")
                    elif "administrative_area_level_2" in types:  # County
                        county = component.get("long_name")
                    elif "administrative_area_level_1" in types:  # State
                        state = component.get("short_name")
                    elif "locality" in types:
                        city = component.get("long_name")
                
                return {
                    "formatted_address": result.get("formatted_address"),
                    "zip": zip_code,
                    "county": county,
                    "state": state,
                    "city": city,
                    "place_id": result.get("place_id"),
                }
        except Exception as e:
            logger.error(f"Error reverse geocoding coordinates: {e}")
            return None


geocoding_service = GeocodingService()

