import logging
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class PropertyVerificationResult:
    """Result of property verification."""
    def __init__(
        self,
        has_parking_lot: bool,
        verification_method: str,
        geometry_data: Optional[Dict[str, Any]] = None
    ):
        self.has_parking_lot = has_parking_lot
        self.verification_method = verification_method
        self.geometry_data = geometry_data


class PropertyVerificationService:
    """Service to verify if a business has a parking lot."""
    
    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/place/details/json"
    
    async def verify_parking_lot_exists(
        self,
        places_id: Optional[str],
        latitude: float,
        longitude: float
    ) -> PropertyVerificationResult:
        """
        Verify if business has parking lot using Google Places Place Details API.
        
        Args:
            places_id: Google Places place_id
            latitude: Business latitude
            longitude: Business longitude
            
        Returns:
            PropertyVerificationResult with verification status
        """
        if not self.api_key:
            logger.warning("GOOGLE_MAPS_KEY not configured")
            return PropertyVerificationResult(
                has_parking_lot=False,
                verification_method="api_key_missing"
            )
        
        if not places_id:
            logger.debug("No places_id provided, cannot verify")
            return PropertyVerificationResult(
                has_parking_lot=False,
                verification_method="no_place_id"
            )
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.base_url,
                    params={
                        "place_id": places_id,
                        "fields": "geometry,parkingOptions",
                        "key": self.api_key
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") != "OK":
                    logger.warning(f"Place Details API error: {data.get('status')} for place_id {places_id}")
                    return PropertyVerificationResult(
                        has_parking_lot=False,
                        verification_method="api_error"
                    )
                
                result = data.get("result", {})
                parking_options = result.get("parkingOptions", {})
                parking_lot = parking_options.get("parkingLot")
                
                if parking_lot is True:
                    return PropertyVerificationResult(
                        has_parking_lot=True,
                        verification_method="place_details",
                        geometry_data=result.get("geometry")
                    )
                elif parking_lot is False:
                    return PropertyVerificationResult(
                        has_parking_lot=False,
                        verification_method="place_details"
                    )
                else:
                    # Field not available in API response
                    logger.debug(f"parkingOptions.parkingLot not available for place_id {places_id}")
                    return PropertyVerificationResult(
                        has_parking_lot=False,
                        verification_method="field_unavailable"
                    )
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout verifying place_id {places_id}")
            return PropertyVerificationResult(
                has_parking_lot=False,
                verification_method="timeout"
            )
        except Exception as e:
            logger.error(f"Error verifying parking lot for place_id {places_id}: {e}")
            return PropertyVerificationResult(
                has_parking_lot=False,
                verification_method="error"
            )


property_verification_service = PropertyVerificationService()

