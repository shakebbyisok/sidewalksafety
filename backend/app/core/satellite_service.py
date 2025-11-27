import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class SatelliteService:
    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_KEY
    
    def get_satellite_image_url(self, latitude: float, longitude: float, zoom: int = 20, size: str = "640x640") -> Optional[str]:
        """Generate Google Maps Static API URL for satellite imagery."""
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_KEY not configured")
            return None
        
        base_url = "https://maps.googleapis.com/maps/api/staticmap"
        url = f"{base_url}?center={latitude},{longitude}&zoom={zoom}&size={size}&maptype=satellite&key={self.api_key}"
        return url
    
    async def download_satellite_image(self, latitude: float, longitude: float) -> Optional[bytes]:
        """Download satellite image as bytes."""
        import httpx
        
        url = self.get_satellite_image_url(latitude, longitude, zoom=20, size="2048x2048")
        if not url:
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f"Error downloading satellite image: {e}")
            return None


satellite_service = SatelliteService()

