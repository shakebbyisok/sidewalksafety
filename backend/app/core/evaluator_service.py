import logging
import numpy as np
from PIL import Image
import io
from typing import Dict, Any, Optional, List
from decimal import Decimal
from shapely.geometry import Polygon
from app.core.satellite_service import satellite_service
from app.core.geocoding_service import geocoding_service

logger = logging.getLogger(__name__)


class EvaluatorService:
    def __init__(self):
        self.sam_model = None
        self.yolo_model = None
    
    async def evaluate_deal(self, address: str, latitude: float, longitude: float) -> Dict[str, Any]:
        """Full evaluation pipeline."""
        # 1. Geocode if needed
        if not latitude or not longitude:
            geocode_result = await geocoding_service.geocode_address(address)
            if geocode_result:
                latitude = float(geocode_result["latitude"])
                longitude = float(geocode_result["longitude"])
            else:
                return {"error": "Could not geocode address"}
        
        # 2. Download satellite image
        image_bytes = await satellite_service.download_satellite_image(latitude, longitude)
        if not image_bytes:
            return {"error": "Could not download satellite image"}
        
        image = Image.open(io.BytesIO(image_bytes))
        image_array = np.array(image)
        
        # 3. Detect parking lot (SAM)
        parking_lot_mask = await self._detect_parking_lot(image_array)
        
        # 4. Detect cracks (YOLO)
        crack_detections = await self._detect_cracks(image_array)
        
        # 5. Calculate metrics
        metrics = self._calculate_metrics(parking_lot_mask, crack_detections, latitude, longitude)
        
        # 6. Calculate score
        score = self._calculate_score(metrics)
        
        # 7. Estimate revenue
        revenue = self._estimate_revenue(metrics)
        
        return {
            "deal_score": score,
            "parking_lot_area_sqft": metrics["area_sqft"],
            "crack_density_percent": metrics["crack_density"],
            "damage_severity": metrics["severity"],
            "estimated_repair_cost": revenue * 0.6,
            "estimated_job_value": revenue,
            "satellite_image_url": satellite_service.get_satellite_image_url(latitude, longitude),
            "parking_lot_mask": parking_lot_mask,
            "crack_detections": crack_detections,
            "evaluation_metadata": metrics,
        }
    
    async def _detect_parking_lot(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Detect parking lot boundaries using SAM."""
        # TODO: Implement SAM integration
        # For now, return a placeholder polygon covering center area
        h, w = image.shape[:2]
        center_x, center_y = w // 2, h // 2
        size = min(w, h) // 3
        
        polygon = [
            [center_x - size, center_y - size],
            [center_x + size, center_y - size],
            [center_x + size, center_y + size],
            [center_x - size, center_y + size],
        ]
        
        return {
            "type": "Polygon",
            "coordinates": [polygon]
        }
    
    async def _detect_cracks(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Detect cracks using YOLOv8."""
        # TODO: Implement YOLOv8 integration
        # For now, return empty list
        return []
    
    def _calculate_metrics(self, mask: Optional[Dict], detections: List[Dict], lat: float, lon: float) -> Dict[str, Any]:
        """Calculate parking lot metrics."""
        if not mask:
            return {
                "area_sqft": 0,
                "crack_density": 0,
                "severity": "low",
            }
        
        # Calculate area from polygon
        coords = mask.get("coordinates", [[]])[0]
        if len(coords) >= 3:
            polygon = Polygon(coords)
            # Convert pixel area to square feet (rough estimate)
            # This is a placeholder - real calculation needs proper georeferencing
            area_sqft = polygon.area * 100  # Placeholder multiplier
        
        crack_count = len(detections)
        crack_density = (crack_count / max(area_sqft / 1000, 1)) * 100 if area_sqft > 0 else 0
        
        if crack_density > 10:
            severity = "high"
        elif crack_density > 5:
            severity = "medium"
        else:
            severity = "low"
        
        return {
            "area_sqft": area_sqft,
            "crack_density": crack_density,
            "severity": severity,
        }
    
    def _calculate_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate deal score 0-100."""
        area = metrics.get("area_sqft", 0)
        severity = metrics.get("severity", "low")
        
        # Base score from area (larger = better, max 50 points)
        area_score = min(50, (area / 10000) * 50)
        
        # Damage multiplier (more damage = higher value, max 50 points)
        severity_multipliers = {"low": 20, "medium": 35, "high": 50}
        damage_score = severity_multipliers.get(severity, 20)
        
        return round(area_score + damage_score, 2)
    
    def _estimate_revenue(self, metrics: Dict[str, Any]) -> float:
        """Estimate job revenue."""
        area = metrics.get("area_sqft", 0)
        severity = metrics.get("severity", "low")
        
        base_cost_per_sqft = 2.0  # $2 per sqft base
        severity_multipliers = {"low": 1.0, "medium": 1.5, "high": 2.0}
        
        multiplier = severity_multipliers.get(severity, 1.0)
        return round(area * base_cost_per_sqft * multiplier, 2)


evaluator_service = EvaluatorService()

