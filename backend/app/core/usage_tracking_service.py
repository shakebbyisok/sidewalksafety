"""
Usage Tracking Service

Tracks API usage for monitoring and quota management.

BILLING MODELS:
- OpenRouter: Per-token billing, returns actual cost in API response
- Google Places: Per-request (~$17-32/1K) with $200 free credit/month
- Regrid: Subscription-based with monthly API call quota (NOT per-call billing)
- Google Satellite (contextily): FREE - uses raw tile server, not official API
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal

from app.models.usage_log import UsageLog

logger = logging.getLogger(__name__)


# Cost estimates and billing notes
# These are for DISPLAY purposes - actual billing varies
SERVICE_INFO = {
    "openrouter": {
        "billing": "per_token",
        "note": "Actual cost returned by API",
        "estimate_per_call": 0.0,  # We get actual cost
    },
    "google_places": {
        "billing": "per_request",
        "note": "$200 free credit/month, then ~$17-32/1K requests",
        "estimate_per_call": 0.02,  # ~$20/1K average
    },
    "regrid": {
        "billing": "subscription",
        "note": "Plan-based quota, not per-call billing",
        "estimate_per_call": 0.0,  # Included in subscription
    },
    "google_satellite": {
        "billing": "free",
        "note": "Raw tile server (contextily), not official Google API",
        "estimate_per_call": 0.0,
    },
    "apollo": {
        "billing": "per_credit",
        "note": "Credits-based (~2-3 credits per enrichment)",
        "estimate_per_call": 0.0,  # Credit usage tracked, not $ cost
    },
}


class UsageTrackingService:
    """Service to track API usage for monitoring and quota management."""
    
    def log_api_call(
        self,
        db: Session,
        user_id: UUID,
        service: str,
        operation: Optional[str] = None,
        job_id: Optional[UUID] = None,
        property_id: Optional[UUID] = None,
        api_calls: int = 1,
        tokens_used: int = 0,
        actual_cost: Optional[float] = None,  # For OpenRouter - actual cost from response
        metadata: Optional[Dict[str, Any]] = None
    ) -> UsageLog:
        """
        Log an API call for usage tracking.
        
        Args:
            service: Service name (openrouter, google_places, regrid, google_satellite)
            actual_cost: For OpenRouter, the actual cost returned by the API
        """
        # Get cost estimate based on service
        service_info = SERVICE_INFO.get(service, {"estimate_per_call": 0})
        
        if actual_cost is not None:
            # Use actual cost if provided (OpenRouter)
            cost_estimate = actual_cost
        elif service_info.get("billing") == "per_request":
            # Estimate cost for per-request services
            cost_estimate = service_info["estimate_per_call"] * api_calls
        else:
            # Free or subscription-based - no per-call cost
            cost_estimate = 0.0
        
        log = UsageLog(
            user_id=user_id,
            service=service,
            operation=operation,
            api_calls=api_calls,
            tokens_used=tokens_used,
            cost_estimate=Decimal(str(cost_estimate)) if cost_estimate else None,
            job_id=job_id,
            property_id=property_id,
            extra_data=metadata,
        )
        
        db.add(log)
        db.commit()
        
        # Log differently based on billing type
        if actual_cost:
            logger.info(f"[Usage] {service}: ${actual_cost:.4f} (actual) user={user_id}")
        elif cost_estimate > 0:
            logger.info(f"[Usage] {service} x{api_calls}: ~${cost_estimate:.4f} (est) user={user_id}")
        else:
            logger.info(f"[Usage] {service} x{api_calls} (quota/free) user={user_id}")
        
        return log
    
    def log_openrouter_call(
        self,
        db: Session,
        user_id: UUID,
        model: str,
        tokens_used: int,
        actual_cost: float,
        property_id: Optional[UUID] = None,
        job_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UsageLog:
        """
        Log an OpenRouter VLM call with actual cost from API response.
        
        OpenRouter returns usage info including cost directly in the response,
        so we track the ACTUAL cost, not an estimate.
        """
        log_metadata = {
            "model": model,
            **(metadata or {}),
        }
        
        log = UsageLog(
            user_id=user_id,
            service="openrouter",
            operation="vlm_analysis",
            api_calls=1,
            tokens_used=tokens_used,
            cost_estimate=Decimal(str(actual_cost)),
            job_id=job_id,
            property_id=property_id,
            extra_data=log_metadata,
        )
        
        db.add(log)
        db.commit()
        
        logger.info(
            f"[Usage] OpenRouter {model}: {tokens_used} tokens, ${actual_cost:.6f} user={user_id}"
        )
        
        return log
    
    def log_discovery_job(
        self,
        db: Session,
        user_id: UUID,
        job_id: UUID,
        properties_found: int = 0,
        properties_with_imagery: int = 0,
        properties_analyzed: int = 0,
        businesses_loaded: int = 0,
        vlm_total_cost: float = 0.0,  # Actual cost from OpenRouter
        metadata: Optional[Dict[str, Any]] = None
    ) -> UsageLog:
        """
        Log a complete discovery job summary.
        
        Cost breakdown:
        - Regrid: Subscription (no per-call cost)
        - Satellite: Free (raw tiles)
        - Google Places: ~$0.02/call with $200 free credit
        - VLM: Actual cost from OpenRouter
        """
        # Only Google Places has per-call cost estimate
        places_cost_est = SERVICE_INFO["google_places"]["estimate_per_call"] * businesses_loaded
        
        # Total cost = Places estimate + actual VLM cost
        total_cost = places_cost_est + vlm_total_cost
        
        log_metadata = {
            "properties_found": properties_found,
            "properties_with_imagery": properties_with_imagery,
            "properties_analyzed": properties_analyzed,
            "businesses_loaded": businesses_loaded,
            "cost_breakdown": {
                "google_places_est": round(places_cost_est, 4),
                "vlm_actual": round(vlm_total_cost, 4),
                "regrid": "subscription (no per-call)",
                "satellite": "free (raw tiles)",
            },
            **(metadata or {}),
        }
        
        log = UsageLog(
            user_id=user_id,
            service="discovery_pipeline",
            operation="discovery_job",
            api_calls=1,
            cost_estimate=Decimal(str(total_cost)) if total_cost > 0 else None,
            job_id=job_id,
            extra_data=log_metadata,
        )
        
        db.add(log)
        db.commit()
        
        logger.info(
            f"[Usage] Discovery job: {properties_found} properties, {businesses_loaded} businesses, "
            f"${total_cost:.4f} total (Places ~${places_cost_est:.4f} + VLM ${vlm_total_cost:.4f}) user={user_id}"
        )
        
        return log
    
    def get_user_usage_summary(
        self,
        db: Session,
        user_id: UUID,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get usage summary for a user over the past N days."""
        since = datetime.utcnow() - timedelta(days=days)
        
        # Query usage logs
        logs = db.query(UsageLog).filter(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= since
        ).all()
        
        # Aggregate by service
        by_service = {}
        for log in logs:
            if log.service not in by_service:
                by_service[log.service] = {
                    "count": 0,
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "billing": SERVICE_INFO.get(log.service, {}).get("billing", "unknown"),
                }
            by_service[log.service]["count"] += log.api_calls or 1
            by_service[log.service]["total_cost"] += float(log.cost_estimate or 0)
            by_service[log.service]["total_tokens"] += log.tokens_used or 0
        
        total_cost = sum(float(log.cost_estimate or 0) for log in logs)
        total_tokens = sum(log.tokens_used or 0 for log in logs)
        
        return {
            "period_days": days,
            "total_requests": len(logs),
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "by_service": by_service,
            "billing_notes": {
                "openrouter": "Actual cost (per-token)",
                "google_places": "Estimated (~$200 free/month, then ~$20/1K)",
                "regrid": "Subscription-based (quota only)",
                "google_satellite": "Free (raw tile server)",
            }
        }
    
    def get_daily_usage(
        self,
        db: Session,
        user_id: UUID,
        days: int = 7
    ) -> list:
        """Get daily usage breakdown for a user."""
        since = datetime.utcnow() - timedelta(days=days)
        
        # Query with date grouping
        results = db.query(
            func.date(UsageLog.created_at).label("date"),
            func.count(UsageLog.id).label("request_count"),
            func.sum(UsageLog.cost_estimate).label("total_cost"),
            func.sum(UsageLog.tokens_used).label("total_tokens"),
        ).filter(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= since
        ).group_by(
            func.date(UsageLog.created_at)
        ).order_by(
            func.date(UsageLog.created_at)
        ).all()
        
        return [
            {
                "date": str(r.date),
                "request_count": r.request_count,
                "total_cost_usd": round(float(r.total_cost or 0), 4),
                "total_tokens": r.total_tokens or 0,
            }
            for r in results
        ]


# Singleton instance
usage_tracking_service = UsageTrackingService()
